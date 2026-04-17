"""
SmartMoney Engine — концепции Smart Money.

Работает с буфером свечей, публикует события:
  smc.fvg.detected   — Fair Value Gap
  smc.bos.detected   — Break of Structure
  smc.choch.detected — Change of Character
  smc.ob.identified  — Order Block
  smc.zone.updated   — Premium/Discount зона
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Literal

from core.event_bus import Event, EventBus
from core.logger import get_logger
from data.tf_aggregator import TF_MINUTES
from data.validator import Candle

log = get_logger("SmartMoney")

ALL_TIMEFRAMES = ["1m"] + list(TF_MINUTES.keys())
SWING_LOOKBACK = 5     # свечей для определения swing high/low
OB_LOOKBACK = 10       # свечей для поиска Order Block
MIN_CANDLES = 10       # минимум для работы модуля


@dataclass
class FVG:
    symbol: str
    timeframe: str
    direction: Literal["bull", "bear"]
    top: float      # верхняя граница гэпа
    bottom: float   # нижняя граница гэпа
    timestamp: int
    filled: bool = False


@dataclass
class OrderBlock:
    symbol: str
    timeframe: str
    direction: Literal["bull", "bear"]  # bull OB = последняя медвежья свеча перед ростом
    high: float
    low: float
    timestamp: int


# ─── Детекторы ───────────────────────────────────────────────────────────────

def detect_fvg(candles: list[Candle]) -> list[FVG]:
    """
    FVG (Fair Value Gap): 3 свечи.
    Бычий FVG: candle[-3].high < candle[-1].low → гэп между [-3] и [-1]
    Медвежий FVG: candle[-3].low > candle[-1].high → гэп сверху
    """
    if len(candles) < 3:
        return []
    result = []
    # Смотрим последние 3 свечи
    c1, _, c3 = candles[-3], candles[-2], candles[-1]

    if c1.high < c3.low:
        result.append(FVG(
            symbol=c3.symbol, timeframe=c3.timeframe,
            direction="bull", top=c3.low, bottom=c1.high,
            timestamp=c3.open_time,
        ))
    elif c1.low > c3.high:
        result.append(FVG(
            symbol=c3.symbol, timeframe=c3.timeframe,
            direction="bear", top=c1.low, bottom=c3.high,
            timestamp=c3.open_time,
        ))
    return result


def _swing_high(candles: list[Candle], lookback: int) -> float | None:
    """Максимальный High за последние lookback свечей (кроме последней)."""
    window = candles[-(lookback + 1):-1]
    if not window:
        return None
    return max(c.high for c in window)


def _swing_low(candles: list[Candle], lookback: int) -> float | None:
    """Минимальный Low за последние lookback свечей (кроме последней)."""
    window = candles[-(lookback + 1):-1]
    if not window:
        return None
    return min(c.low for c in window)


def detect_bos(candles: list[Candle], lookback: int = SWING_LOOKBACK) -> dict | None:
    """
    BOS (Break of Structure):
    - Цена закрытия пробивает swing high → бычий BOS
    - Цена закрытия пробивает swing low → медвежий BOS
    """
    if len(candles) < lookback + 1:
        return None

    last = candles[-1]
    sh = _swing_high(candles, lookback)
    sl = _swing_low(candles, lookback)

    if sh and last.close > sh:
        return {"direction": "bull", "level": sh, "close": last.close, "timestamp": last.open_time}
    if sl and last.close < sl:
        return {"direction": "bear", "level": sl, "close": last.close, "timestamp": last.open_time}
    return None


def detect_choch(candles: list[Candle], lookback: int = SWING_LOOKBACK) -> dict | None:
    """
    CHoCH (Change of Character): BOS в противоположную сторону предыдущего BOS.
    Смотрим последние 2*lookback свечей — если был медвежий BOS, а теперь бычий → CHoCH.
    """
    if len(candles) < lookback * 2 + 2:
        return None

    prev_half = candles[-(lookback * 2 + 1):-(lookback)]
    curr_half = candles[-(lookback + 1):]

    prev_bos = detect_bos(prev_half, lookback)
    curr_bos = detect_bos(curr_half, lookback)

    if prev_bos and curr_bos and prev_bos["direction"] != curr_bos["direction"]:
        return {
            "direction": curr_bos["direction"],
            "prev_direction": prev_bos["direction"],
            "level": curr_bos["level"],
            "timestamp": curr_bos["timestamp"],
        }
    return None


def detect_order_block(candles: list[Candle], lookback: int = OB_LOOKBACK) -> list[OrderBlock]:
    """
    Order Block: последняя свеча противоположного цвета перед значительным движением.
    Бычий OB: последняя медвежья свеча перед серией роста (следующие 3+ свечи бычьи)
    Медвежий OB: последняя бычья свеча перед серией падения
    """
    if len(candles) < lookback + 3:
        return []

    result = []
    window = candles[-lookback:]

    for i in range(len(window) - 3):
        c = window[i]
        next_3 = window[i + 1: i + 4]

        # Бычий OB: медвежья свеча + 3 бычьих после
        if c.close < c.open and all(nc.close > nc.open for nc in next_3):
            result.append(OrderBlock(
                symbol=c.symbol, timeframe=c.timeframe,
                direction="bull", high=c.high, low=c.low, timestamp=c.open_time,
            ))

        # Медвежий OB: бычья свеча + 3 медвежьих после
        elif c.close > c.open and all(nc.close < nc.open for nc in next_3):
            result.append(OrderBlock(
                symbol=c.symbol, timeframe=c.timeframe,
                direction="bear", high=c.high, low=c.low, timestamp=c.open_time,
            ))

    return result


def detect_premium_discount(candles: list[Candle], lookback: int = 20) -> dict | None:
    """
    Premium/Discount зоны: верхняя/нижняя треть диапазона.
    Premium (дорого) > 66% диапазона, Discount (дёшево) < 33%.
    """
    if len(candles) < lookback:
        return None

    window = candles[-lookback:]
    range_high = max(c.high for c in window)
    range_low = min(c.low for c in window)
    total_range = range_high - range_low

    if total_range == 0:
        return None

    last_close = candles[-1].close
    position = (last_close - range_low) / total_range  # 0..1

    zone: str
    if position > 0.66:
        zone = "premium"
    elif position < 0.33:
        zone = "discount"
    else:
        zone = "equilibrium"

    return {
        "zone": zone,
        "position": round(position, 4),
        "range_high": range_high,
        "range_low": range_low,
        "equilibrium": round((range_high + range_low) / 2, 8),
    }


# ─── Главный класс ───────────────────────────────────────────────────────────

class SmartMoneyEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._buffers: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=100))

    async def start(self) -> None:
        for tf in ALL_TIMEFRAMES:
            self._bus.subscribe(f"candle.{tf}.closed", self._on_candle)
        log.info(f"SmartMoney Engine запущен, подписан на {len(ALL_TIMEFRAMES)} таймфреймов")

    async def stop(self) -> None:
        log.info("SmartMoney Engine остановлен")

    async def _on_candle(self, event: Event) -> None:
        candle: Candle = event.data
        key = (candle.symbol, candle.timeframe)
        self._buffers[key].append(candle)
        buf = list(self._buffers[key])

        if len(buf) < MIN_CANDLES:
            return

        symbol, tf = candle.symbol, candle.timeframe
        ctx = {"symbol": symbol, "timeframe": tf}

        # ── FVG ──────────────────────────────────────────────────────────────
        for fvg in detect_fvg(buf):
            log.debug(f"FVG {fvg.direction} {symbol} {tf}: {fvg.bottom:.2f}–{fvg.top:.2f}")
            await self._bus.publish("smc.fvg.detected", {**ctx, **fvg.__dict__})

        # ── BOS ───────────────────────────────────────────────────────────────
        bos = detect_bos(buf)
        if bos:
            log.debug(f"BOS {bos['direction']} {symbol} {tf}: level={bos['level']:.2f}")
            await self._bus.publish("smc.bos.detected", {**ctx, **bos})

        # ── CHoCH ─────────────────────────────────────────────────────────────
        choch = detect_choch(buf)
        if choch:
            log.debug(f"CHoCH {choch['direction']} {symbol} {tf}")
            await self._bus.publish("smc.choch.detected", {**ctx, **choch})

        # ── Order Block ───────────────────────────────────────────────────────
        for ob in detect_order_block(buf):
            log.debug(f"OB {ob.direction} {symbol} {tf}: {ob.low:.2f}–{ob.high:.2f}")
            await self._bus.publish("smc.ob.identified", {**ctx, **ob.__dict__})

        # ── Premium/Discount ──────────────────────────────────────────────────
        pd_zone = detect_premium_discount(buf)
        if pd_zone:
            await self._bus.publish("smc.zone.updated", {**ctx, **pd_zone})
