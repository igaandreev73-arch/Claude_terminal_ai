"""
TA Engine — технический анализ.

Подписывается на candle.{tf}.closed для всех таймфреймов.
Поддерживает скользящий буфер свечей per (symbol, timeframe).
Считает все индикаторы и публикует ta.{symbol}.{tf}.updated.

Промежуточные значения (raw RSI, ema_fast/slow) также включаются в результат
для записи в ml_dataset.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import pandas as pd

from core.event_bus import Event, EventBus
from core.logger import get_logger
from data.tf_aggregator import TF_MINUTES
from data.validator import Candle

log = get_logger("TAEngine")

# Буфер: достаточно для EMA-200 + запас
BUFFER_SIZE = 250

# Все подписываемые таймфреймы
ALL_TIMEFRAMES = ["1m"] + list(TF_MINUTES.keys())


# ─── Вспомогательные вычисления ─────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> dict[str, pd.Series]:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    # avg_loss=0 → RSI=100 (все свечи растут), avg_gain=0 → RSI=0
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.where(avg_loss > 0, 100.0)
    rsi = rsi.where(avg_gain > 0, 0.0)
    return {"rsi": rsi, "avg_gain": avg_gain, "avg_loss": avg_loss}


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pd.Series]:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return {
        "macd_line": macd_line,
        "macd_signal": signal_line,
        "macd_hist": histogram,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
    }


def _bollinger(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> dict[str, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    width = (upper - lower) / mid.replace(0, float("nan"))
    # Позиция цены внутри BB (0 = нижняя граница, 1 = верхняя)
    bb_pos = (close - lower) / (upper - lower).replace(0, float("nan"))
    return {"bb_mid": mid, "bb_upper": upper, "bb_lower": lower, "bb_width": width, "bb_pos": bb_pos}


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> dict[str, pd.Series]:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(com=period - 1, min_periods=period).mean()
    return {"atr": atr, "true_range": tr}


def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                k_period: int = 14, d_period: int = 3) -> dict[str, pd.Series]:
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    denom = (highest_high - lowest_low).replace(0, float("nan"))
    k = 100 * (close - lowest_low) / denom
    d = k.rolling(d_period).mean()
    return {"stoch_k": k, "stoch_d": d}


def _vwap(df: pd.DataFrame) -> pd.Series:
    """Внутридневной VWAP — сбрасывается в начале каждого дня (по open_time)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    # Группируем по дате (день по open_time в мс)
    df = df.copy()
    df["_day"] = (df["open_time"] // 86_400_000)
    df["_tp_vol"] = typical * df["volume"]
    cumtp = df.groupby("_day")["_tp_vol"].cumsum()
    cumvol = df.groupby("_day")["volume"].cumsum()
    return cumtp / cumvol.replace(0, float("nan"))


def _pivot_points(high: float, low: float, close: float) -> dict[str, float]:
    pivot = (high + low + close) / 3
    return {
        "pivot": round(pivot, 8),
        "r1": round(2 * pivot - low, 8),
        "s1": round(2 * pivot - high, 8),
        "r2": round(pivot + (high - low), 8),
        "s2": round(pivot - (high - low), 8),
    }


def _support_resistance(close: pd.Series, window: int = 20) -> dict[str, float | None]:
    if len(close) < window * 2:
        return {"resistance": None, "support": None}
    recent = close.tail(window * 2)
    return {
        "resistance": float(recent.max()),
        "support": float(recent.min()),
    }


# ─── Детектор паттернов свечей ───────────────────────────────────────────────

def _candle_patterns(o: float, h: float, l: float, c: float) -> dict[str, bool]:
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    full_range = h - l or 1e-10

    is_bullish = c > o
    is_bearish = c < o

    # Молот / повешенный: маленькое тело, большая нижняя тень (≥ 2× тело), маленькая верхняя тень
    hammer = (body / full_range < 0.35) and (lower_wick >= 2 * body) and (upper_wick <= body)

    # Доджи: тело < 5% от диапазона
    doji = body / full_range < 0.05

    # Пин-бар бычий: нижняя тень > 2/3 диапазона
    pin_bar_bull = (lower_wick / full_range > 0.66) and is_bullish
    # Пин-бар медвежий: верхняя тень > 2/3 диапазона
    pin_bar_bear = (upper_wick / full_range > 0.66) and is_bearish

    return {
        "hammer": hammer,
        "doji": doji,
        "pin_bar_bull": pin_bar_bull,
        "pin_bar_bear": pin_bar_bear,
    }


def _engulfing(prev_o: float, prev_c: float, curr_o: float, curr_c: float) -> dict[str, bool]:
    bull_engulf = (prev_c < prev_o) and (curr_c > curr_o) and (curr_o <= prev_c) and (curr_c >= prev_o)
    bear_engulf = (prev_c > prev_o) and (curr_c < curr_o) and (curr_o >= prev_c) and (curr_c <= prev_o)
    return {"bull_engulfing": bull_engulf, "bear_engulfing": bear_engulf}


# ─── Главный класс ───────────────────────────────────────────────────────────

def _v(series: pd.Series) -> float | None:
    """Безопасно берёт последнее значение Series, возвращает None если NaN."""
    val = series.iloc[-1] if len(series) > 0 else float("nan")
    if pd.isna(val):
        return None
    return round(float(val), 8)


class TAEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        # {(symbol, timeframe): deque[Candle]}
        self._buffers: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=BUFFER_SIZE))

    async def start(self) -> None:
        for tf in ALL_TIMEFRAMES:
            self._bus.subscribe(f"candle.{tf}.closed", self._on_candle)
        log.info(f"TA Engine запущен, подписан на {len(ALL_TIMEFRAMES)} таймфреймов")

    async def stop(self) -> None:
        log.info("TA Engine остановлен")

    async def _on_candle(self, event: Event) -> None:
        candle: Candle = event.data
        key = (candle.symbol, candle.timeframe)
        self._buffers[key].append(candle)

        result = self._calculate(key)
        if result:
            await self._bus.publish(f"ta.{candle.symbol}.{candle.timeframe}.updated", result)

    def _calculate(self, key: tuple[str, str]) -> dict[str, Any] | None:
        buf = list(self._buffers[key])
        if len(buf) < 2:
            return None

        symbol, tf = key
        df = pd.DataFrame([{
            "open_time": c.open_time,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        } for c in buf])

        n = len(df)
        close = df["close"]
        high = df["high"]
        low = df["low"]

        result: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": tf,
            "timestamp": buf[-1].open_time,
            "close": float(close.iloc[-1]),
        }

        # ── EMA ──────────────────────────────────────────────────────────────
        for period in (9, 21, 50, 200):
            if n >= period:
                result[f"ema_{period}"] = _v(_ema(close, period))

        # ── RSI ──────────────────────────────────────────────────────────────
        if n >= 15:
            rsi_data = _rsi(close)
            result["rsi_14"] = _v(rsi_data["rsi"])
            result["rsi_avg_gain"] = _v(rsi_data["avg_gain"])
            result["rsi_avg_loss"] = _v(rsi_data["avg_loss"])

        # ── MACD ─────────────────────────────────────────────────────────────
        if n >= 27:
            macd_data = _macd(close)
            result["macd_line"] = _v(macd_data["macd_line"])
            result["macd_signal"] = _v(macd_data["macd_signal"])
            result["macd_hist"] = _v(macd_data["macd_hist"])
            result["ema_fast_12"] = _v(macd_data["ema_fast"])
            result["ema_slow_26"] = _v(macd_data["ema_slow"])

        # ── Bollinger Bands ───────────────────────────────────────────────────
        if n >= 20:
            bb = _bollinger(close)
            result["bb_mid"] = _v(bb["bb_mid"])
            result["bb_upper"] = _v(bb["bb_upper"])
            result["bb_lower"] = _v(bb["bb_lower"])
            result["bb_width"] = _v(bb["bb_width"])
            result["bb_pos"] = _v(bb["bb_pos"])

        # ── ATR ───────────────────────────────────────────────────────────────
        if n >= 15:
            atr_data = _atr(high, low, close)
            result["atr_14"] = _v(atr_data["atr"])
            result["true_range"] = _v(atr_data["true_range"])

        # ── Stochastic ────────────────────────────────────────────────────────
        if n >= 14:
            stoch = _stochastic(high, low, close)
            result["stoch_k"] = _v(stoch["stoch_k"])
            result["stoch_d"] = _v(stoch["stoch_d"])

        # ── VWAP ──────────────────────────────────────────────────────────────
        vwap_series = _vwap(df)
        result["vwap"] = _v(vwap_series)

        # ── Уровни ────────────────────────────────────────────────────────────
        sr = _support_resistance(close)
        result["resistance"] = sr["resistance"]
        result["support"] = sr["support"]

        last = df.iloc[-1]
        pivots = _pivot_points(float(last["high"]), float(last["low"]), float(last["close"]))
        result.update(pivots)

        # ── Паттерны свечей ────────────────────────────────────────────────────
        last_c = buf[-1]
        patterns = _candle_patterns(last_c.open, last_c.high, last_c.low, last_c.close)
        result.update(patterns)

        if len(buf) >= 2:
            prev_c = buf[-2]
            engulf = _engulfing(prev_c.open, prev_c.close, last_c.open, last_c.close)
            result.update(engulf)

        return result

    def get_latest(self, symbol: str, timeframe: str) -> dict[str, Any] | None:
        """Синхронно возвращает последний рассчитанный результат (для тестов/AI)."""
        key = (symbol, timeframe)
        if key not in self._buffers or len(self._buffers[key]) < 2:
            return None
        return self._calculate(key)
