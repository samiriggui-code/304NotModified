"""Routes /v1/calc/* : calculs sur les bougies envoyées par l'agent (aucune donnée de marché fournie
par 304). Chaque appel réussi est décompté du quota et journalisé à part des questions."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from itertools import pairwise
from typing import Literal

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel, Field, model_validator

from . import DISCLAIMER, METHOD_VERSION
from .analysis import ichimoku_rvol, regime, size_position, sized, stop_distance_from_atr
from .indicators import AdxParams, AtrParams, Candle, IchimokuParams, RvolParams

MAX_CANDLES = 5000
MAX_SERIES = 500


class CandleIn(BaseModel):
    time: int = Field(description="Horodatage Unix (secondes) de l'ouverture de la bougie.")
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def coherent(self):
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close):
            raise ValueError("bougie incohérente : high doit être le plus haut et low le plus bas")
        return self


class CandlesIn(BaseModel):
    candles: list[CandleIn] = Field(
        min_length=2,
        max_length=MAX_CANDLES,
        description="Bougies clôturées, de la plus ancienne à la plus récente (vos propres données).",
    )
    series: int = Field(
        default=0,
        ge=0,
        le=MAX_SERIES,
        description="Nombre de dernières bougies à détailler (0 = la dernière seulement).",
    )

    @model_validator(mode="after")
    def increasing(self):
        times = [c.time for c in self.candles]
        if any(b <= a for a, b in pairwise(times)):
            raise ValueError("les bougies doivent être triées par heure strictement croissante, sans doublon")
        return self

    def as_candles(self) -> list[Candle]:
        return [Candle(c.time, c.open, c.high, c.low, c.close, c.volume) for c in self.candles]


class IchimokuIn(CandlesIn):
    tenkan: int = Field(default=9, ge=2, le=200)
    kijun: int = Field(default=26, ge=2, le=400)
    senkou_b: int = Field(default=52, ge=2, le=800)
    displacement: int = Field(default=26, ge=1, le=400)
    rvol_window: int = Field(default=20, ge=2, le=500)
    rvol_confirm: float = Field(
        default=1.5, gt=0, le=20, description="Seuil de volume relatif qui confirme un événement."
    )


class RegimeIn(CandlesIn):
    adx_period: int = Field(default=14, ge=2, le=200)
    atr_period: int = Field(default=14, ge=2, le=200)
    regime_lookback: int = Field(default=100, ge=10, le=2000)


class PositionIn(BaseModel):
    equity: float = Field(gt=0, description="Capital total du compte.")
    cash: float | None = Field(default=None, ge=0, description="Liquidités disponibles (par défaut : le capital).")
    direction: Literal["LONG", "SHORT"]
    entry_price: float = Field(gt=0)
    stop_distance: float | None = Field(
        default=None, gt=0, description="Distance du stop en prix ; sinon calculée par l'ATR des bougies."
    )
    candles: list[CandleIn] | None = Field(default=None, min_length=2, max_length=MAX_CANDLES)
    atr_period: int = Field(default=14, ge=2, le=200)
    atr_multiplier: float = Field(default=1.5, gt=0, le=20)
    risk_pct: float = Field(default=0.01, gt=0, le=0.2, description="Part du capital risquée si le stop est touché.")
    take_profit_r: float = Field(default=2.0, gt=0, le=50)
    max_notional_pct: float = Field(default=0.25, gt=0, le=10)
    commission_bps: float = Field(default=5.0, ge=0, le=1000)
    spread_bps: float = Field(default=2.0, ge=0, le=1000)
    slippage_bps: float = Field(default=3.0, ge=0, le=1000)

    @model_validator(mode="after")
    def stop_known(self):
        if self.stop_distance is None and not self.candles:
            raise ValueError("donnez stop_distance, ou des bougies pour le calculer par l'ATR")
        return self


def _response(name: str, method: dict, candles: list[Candle] | None, result, series, request_id: str) -> dict:
    return {
        "status": "computed",
        "request_id": request_id,
        "calculation": name,
        "method": {"version": METHOD_VERSION, **method},
        "computed_at": datetime.now(UTC).isoformat(),
        "candles_used": len(candles) if candles else 0,
        "last_candle_time": candles[-1].time if candles else None,
        "result": result,
        "series": series,
        "billable": True,
        "disclaimer": DISCLAIMER,
    }


def register_calc_routes(app: FastAPI, store, require_key: Callable) -> None:
    def run(
        name: str, api_key: str, client: str, compute: Callable[[], tuple[dict, list[Candle] | None, object, list]]
    ):
        started = time.monotonic()
        method, candles, result, series = compute()
        store.consume(api_key)
        request_id = store.log_calc(
            api_key=api_key,
            name=name,
            candles=len(candles) if candles else 0,
            latency_ms=int((time.monotonic() - started) * 1000),
            client=client[:200] or None,
        )
        return _response(name, method, candles, result, series, request_id)

    tags = ["Calculs sur vos données"]

    @app.post("/v1/calc/ichimoku-rvol", tags=tags, summary="Ichimoku confirmé par le volume relatif, sur vos bougies")
    def calc_ichimoku(body: IchimokuIn, api_key: str = Depends(require_key), x_client: str = Header(default="")):
        def compute():
            candles = body.as_candles()
            params = IchimokuParams(body.tenkan, body.kijun, body.senkou_b, body.displacement)
            rvol = RvolParams(primary_window=body.rvol_window, significant_threshold=body.rvol_confirm)
            last, series = ichimoku_rvol(candles, params, rvol, body.series)
            method = {
                "name": "Ichimoku × volume relatif (IchiVol)",
                "rule": "Un croisement Tenkan/Kijun ou une sortie du nuage n'est confirmé que si le volume relatif "
                "(volume / moyenne glissante) atteint rvol_confirm. Chikou évalué sans regard vers le futur.",
                "parameters": {**params.__dict__, "rvol_window": body.rvol_window, "rvol_confirm": body.rvol_confirm},
                "minimum_candles": max(body.senkou_b, body.kijun) + body.displacement,
            }
            return method, candles, last, series

        return run("ichimoku-rvol", api_key, x_client, compute)

    @app.post(
        "/v1/calc/regime", tags=tags, summary="Régime de marché (tendance, volatilité, direction) sur vos bougies"
    )
    def calc_regime(body: RegimeIn, api_key: str = Depends(require_key), x_client: str = Header(default="")):
        def compute():
            candles = body.as_candles()
            adx = AdxParams(period=body.adx_period)
            atr = AtrParams(period=body.atr_period, regime_lookback=body.regime_lookback)
            last, series = regime(candles, adx, atr, body.series)
            method = {
                "name": "Régime de marché (IchiVol)",
                "rule": "Structure par l'ADX de Wilder (tendance dès 25, forte dès 40), volatilité par le rang de "
                "l'ATR dans son propre historique (basse ≤ 15 %, haute ≥ 90 %), direction par +DI/-DI. "
                "Description du marché, jamais un sens d'entrée.",
                "parameters": {"adx": adx.__dict__, "atr": atr.__dict__},
                "minimum_candles": 2 * body.adx_period,
            }
            return method, candles, last, series

        return run("regime", api_key, x_client, compute)

    @app.post(
        "/v1/calc/position-size", tags=tags, summary="Taille de position pour un risque fixé (stop donné ou par l'ATR)"
    )
    def calc_position(body: PositionIn, api_key: str = Depends(require_key), x_client: str = Header(default="")):
        def compute():
            candles = [Candle(c.time, c.open, c.high, c.low, c.close, c.volume) for c in body.candles or []]
            atr = AtrParams(period=body.atr_period, stop_multiplier=body.atr_multiplier)
            stop = body.stop_distance or stop_distance_from_atr(candles, atr)
            order = size_position(
                equity=body.equity,
                cash=body.cash if body.cash is not None else body.equity,
                direction=body.direction,
                entry_price=body.entry_price,
                stop_distance=stop,
                risk_pct=body.risk_pct,
                take_profit_r=body.take_profit_r,
                max_notional_pct=body.max_notional_pct,
                commission_bps=body.commission_bps,
                spread_bps=body.spread_bps,
                slippage_bps=body.slippage_bps,
            )
            result = {
                "stop_distance": stop,
                "stop_source": "given" if body.stop_distance else "atr",
                "order": sized(order),
                "refused": None
                if order
                else "Taille impossible : stop nul, capital ou liquidités insuffisants, "
                "ou stop / objectif au-dessous de zéro.",
            }
            method = {
                "name": "Risque fixe en fraction du capital (IchiVol)",
                "rule": "quantité = capital × risk_pct / distance du stop, plafonnée à max_notional_pct du capital et "
                "aux liquidités ; prix d'entrée dégradé de l'écart et du glissement ; objectif à take_profit_r fois "
                "la distance du stop.",
                "parameters": body.model_dump(exclude={"candles"}),
            }
            return method, candles or None, result, []

        return run("position-size", api_key, x_client, compute)
