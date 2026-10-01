"""Régime de marché et taille de position, repris d'IchiVol (app/strategy_lab/regime.py et
app/paper/risk.py), et assemblage des résultats renvoyés aux agents."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import Enum

from .indicators import (
    AdxParams,
    AtrParams,
    Candle,
    CrossState,
    IchimokuParams,
    RvolParams,
    TrendStrength,
    VolatilityRegime,
    compute_adx,
    compute_atr,
    compute_ichimoku,
    compute_rvol,
)

# --- Régime (IchiVol app/strategy_lab/regime.py, sans le registre d'indicateurs) ---------------


class StructureRegime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    UNKNOWN = "UNKNOWN"


class VolRegime(str, Enum):
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    NORMAL_VOLATILITY = "NORMAL_VOLATILITY"
    UNKNOWN = "UNKNOWN"


class DirectionRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    UNKNOWN = "UNKNOWN"


def _structure_from_adx(strength: TrendStrength) -> StructureRegime:
    if strength in (TrendStrength.TRENDING, TrendStrength.STRONG):
        return StructureRegime.TRENDING
    if strength in (TrendStrength.ABSENT, TrendStrength.DEVELOPING):
        return StructureRegime.RANGING
    return StructureRegime.UNKNOWN


def _vol_from_atr(regime: VolatilityRegime) -> VolRegime:
    return {
        VolatilityRegime.EXTREME: VolRegime.HIGH_VOLATILITY,
        VolatilityRegime.DEAD: VolRegime.LOW_VOLATILITY,
        VolatilityRegime.NORMAL: VolRegime.NORMAL_VOLATILITY,
    }.get(regime, VolRegime.UNKNOWN)


def _direction_from_di(
    plus_di: float | None, minus_di: float | None, structure: StructureRegime, *, side_band: float = 2.0
) -> DirectionRegime:
    if structure == StructureRegime.RANGING:
        return DirectionRegime.SIDEWAYS
    if plus_di is None or minus_di is None:
        return DirectionRegime.UNKNOWN
    if plus_di > minus_di + side_band:
        return DirectionRegime.BULL
    if minus_di > plus_di + side_band:
        return DirectionRegime.BEAR
    return DirectionRegime.SIDEWAYS


# --- Taille de position (IchiVol app/paper/risk.py, risque fixe en fraction du capital) --------


@dataclass(frozen=True)
class SizedOrder:
    qty: float
    notional: float
    stop_price: float
    take_profit_price: float
    risk_pct: float
    risk_amount: float
    entry_fill: float


def apply_entry_friction(price: float, *, direction: str, spread_bps: float, slippage_bps: float) -> float:
    """Exécution défavorable pour qui prend la liquidité : un achat paie plus cher, une vente reçoit moins."""
    total = (spread_bps + slippage_bps) / 10_000.0
    return price * (1.0 + total) if direction == "LONG" else price * (1.0 - total)


def size_position(
    *,
    equity: float,
    cash: float,
    direction: str,
    entry_price: float,
    stop_distance: float,
    risk_pct: float = 0.01,
    take_profit_r: float = 2.0,
    max_notional_pct: float = 0.25,
    commission_bps: float = 5.0,
    spread_bps: float = 2.0,
    slippage_bps: float = 3.0,
    min_fill_fraction: float = 0.0,
    min_notional: float = 0.0,
) -> SizedOrder | None:
    if equity <= 0 or entry_price <= 0 or stop_distance <= 0:
        return None
    entry_fill = apply_entry_friction(
        entry_price, direction=direction, spread_bps=spread_bps, slippage_bps=slippage_bps
    )
    risk_amount = equity * risk_pct
    qty = risk_amount / stop_distance
    notional = qty * entry_fill

    max_notional = equity * max_notional_pct
    if notional > max_notional > 0:
        qty = max_notional / entry_fill
        notional = qty * entry_fill
        risk_amount = qty * stop_distance

    intended_notional = notional
    if notional + notional * (commission_bps / 10_000.0) > cash:
        affordable = cash / (1.0 + commission_bps / 10_000.0)
        if affordable <= 0:
            return None
        qty = affordable / entry_fill
        notional = qty * entry_fill
        risk_amount = qty * stop_distance
        if qty <= 0 or notional <= 0 or notional < intended_notional * min_fill_fraction:
            return None
    if notional < min_notional:
        return None

    if direction == "LONG":
        stop_price = entry_fill - stop_distance
        take_profit_price = entry_fill + stop_distance * take_profit_r
    else:
        stop_price = entry_fill + stop_distance
        take_profit_price = entry_fill - stop_distance * take_profit_r
    if stop_price <= 0 or take_profit_price <= 0:
        return None
    return SizedOrder(qty, notional, stop_price, take_profit_price, risk_pct, risk_amount, entry_fill)


# --- Assemblage des résultats -------------------------------------------------------------------


def _plain(obj) -> dict:
    return {k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(obj).items()}


def ichimoku_rvol(
    candles: Sequence[Candle], ichimoku: IchimokuParams, rvol: RvolParams, series: int
) -> tuple[dict, list[dict]]:
    """Principe d'IchiVol : un événement Ichimoku (croisement Tenkan/Kijun ou sortie du nuage) ne compte
    que s'il est confirmé par le volume relatif (RVOL ≥ seuil « significatif », 1,5 par défaut)."""
    ichi = compute_ichimoku(candles, ichimoku)
    vol = compute_rvol(candles, rvol)
    rows = []
    for i_state, v_state in zip(ichi, vol):
        events = [s for s in (i_state.kumo_breakout, i_state.tk_cross) if s in (CrossState.BULLISH, CrossState.BEARISH)]
        direction = events[0].value if events else "NONE"
        rows.append(
            {
                "ichimoku": _plain(i_state),
                "rvol": _plain(v_state),
                "event": {
                    "kumo_breakout": i_state.kumo_breakout.value,
                    "tk_cross": i_state.tk_cross.value,
                    "direction": direction,
                    "volume_confirmed": bool(events) and v_state.confirmed,
                },
            }
        )
    return rows[-1], rows[-series:] if series else []


def regime(candles: Sequence[Candle], adx: AdxParams, atr: AtrParams, series: int) -> tuple[dict, list[dict]]:
    adx_states = compute_adx(candles, adx)
    atr_states = compute_atr(candles, atr)
    rows = []
    for a, v in zip(adx_states, atr_states):
        structure = _structure_from_adx(a.strength)
        rows.append(
            {
                "time": a.time,
                "structure": structure.value,
                "volatility": _vol_from_atr(v.regime).value,
                "direction": _direction_from_di(a.plus_di, a.minus_di, structure).value,
                "adx": _plain(a),
                "atr": _plain(v),
            }
        )
    return rows[-1], rows[-series:] if series else []


def stop_distance_from_atr(candles: Sequence[Candle], atr: AtrParams) -> float:
    return compute_atr(candles, atr)[-1].suggested_stop_distance or 0.0


def sized(order: SizedOrder | None) -> dict | None:
    return asdict(order) if order else None
