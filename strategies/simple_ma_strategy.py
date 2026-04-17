"""
Simple Moving Average Crossover strategy — example / test strategy.

Long when fast MA crosses above slow MA.
Short when fast MA crosses below slow MA.
"""
from __future__ import annotations

from collections import deque

from strategies.base_strategy import AbstractStrategy, Signal


class SimpleMAStrategy(AbstractStrategy):
    """
    Params:
        fast_period: int (default 5)
        slow_period: int (default 20)
        sl_pct: float (default 0.02)
        tp_pct: float (default 0.04)
    """

    def __init__(self, params: dict | None = None) -> None:
        defaults = {"fast_period": 5, "slow_period": 20, "sl_pct": 0.02, "tp_pct": 0.04}
        if params:
            defaults.update(params)
        super().__init__(defaults)
        self._closes: deque[float] = deque()
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None
        self._in_position: bool = False

    def reset(self) -> None:
        self._closes.clear()
        self._prev_fast = None
        self._prev_slow = None
        self._in_position = False

    def on_candle(self, candle: dict, context: dict | None = None) -> Signal | None:
        fast = self._params["fast_period"]
        slow = self._params["slow_period"]

        self._closes.append(candle["close"])
        # Keep only what we need
        if len(self._closes) > slow + 1:
            self._closes.popleft()

        if len(self._closes) < slow:
            return None

        closes = list(self._closes)
        fast_ma = sum(closes[-fast:]) / fast
        slow_ma = sum(closes[-slow:]) / slow

        signal = None

        if self._prev_fast is not None and self._prev_slow is not None:
            bull_cross = self._prev_fast <= self._prev_slow and fast_ma > slow_ma
            bear_cross = self._prev_fast >= self._prev_slow and fast_ma < slow_ma

            if bull_cross and not self._in_position:
                self._in_position = True
                signal = Signal(
                    direction="long",
                    sl_pct=self._params["sl_pct"],
                    tp_pct=self._params["tp_pct"],
                )
            elif bear_cross and not self._in_position:
                self._in_position = True
                signal = Signal(
                    direction="short",
                    sl_pct=self._params["sl_pct"],
                    tp_pct=self._params["tp_pct"],
                )

        self._prev_fast = fast_ma
        self._prev_slow = slow_ma
        return signal

    def on_close(self, trade: dict) -> None:
        self._in_position = False
