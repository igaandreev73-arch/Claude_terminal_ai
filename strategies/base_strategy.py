"""
Abstract base for all trading strategies.

Each strategy receives candles one-by-one and returns a Signal or None.
The engine calls on_candle() for each bar and handles position management.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Signal:
    direction: Literal["long", "short"]
    size_pct: float = 1.0        # fraction of available capital (0..1]
    sl_pct: float = 0.02         # stop-loss % from entry price
    tp_pct: float = 0.04         # take-profit % from entry price
    confidence: float = 1.0      # 0..1, for scoring


class AbstractStrategy(ABC):
    """
    Contract every strategy must satisfy.

    params: dict of named parameters (used by optimizer for grid search).
    on_candle: called bar-by-bar with OHLCV dict + optional indicators dict.
               Return Signal to open/maintain a trade, None to stay flat.
    on_close: called when a trade is closed by the engine (SL/TP/end-of-data).
    """

    def __init__(self, params: dict | None = None) -> None:
        self._params: dict = params or {}

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def params(self) -> dict:
        return dict(self._params)

    @params.setter
    def params(self, values: dict) -> None:
        self._params.update(values)

    @abstractmethod
    def on_candle(self, candle: dict, context: dict | None = None) -> Signal | None:
        """
        candle: {open, high, low, close, volume, open_time}
        context: optional indicators / analytics data
        Return Signal to enter, None to stay flat / hold current position.
        """

    def on_close(self, trade: dict) -> None:
        """Called when the engine closes a position. Override for stateful strategies."""

    def reset(self) -> None:
        """Reset internal state (called before each backtest run)."""
