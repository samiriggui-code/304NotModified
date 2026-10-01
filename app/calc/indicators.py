"""Indicateurs repris à l'identique d'IchiVol (ichivol-app/engine/app/indicators/) : Ichimoku, volume
relatif (RVOL), ATR et régime de volatilité, ADX. Seule différence : la bougie ne porte plus le type de
volume ni le volume acheteur, propres aux fournisseurs de données d'IchiVol.

Chaque valeur à l'indice i est une fonction pure des bougies 0..i (anti-regard vers le futur).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


# --- Ichimoku (IchiVol app/indicators/ichimoku.py) ----------------------------------------------


@dataclass(frozen=True)
class IchimokuParams:
    tenkan: int = 9
    kijun: int = 26
    senkou_b: int = 52
    displacement: int = 26


class PriceVsKumo(str, Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    INSIDE = "INSIDE"
    UNKNOWN = "UNKNOWN"


class CrossState(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class ChikouState(str, Enum):
    CLEAR_BULLISH = "CLEAR_BULLISH"
    CLEAR_BEARISH = "CLEAR_BEARISH"
    OBSTRUCTED = "OBSTRUCTED"
    UNKNOWN = "UNKNOWN"


class Strength(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IchimokuState:
    time: int
    tenkan: float | None
    kijun: float | None
    senkou_a: float | None
    senkou_b: float | None
    cloud_top: float | None
    cloud_bot: float | None
    price_vs_kumo: PriceVsKumo
    tk_cross: CrossState
    tk_strength: Strength
    future_kumo: CrossState
    chikou_state: ChikouState
    kumo_breakout: CrossState
    kumo_thickness: float | None
    trend_strength: Strength
    score: float | None


def _donchian_mid(candles: Sequence[Candle], end: int, length: int) -> float | None:
    start = end - length + 1
    if start < 0:
        return None
    window = candles[start : end + 1]
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    return (hi + lo) / 2


def _tk_strength_from_gap(rel_gap: float) -> Strength:
    if rel_gap >= 0.01:
        return Strength.STRONG
    if rel_gap >= 0.003:
        return Strength.MODERATE
    return Strength.WEAK


def compute_ichimoku(candles: Sequence[Candle], params: IchimokuParams | None = None) -> list[IchimokuState]:
    params = params or IchimokuParams()
    n = len(candles)
    d = params.displacement
    tenkan_raw: list[float | None] = [None] * n
    kijun_raw: list[float | None] = [None] * n
    span_a_raw: list[float | None] = [None] * n
    span_b_raw: list[float | None] = [None] * n
    for i in range(n):
        tenkan_raw[i] = _donchian_mid(candles, i, params.tenkan)
        kijun_raw[i] = _donchian_mid(candles, i, params.kijun)
        if tenkan_raw[i] is not None and kijun_raw[i] is not None:
            span_a_raw[i] = (tenkan_raw[i] + kijun_raw[i]) / 2
        span_b_raw[i] = _donchian_mid(candles, i, params.senkou_b)

    cloud_top_hist: list[float | None] = [None] * n
    cloud_bot_hist: list[float | None] = [None] * n
    out: list[IchimokuState] = []
    for i in range(n):
        tenkan, kijun, close = tenkan_raw[i], kijun_raw[i], candles[i].close
        # Le nuage affiché à i a été calculé avec les données de i - d : aucune donnée future.
        cloud_idx = i - d
        sa = span_a_raw[cloud_idx] if cloud_idx >= 0 else None
        sb = span_b_raw[cloud_idx] if cloud_idx >= 0 else None
        cloud_top = max(sa, sb) if sa is not None and sb is not None else None
        cloud_bot = min(sa, sb) if sa is not None and sb is not None else None
        cloud_top_hist[i], cloud_bot_hist[i] = cloud_top, cloud_bot

        if cloud_top is None or cloud_bot is None:
            price_vs_kumo = PriceVsKumo.UNKNOWN
        elif close > cloud_top:
            price_vs_kumo = PriceVsKumo.ABOVE
        elif close < cloud_bot:
            price_vs_kumo = PriceVsKumo.BELOW
        else:
            price_vs_kumo = PriceVsKumo.INSIDE

        if tenkan is None or kijun is None:
            tk_cross, tk_strength = CrossState.UNKNOWN, Strength.UNKNOWN
        else:
            rel_gap = abs(tenkan - kijun) / close if close else 0.0
            tk_strength = _tk_strength_from_gap(rel_gap)
            prev_t = tenkan_raw[i - 1] if i > 0 else None
            prev_k = kijun_raw[i - 1] if i > 0 else None
            if prev_t is None or prev_k is None:
                tk_cross = CrossState.NONE
            elif prev_t <= prev_k and tenkan > kijun:
                tk_cross = CrossState.BULLISH
            elif prev_t >= prev_k and tenkan < kijun:
                tk_cross = CrossState.BEARISH
            else:
                tk_cross = CrossState.NONE

        # Nuage futur calculé avec les données jusqu'à i : une projection, pas une lecture du futur.
        sa_now, sb_now = span_a_raw[i], span_b_raw[i]
        if sa_now is None or sb_now is None:
            future_kumo = CrossState.UNKNOWN
        elif sa_now > sb_now:
            future_kumo = CrossState.BULLISH
        elif sa_now < sb_now:
            future_kumo = CrossState.BEARISH
        else:
            future_kumo = CrossState.NONE

        # Chikou causal : clôture actuelle contre le nuage tel qu'il était d périodes plus tôt.
        ref_idx = i - d
        ref_top = cloud_top_hist[ref_idx] if ref_idx >= 0 else None
        ref_bot = cloud_bot_hist[ref_idx] if ref_idx >= 0 else None
        if ref_top is None or ref_bot is None:
            chikou_state = ChikouState.UNKNOWN
        elif close > ref_top:
            chikou_state = ChikouState.CLEAR_BULLISH
        elif close < ref_bot:
            chikou_state = ChikouState.CLEAR_BEARISH
        else:
            chikou_state = ChikouState.OBSTRUCTED

        prev_top = cloud_top_hist[i - 1] if i > 0 else None
        prev_bot = cloud_bot_hist[i - 1] if i > 0 else None
        if cloud_top is None or cloud_bot is None or prev_top is None or prev_bot is None:
            kumo_breakout = CrossState.UNKNOWN if cloud_top is None else CrossState.NONE
        else:
            prev_close = candles[i - 1].close
            if prev_close <= prev_top and close > cloud_top:
                kumo_breakout = CrossState.BULLISH
            elif prev_close >= prev_bot and close < cloud_bot:
                kumo_breakout = CrossState.BEARISH
            else:
                kumo_breakout = CrossState.NONE

        kumo_thickness = cloud_top - cloud_bot if cloud_top is not None and cloud_bot is not None else None

        score, weight = 0.0, 0.0
        for state, bullish, bearish, w in (
            (price_vs_kumo, PriceVsKumo.ABOVE, PriceVsKumo.BELOW, 3.0),
            (tk_cross, CrossState.BULLISH, CrossState.BEARISH, 2.0),
            (future_kumo, CrossState.BULLISH, CrossState.BEARISH, 2.0),
            (chikou_state, ChikouState.CLEAR_BULLISH, ChikouState.CLEAR_BEARISH, 2.0),
            (kumo_breakout, CrossState.BULLISH, CrossState.BEARISH, 3.0),
        ):
            if state == bullish:
                score += w
                weight += w
            elif state == bearish:
                score -= w
                weight += w
            elif state not in (CrossState.UNKNOWN, PriceVsKumo.UNKNOWN, ChikouState.UNKNOWN):
                weight += w

        final_score = (score / weight * 100) if weight > 0 else None
        if final_score is None:
            trend_strength = Strength.UNKNOWN
        elif abs(final_score) >= 60:
            trend_strength = Strength.STRONG
        elif abs(final_score) >= 25:
            trend_strength = Strength.MODERATE
        else:
            trend_strength = Strength.WEAK

        out.append(
            IchimokuState(
                time=candles[i].time,
                tenkan=tenkan,
                kijun=kijun,
                senkou_a=sa,
                senkou_b=sb,
                cloud_top=cloud_top,
                cloud_bot=cloud_bot,
                price_vs_kumo=price_vs_kumo,
                tk_cross=tk_cross,
                tk_strength=tk_strength,
                future_kumo=future_kumo,
                chikou_state=chikou_state,
                kumo_breakout=kumo_breakout,
                kumo_thickness=kumo_thickness,
                trend_strength=trend_strength,
                score=final_score,
            )
        )
    return out


# --- Volume relatif (IchiVol app/indicators/rvol.py) -------------------------------------------


class AnomalyLevel(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    SIGNIFICANT = "SIGNIFICANT"
    STRONG = "STRONG"
    ANOMALY = "ANOMALY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RvolParams:
    primary_window: int = 20
    percentile_lookback: int = 100
    low_threshold: float = 0.7
    significant_threshold: float = 1.5
    strong_threshold: float = 2.0
    anomaly_threshold: float = 3.0


@dataclass(frozen=True)
class RvolState:
    time: int
    volume: float
    avg_volume: float | None
    rvol: float | None
    rvol5: float | None
    rvol10: float | None
    rvol20: float | None
    vol_accel: float | None
    percentile: float | None
    anomaly_level: AnomalyLevel
    confirmed: bool
    spike: bool


def _trailing_avg(candles: Sequence[Candle], end: int, window: int) -> float | None:
    values = [c.volume for c in candles[max(0, end - window + 1) : end + 1]]
    return sum(values) / len(values) if values else None


def _rvol(candles: Sequence[Candle], end: int, window: int) -> tuple[float | None, float | None]:
    avg = _trailing_avg(candles, end, window)
    if avg is None or avg <= 0:
        return avg, None
    return avg, candles[end].volume / avg


def _volume_percentile(candles: Sequence[Candle], end: int, lookback: int) -> float | None:
    window = [c.volume for c in candles[max(0, end - lookback + 1) : end + 1]]
    if len(window) < 2:
        return None
    current = candles[end].volume
    return sum(1 for v in window if v <= current) / len(window)


def _anomaly_level(rvol: float | None, params: RvolParams) -> AnomalyLevel:
    if rvol is None:
        return AnomalyLevel.UNKNOWN
    if rvol < params.low_threshold:
        return AnomalyLevel.LOW
    if rvol < params.significant_threshold:
        return AnomalyLevel.NORMAL
    if rvol < params.strong_threshold:
        return AnomalyLevel.SIGNIFICANT
    if rvol < params.anomaly_threshold:
        return AnomalyLevel.STRONG
    return AnomalyLevel.ANOMALY


def compute_rvol(candles: Sequence[Candle], params: RvolParams | None = None) -> list[RvolState]:
    params = params or RvolParams()
    out: list[RvolState] = []
    for i in range(len(candles)):
        avg5, rvol5 = _rvol(candles, i, 5)
        avg10, rvol10 = _rvol(candles, i, 10)
        avg20, rvol20 = _rvol(candles, i, 20)
        windows = {5: (avg5, rvol5), 10: (avg10, rvol10), 20: (avg20, rvol20)}
        if params.primary_window in windows:
            avg_primary, rvol_primary = windows[params.primary_window]
        else:
            avg_primary, rvol_primary = _rvol(candles, i, params.primary_window)
        vol_accel = rvol5 / rvol20 - 1 if rvol5 is not None and rvol20 not in (None, 0) else None
        out.append(
            RvolState(
                time=candles[i].time,
                volume=candles[i].volume,
                avg_volume=avg_primary,
                rvol=rvol_primary,
                rvol5=rvol5,
                rvol10=rvol10,
                rvol20=rvol20,
                vol_accel=vol_accel,
                percentile=_volume_percentile(candles, i, params.percentile_lookback),
                anomaly_level=_anomaly_level(rvol_primary, params),
                confirmed=rvol_primary is not None and rvol_primary >= params.significant_threshold,
                spike=rvol_primary is not None and rvol_primary >= params.strong_threshold,
            )
        )
    return out


# --- ATR et régime de volatilité (IchiVol app/indicators/atr.py) -------------------------------


class VolatilityRegime(str, Enum):
    DEAD = "DEAD"
    NORMAL = "NORMAL"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AtrParams:
    period: int = 14
    regime_lookback: int = 100
    dead_percentile: float = 0.15
    extreme_percentile: float = 0.90
    stop_multiplier: float = 1.5


@dataclass(frozen=True)
class AtrState:
    time: int
    true_range: float
    atr: float | None
    percentile: float | None
    regime: VolatilityRegime
    suggested_stop_distance: float | None


def _true_range(candles: Sequence[Candle], i: int) -> float:
    if i == 0:
        return candles[0].high - candles[0].low
    prev_close = candles[i - 1].close
    return max(candles[i].high - candles[i].low, abs(candles[i].high - prev_close), abs(candles[i].low - prev_close))


def compute_atr(candles: Sequence[Candle], params: AtrParams | None = None) -> list[AtrState]:
    params = params or AtrParams()
    n = len(candles)
    true_ranges = [_true_range(candles, i) for i in range(n)]
    atr_series: list[float | None] = [None] * n
    out: list[AtrState] = []
    for i in range(n):
        window = true_ranges[max(0, i - params.period + 1) : i + 1]
        atr_val = sum(window) / len(window)
        atr_series[i] = atr_val
        history = [v for v in atr_series[max(0, i - params.regime_lookback + 1) : i + 1] if v is not None]
        percentile = sum(1 for v in history if v <= atr_val) / len(history) if len(history) >= 2 else None
        if percentile is None:
            regime = VolatilityRegime.UNKNOWN
        elif percentile <= params.dead_percentile:
            regime = VolatilityRegime.DEAD
        elif percentile >= params.extreme_percentile:
            regime = VolatilityRegime.EXTREME
        else:
            regime = VolatilityRegime.NORMAL
        out.append(
            AtrState(
                time=candles[i].time,
                true_range=true_ranges[i],
                atr=atr_val,
                percentile=percentile,
                regime=regime,
                suggested_stop_distance=atr_val * params.stop_multiplier,
            )
        )
    return out


# --- ADX, Wilder 1978 (IchiVol app/indicators/adx.py) ------------------------------------------


class TrendStrength(str, Enum):
    ABSENT = "ABSENT"
    DEVELOPING = "DEVELOPING"
    TRENDING = "TRENDING"
    STRONG = "STRONG"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AdxParams:
    period: int = 14
    weak_threshold: float = 20.0
    trending_threshold: float = 25.0
    strong_threshold: float = 40.0


@dataclass(frozen=True)
class AdxState:
    time: int
    plus_di: float | None
    minus_di: float | None
    adx: float | None
    strength: TrendStrength


def _classify_adx(adx_value: float, params: AdxParams) -> TrendStrength:
    if adx_value < params.weak_threshold:
        return TrendStrength.ABSENT
    if adx_value < params.trending_threshold:
        return TrendStrength.DEVELOPING
    if adx_value < params.strong_threshold:
        return TrendStrength.TRENDING
    return TrendStrength.STRONG


def compute_adx(candles: Sequence[Candle], params: AdxParams | None = None) -> list[AdxState]:
    params = params or AdxParams()
    period = params.period
    out: list[AdxState] = []
    tr_buffer: list[float] = []
    plus_dm_buffer: list[float] = []
    minus_dm_buffer: list[float] = []
    dx_values: list[float] = []
    smoothed_tr = smoothed_plus_dm = smoothed_minus_dm = adx_smoothed = None
    prev_high = prev_low = prev_close = None

    for i, c in enumerate(candles):
        if i == 0:
            tr, plus_dm, minus_dm = c.high - c.low, 0.0, 0.0
        else:
            tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
            up_move = c.high - prev_high
            down_move = prev_low - c.low
            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0
        prev_high, prev_low, prev_close = c.high, c.low, c.close

        if smoothed_tr is None:
            tr_buffer.append(tr)
            plus_dm_buffer.append(plus_dm)
            minus_dm_buffer.append(minus_dm)
            if len(tr_buffer) < period:
                out.append(AdxState(c.time, None, None, None, TrendStrength.UNKNOWN))
                continue
            smoothed_tr = sum(tr_buffer)
            smoothed_plus_dm = sum(plus_dm_buffer)
            smoothed_minus_dm = sum(minus_dm_buffer)
        else:
            smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr
            smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / period) + plus_dm
            smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / period) + minus_dm

        plus_di = 100 * smoothed_plus_dm / smoothed_tr if smoothed_tr > 0 else 0.0
        minus_di = 100 * smoothed_minus_dm / smoothed_tr if smoothed_tr > 0 else 0.0
        di_sum = plus_di + minus_di
        dx = 100 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0.0

        if adx_smoothed is None:
            dx_values.append(dx)
            if len(dx_values) < period:
                out.append(AdxState(c.time, plus_di, minus_di, None, TrendStrength.UNKNOWN))
                continue
            adx_smoothed = sum(dx_values) / period
        else:
            adx_smoothed = (adx_smoothed * (period - 1) + dx) / period
        out.append(AdxState(c.time, plus_di, minus_di, adx_smoothed, _classify_adx(adx_smoothed, params)))
    return out
