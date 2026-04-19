"""
MTF Confluence Strategy — бэктестируемая версия.

Симулирует многотаймфреймный анализ на одном ряде свечей:
  - Короткий горизонт:  EMA(9) vs EMA(21)
  - Средний горизонт:   EMA(20) vs EMA(50), RSI(14), MACD(12/26)
  - Длинный горизонт:   EMA(50) vs EMA(100)
  - Объём:              превышение над скользящим средним

Каждый сигнал голосует ±1. Итоговый score нормализуется [0..100].
Signal при score ≥ min_score (лонг) или ≤ (100 - min_score) (шорт).
"""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from strategies.base_strategy import AbstractStrategy, Signal

if TYPE_CHECKING:
    pass


def _ema(prices: list[float], period: int) -> float:
    if len(prices) < period:
        return sum(prices) / len(prices)
    k = 2.0 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val


def _rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


class MTFConfluenceStrategy(AbstractStrategy):
    """
    Параметры (dict):
      min_score  — порог генерации сигнала, по умолчанию 60 (из 100)
      sl_pct     — доля стоп-лосса, по умолчанию 0.02 (2%)
      tp_pct     — доля тейк-профита, по умолчанию 0.04 (4%)
    """

    def __init__(self, params: dict | None = None) -> None:
        super().__init__(params)
        self._buf: deque[dict] = deque(maxlen=210)
        self._in_position = False

    @property
    def name(self) -> str:
        return "MTF Confluence"

    def reset(self) -> None:
        self._buf.clear()
        self._in_position = False

    def on_close(self, trade: dict) -> None:
        self._in_position = False

    def on_candle(self, candle: dict, context: dict | None = None) -> Signal | None:
        self._buf.append(candle)
        if len(self._buf) < 105 or self._in_position:
            return None

        closes  = [c["close"]  for c in self._buf]
        volumes = [c["volume"] for c in self._buf]

        votes: list[float] = []

        # ── Короткий горизонт: EMA(9) vs EMA(21) ─────────────────────────────
        if len(closes) >= 21:
            e9  = _ema(closes, 9)
            e21 = _ema(closes, 21)
            votes.append(1.0 if e9 > e21 else -1.0)

        # ── Средний горизонт: EMA(20) vs EMA(50) ─────────────────────────────
        if len(closes) >= 50:
            e20 = _ema(closes, 20)
            e50 = _ema(closes, 50)
            votes.append(1.0 if e20 > e50 else -1.0)

        # ── Длинный горизонт: EMA(50) vs EMA(100) ────────────────────────────
        if len(closes) >= 100:
            e50  = _ema(closes, 50)
            e100 = _ema(closes, 100)
            votes.append(1.0 if e50 > e100 else -1.0)

        # ── RSI(14) — перекупленность / перепроданность ───────────────────────
        rsi = _rsi(closes, 14)
        if rsi is not None:
            if rsi < 35:
                votes.append(1.0)
            elif rsi > 65:
                votes.append(-1.0)
            else:
                votes.append((rsi - 50.0) / 50.0 * 0.5)

        # ── MACD = EMA(12) − EMA(26) ──────────────────────────────────────────
        if len(closes) >= 27:
            macd_cur  = _ema(closes,      12) - _ema(closes,      26)
            macd_prev = _ema(closes[:-1], 12) - _ema(closes[:-1], 26)
            if macd_cur > 0 and macd_cur > macd_prev:
                votes.append(1.0)
            elif macd_cur < 0 and macd_cur < macd_prev:
                votes.append(-1.0)
            else:
                votes.append(0.5 if macd_cur > 0 else -0.5)

        # ── Объём: подтверждает направление движения цены ────────────────────
        if len(volumes) >= 20:
            vol_ma = sum(volumes[-20:]) / 20
            if volumes[-1] > vol_ma * 1.2:
                direction = closes[-1] - closes[-2]
                votes.append(0.5 if direction > 0 else -0.5)

        if not votes:
            return None

        raw = sum(votes) / len(votes)          # [-1, 1]
        score = (raw + 1.0) / 2.0 * 100.0     # [0, 100]

        min_score = float(self._params.get("min_score", 60))
        sl_pct    = float(self._params.get("sl_pct",    0.02))
        tp_pct    = float(self._params.get("tp_pct",    0.04))

        if score >= min_score:
            self._in_position = True
            return Signal(direction="long",  sl_pct=sl_pct, tp_pct=tp_pct)
        if score <= (100.0 - min_score):
            self._in_position = True
            return Signal(direction="short", sl_pct=sl_pct, tp_pct=tp_pct)
        return None
