"""Calculs sur les données de l'agent : valeurs connues, absence de regard vers le futur (méthode de
troncature reprise d'IchiVol), et routes /v1/calc/*."""

import random
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from app.calc.analysis import size_position
from app.calc.indicators import (
    AnomalyLevel,
    Candle,
    CrossState,
    PriceVsKumo,
    TrendStrength,
    VolatilityRegime,
    compute_adx,
    compute_atr,
    compute_ichimoku,
    compute_rvol,
)
from app.main import create_app
from app.resolver import NullResolver
from app.store import Store


def random_candles(n: int, seed: int = 42) -> list[Candle]:
    rng = random.Random(seed)
    price, out = 100.0, []
    for i in range(n):
        open_ = price
        close = max(1.0, price + rng.uniform(-1.5, 1.5))
        high = max(open_, close) + rng.uniform(0, 1.0)
        low = min(open_, close) - rng.uniform(0, 1.0)
        out.append(Candle(i * 3600, open_, high, low, close, rng.uniform(10, 1000)))
        price = close
    return out


def flat(n: int, price: float = 100.0, volume: float = 1.0) -> list[Candle]:
    return [Candle(i, price, price, price, price, volume) for i in range(n)]


# --- Aucun regard vers le futur : la valeur à t ne change pas quand on retire les bougies d'après ---


@pytest.mark.parametrize("compute", [compute_ichimoku, compute_rvol, compute_atr, compute_adx])
def test_value_at_t_never_depends_on_later_candles(compute):
    candles = random_candles(220)
    full = compute(candles)
    for t in (10, 27, 53, 79, 105, 150, 219):
        assert asdict(compute(candles[:t])[-1]) == asdict(full[t - 1]), f"différence à t={t}"


# --- Valeurs connues (tests d'IchiVol) ---


def test_ichimoku_flat_market_and_short_history():
    assert compute_ichimoku(flat(5))[0].price_vs_kumo == PriceVsKumo.UNKNOWN
    last = compute_ichimoku(flat(120, 50.0))[-1]
    assert last.tenkan == last.kijun == last.cloud_top == last.cloud_bot == 50.0
    assert last.kumo_thickness == 0.0 and last.tk_cross == CrossState.NONE
    assert last.price_vs_kumo == PriceVsKumo.INSIDE


def test_rvol_constant_volume_then_spike():
    states = compute_rvol(flat(40, volume=50.0))
    assert states[-1].rvol == 1.0 and states[-1].anomaly_level == AnomalyLevel.NORMAL
    spike = compute_rvol(flat(30, volume=50.0) + [Candle(30, 100, 100, 100, 100, 200.0)])[-1]
    assert spike.anomaly_level == AnomalyLevel.ANOMALY and spike.confirmed and spike.spike


def test_atr_counts_gaps_and_flags_a_volatility_spike():
    gap = [Candle(0, 100, 101, 99, 100, 1), Candle(1, 108, 110, 108, 109, 1)]
    assert compute_atr(gap)[1].true_range == pytest.approx(10.0)
    spike = [Candle(150 + i, 100, 100 + 50 * (i + 1), 100, 100, 1) for i in range(3)]
    assert compute_atr(flat(150) + spike)[-1].regime == VolatilityRegime.EXTREME


def test_adx_sees_a_steady_uptrend():
    candles = [Candle(i, 100 + 2 * i, 100 + 2 * i + 1, 100 + 2 * i - 0.5, 100 + 2 * i, 10) for i in range(80)]
    last = compute_adx(candles)[-1]
    assert last.strength in (TrendStrength.TRENDING, TrendStrength.STRONG) and last.plus_di > last.minus_di


def test_position_size_respects_risk_and_caps():
    # 1 % de 10 000 = 100 de risque ; stop à 2 → 50 unités, soit ≈ 5 000 de position : plafonnée à 25 % (2 500).
    order = size_position(equity=10_000, cash=10_000, direction="LONG", entry_price=100, stop_distance=2)
    assert order.notional == pytest.approx(2_500)
    assert order.risk_amount == pytest.approx(order.qty * 2) and order.risk_amount < 100
    assert order.stop_price < order.entry_fill < order.take_profit_price
    small = size_position(equity=10_000, cash=10_000, direction="LONG", entry_price=100, stop_distance=10)
    assert small.risk_amount == pytest.approx(100)  # sous le plafond : risque exact de 1 %
    assert size_position(equity=10_000, cash=0, direction="LONG", entry_price=100, stop_distance=2) is None
    assert size_position(equity=10_000, cash=10_000, direction="SHORT", entry_price=1, stop_distance=2) is None


# --- Routes ---


def as_json(candles: list[Candle]) -> list[dict]:
    return [asdict(c) for c in candles]


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Store(str(tmp_path / "t.sqlite3")), NullResolver()))


def test_ichimoku_route_returns_method_result_and_series(client):
    body = client.post("/v1/calc/ichimoku-rvol", json={"candles": as_json(random_candles(150)), "series": 3}).json()
    assert body["status"] == "computed" and body["billable"] is True
    assert body["candles_used"] == 150 and body["last_candle_time"] == 149 * 3600
    assert body["method"]["parameters"]["tenkan"] == 9 and "conseil" in body["disclaimer"]
    assert set(body["result"]) == {"ichimoku", "rvol", "event"} and len(body["series"]) == 3
    expected = compute_ichimoku(random_candles(150))[-1]
    assert body["result"]["ichimoku"]["score"] == pytest.approx(expected.score)


def test_event_is_volume_confirmed_only_with_enough_volume(client):
    # Montée brusque après un marché calme : sortie du nuage par le haut, avec ou sans volume.
    base = [Candle(i, 100, 100.5, 99.5, 100, 50.0) for i in range(80)]
    for volume, confirmed in ((50.0, False), (500.0, True)):
        candles = base + [Candle(80, 100, 110, 100, 109, volume)]
        event = client.post("/v1/calc/ichimoku-rvol", json={"candles": as_json(candles)}).json()["result"]["event"]
        assert event["kumo_breakout"] == "BULLISH" and event["volume_confirmed"] is confirmed


def test_regime_route(client):
    body = client.post("/v1/calc/regime", json={"candles": as_json(random_candles(200))}).json()
    assert body["result"]["structure"] in ("TRENDING", "RANGING")
    assert body["result"]["volatility"].endswith("VOLATILITY")


def test_position_size_from_atr_or_given_stop(client):
    from_atr = client.post(
        "/v1/calc/position-size",
        json={"equity": 10000, "direction": "LONG", "entry_price": 100, "candles": as_json(random_candles(50))},
    ).json()["result"]
    assert from_atr["stop_source"] == "atr" and from_atr["order"]["qty"] > 0
    refused = client.post(
        "/v1/calc/position-size",
        json={"equity": 10000, "cash": 0, "direction": "LONG", "entry_price": 100, "stop_distance": 2},
    ).json()["result"]
    assert refused["order"] is None and refused["refused"]
    missing = client.post("/v1/calc/position-size", json={"equity": 10000, "direction": "LONG", "entry_price": 100})
    assert missing.status_code == 422


BAD = [
    [{"time": 2, "open": 1, "high": 1, "low": 1, "close": 1}, {"time": 1, "open": 1, "high": 1, "low": 1, "close": 1}],
    [
        {"time": 1, "open": 1, "high": 0.5, "low": 1, "close": 1},
        {"time": 2, "open": 1, "high": 1, "low": 1, "close": 1},
    ],
]


@pytest.mark.parametrize("candles", BAD)
def test_bad_candles_are_refused(client, candles):
    assert client.post("/v1/calc/regime", json={"candles": candles}).status_code == 422


def test_calculations_use_the_quota_and_are_counted_apart(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ADMIN_TOKEN", "t")
    client = TestClient(create_app(Store(str(tmp_path / "t.sqlite3")), NullResolver()))
    admin = {"Authorization": "Bearer t"}
    key = client.post("/internal/keys", json={"label": "x", "quota": 2}, headers=admin).json()["api_key"]
    body = {"candles": as_json(random_candles(60))}
    for _ in range(2):
        assert client.post("/v1/calc/regime", json=body, headers={"X-API-Key": key}).status_code == 200
    assert client.post("/v1/calc/regime", json=body, headers={"X-API-Key": key}).status_code == 429
    stats = client.get("/internal/stats", headers=admin).json()
    assert stats["calculations"]["regime"]["calls"] == 2 and stats["requests"] == 0
