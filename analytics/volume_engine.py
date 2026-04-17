"""
Volume Engine — объёмный анализ.

Обрабатывает:
  - trade.raw → CVD (накопленная дельта объёма) в реалтайм
  - candle.{tf}.closed → дельта свечи, Volume Profile, анализ

Публикует:
  volume.cvd.updated    — обновление CVD
  volume.profile.updated — Volume Profile (POC, VAH, VAL)
  volume.delta.candle   — дельта объёма на закрытой свече
"""
from __future__ import annotations

from collections import defaultdict, deque

from core.event_bus import Event, EventBus
from core.logger import get_logger
from data.tf_aggregator import TF_MINUTES
from data.validator import Candle, Trade

log = get_logger("VolumeEngine")

ALL_TIMEFRAMES = ["1m"] + list(TF_MINUTES.keys())

VOLUME_PROFILE_BINS = 50    # число уровней в профиле
VAH_VAL_PCT = 0.70          # Value Area = 70% от суммарного объёма
CVD_WINDOW = 500            # максимальное число сделок в CVD буфере


# ─── Volume Profile ──────────────────────────────────────────────────────────

def compute_volume_profile(candles: list[Candle], bins: int = VOLUME_PROFILE_BINS) -> dict:
    """
    Строит Volume Profile из свечей.
    Каждая свеча вносит свой объём на типичный уровень (H+L+C)/3.
    Возвращает: {poc, vah, val, histogram}
    """
    if not candles:
        return {}

    price_min = min(c.low for c in candles)
    price_max = max(c.high for c in candles)
    if price_max == price_min:
        return {}

    bin_size = (price_max - price_min) / bins
    histogram: dict[int, float] = defaultdict(float)

    for c in candles:
        typical = (c.high + c.low + c.close) / 3
        idx = int((typical - price_min) / bin_size)
        idx = min(idx, bins - 1)
        histogram[idx] += c.volume

    if not histogram:
        return {}

    # POC — уровень с максимальным объёмом
    poc_idx = max(histogram, key=histogram.get)  # type: ignore
    poc_price = price_min + (poc_idx + 0.5) * bin_size

    # Value Area (70% от суммарного объёма вокруг POC)
    total_vol = sum(histogram.values())
    target_vol = total_vol * VAH_VAL_PCT
    accumulated = histogram[poc_idx]
    lo_idx = hi_idx = poc_idx

    while accumulated < target_vol:
        can_up = hi_idx + 1 < bins and hi_idx + 1 in histogram
        can_dn = lo_idx - 1 >= 0 and lo_idx - 1 in histogram
        if not can_up and not can_dn:
            break
        up_vol = histogram.get(hi_idx + 1, 0) if can_up else 0
        dn_vol = histogram.get(lo_idx - 1, 0) if can_dn else 0
        if up_vol >= dn_vol:
            hi_idx += 1
            accumulated += up_vol
        else:
            lo_idx -= 1
            accumulated += dn_vol

    vah = price_min + (hi_idx + 1) * bin_size
    val = price_min + lo_idx * bin_size

    return {
        "poc": round(poc_price, 8),
        "vah": round(vah, 8),
        "val": round(val, 8),
        "total_volume": round(total_vol, 4),
        "histogram": {
            round(price_min + (i + 0.5) * bin_size, 2): round(v, 4)
            for i, v in sorted(histogram.items())
        },
    }


# ─── CVD ─────────────────────────────────────────────────────────────────────

class CVDTracker:
    """Отслеживает накопленную дельту объёма из потока сделок."""

    def __init__(self) -> None:
        # {symbol: float}
        self._cvd: dict[str, float] = defaultdict(float)
        self._trade_count: dict[str, int] = defaultdict(int)

    def update(self, trade: Trade) -> float:
        delta = trade.quantity if trade.side == "buy" else -trade.quantity
        self._cvd[trade.symbol] += delta
        self._trade_count[trade.symbol] += 1
        return self._cvd[trade.symbol]

    def get(self, symbol: str) -> float:
        return self._cvd[symbol]

    def reset(self, symbol: str) -> None:
        self._cvd[symbol] = 0.0


# ─── Дельта свечи (аппроксимация из OHLCV) ────────────────────────────────

def candle_delta_estimate(candle: Candle) -> float:
    """
    Аппроксимация delta buy-sell объёма по OHLCV.
    Если свеча бычья (close > open) → бо́льшая часть объёма — покупки.
    Пропорция: delta ≈ volume × (close - open) / (high - low + 1e-10)
    """
    direction = candle.close - candle.open
    price_range = candle.high - candle.low + 1e-10
    ratio = direction / price_range
    return round(candle.volume * ratio, 8)


# ─── Главный класс ───────────────────────────────────────────────────────────

class VolumeEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._cvd = CVDTracker()
        # {(symbol, timeframe): deque[Candle]}
        self._candle_buffers: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=200))

    async def start(self) -> None:
        self._bus.subscribe("trade.raw", self._on_trade)
        for tf in ALL_TIMEFRAMES:
            self._bus.subscribe(f"candle.{tf}.closed", self._on_candle)
        log.info("Volume Engine запущен")

    async def stop(self) -> None:
        log.info("Volume Engine остановлен")

    async def _on_trade(self, event: Event) -> None:
        trade: Trade = event.data
        cvd = self._cvd.update(trade)
        await self._bus.publish("volume.cvd.updated", {
            "symbol": trade.symbol,
            "cvd": round(cvd, 8),
            "last_trade_side": trade.side,
            "last_trade_qty": trade.quantity,
        })

    async def _on_candle(self, event: Event) -> None:
        candle: Candle = event.data
        key = (candle.symbol, candle.timeframe)
        self._candle_buffers[key].append(candle)
        buf = list(self._candle_buffers[key])

        # Дельта текущей свечи
        delta = candle_delta_estimate(candle)
        await self._bus.publish("volume.delta.candle", {
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "timestamp": candle.open_time,
            "delta": delta,
            "volume": candle.volume,
            "cvd_realtime": self._cvd.get(candle.symbol),
        })

        # Volume Profile (только если достаточно свечей)
        if len(buf) >= 20:
            profile = compute_volume_profile(buf[-100:])
            if profile:
                await self._bus.publish("volume.profile.updated", {
                    "symbol": candle.symbol,
                    "timeframe": candle.timeframe,
                    "timestamp": candle.open_time,
                    **{k: v for k, v in profile.items() if k != "histogram"},
                })

    def get_cvd(self, symbol: str) -> float:
        return self._cvd.get(symbol)
