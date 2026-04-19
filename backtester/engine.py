"""
Backtesting engine — simulates strategy execution bar-by-bar.

Design:
  - One position at a time (no pyramiding).
  - SL/TP checked against bar's high/low each candle (optimistic fill at SL/TP price).
  - Commission applied on open and close.
  - Capital compounds between trades.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from backtester.metrics import compute_metrics
from core.logger import get_logger
from strategies.base_strategy import AbstractStrategy, Signal

log = get_logger("Backtester")


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    leverage: int = 1
    commission_pct: float = 0.04   # 0.04% per side (like BingX taker)
    slippage_pct: float = 0.01     # 0.01% market slippage


@dataclass
class BacktestTrade:
    entry_time: int          # ms
    exit_time: int           # ms
    direction: Literal["long", "short"]
    entry_price: float
    exit_price: float
    size_usd: float          # position size in USD
    pnl: float               # net (after commission)
    pnl_pct: float           # % of entry capital at risk
    closed_by: Literal["signal", "sl", "tp", "end"]


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    strategy_name: str
    config: BacktestConfig
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


class BacktestEngine:
    """
    Bar-by-bar backtesting engine.

    Usage:
        engine = BacktestEngine()
        result = engine.run(strategy, candles, config, symbol="BTC/USDT", timeframe="1h")
    """

    def run(
        self,
        strategy: AbstractStrategy,
        candles: list[dict],
        config: BacktestConfig | None = None,
        symbol: str = "",
        timeframe: str = "",
        on_progress: Callable[[int, int], None] | None = None,
    ) -> BacktestResult:
        config = config or BacktestConfig()
        strategy.reset()

        result = BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy.name,
            config=config,
        )

        capital = config.initial_capital
        result.equity_curve.append(capital)

        position: _Position | None = None
        total = len(candles)
        report_every = max(1, total // 20)  # ~20 обновлений прогресса

        for idx, candle in enumerate(candles):
            if on_progress and idx % report_every == 0:
                on_progress(idx, total)
            if position is not None:
                # Check SL/TP hit on this bar
                closed = position.check_exit(candle)
                if closed:
                    trade = position.to_trade(
                        exit_price=closed["price"],
                        exit_time=candle["open_time"],
                        closed_by=closed["reason"],
                        config=config,
                    )
                    capital += trade.pnl
                    result.trades.append(trade)
                    result.equity_curve.append(capital)
                    strategy.on_close(
                        {"direction": trade.direction, "pnl": trade.pnl, "closed_by": trade.closed_by}
                    )
                    position = None

            signal: Signal | None = strategy.on_candle(candle)

            if signal is not None and position is None:
                entry_price = candle["close"] * (
                    1 + config.slippage_pct / 100
                    if signal.direction == "long"
                    else 1 - config.slippage_pct / 100
                )
                size_usd = capital * signal.size_pct * config.leverage
                position = _Position(
                    direction=signal.direction,
                    entry_price=entry_price,
                    entry_time=candle["open_time"],
                    size_usd=size_usd,
                    sl_pct=signal.sl_pct,
                    tp_pct=signal.tp_pct,
                )

        # Close any open position at end of data
        if position is not None and candles:
            last = candles[-1]
            trade = position.to_trade(
                exit_price=last["close"],
                exit_time=last["open_time"],
                closed_by="end",
                config=config,
            )
            capital += trade.pnl
            result.trades.append(trade)
            result.equity_curve.append(capital)

        result.metrics = compute_metrics(
            [{"pnl": t.pnl, "entry_time": t.entry_time, "exit_time": t.exit_time,
              "direction": t.direction} for t in result.trades],
            config.initial_capital,
        )

        log.info(
            f"Backtest {strategy.name} on {symbol}/{timeframe}: "
            f"{len(result.trades)} сделок, PnL={result.metrics.get('total_pnl_pct', 0):.2f}%"
        )
        return result


class _Position:
    """Internal position state during backtest."""

    def __init__(
        self,
        direction: str,
        entry_price: float,
        entry_time: int,
        size_usd: float,
        sl_pct: float,
        tp_pct: float,
    ) -> None:
        self.direction = direction
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.size_usd = size_usd

        if direction == "long":
            self.sl_price = entry_price * (1 - sl_pct)
            self.tp_price = entry_price * (1 + tp_pct)
        else:
            self.sl_price = entry_price * (1 + sl_pct)
            self.tp_price = entry_price * (1 - tp_pct)

    def check_exit(self, candle: dict) -> dict | None:
        """Returns exit info if SL or TP is hit on this candle, else None."""
        low = candle["low"]
        high = candle["high"]

        if self.direction == "long":
            if low <= self.sl_price:
                return {"price": self.sl_price, "reason": "sl"}
            if high >= self.tp_price:
                return {"price": self.tp_price, "reason": "tp"}
        else:
            if high >= self.sl_price:
                return {"price": self.sl_price, "reason": "sl"}
            if low <= self.tp_price:
                return {"price": self.tp_price, "reason": "tp"}
        return None

    def to_trade(
        self, exit_price: float, exit_time: int, closed_by: str, config: BacktestConfig
    ) -> BacktestTrade:
        if self.direction == "long":
            gross_pnl = (exit_price - self.entry_price) / self.entry_price * self.size_usd
        else:
            gross_pnl = (self.entry_price - exit_price) / self.entry_price * self.size_usd

        commission = self.size_usd * config.commission_pct / 100 * 2  # open + close
        net_pnl = gross_pnl - commission

        return BacktestTrade(
            entry_time=self.entry_time,
            exit_time=exit_time,
            direction=self.direction,
            entry_price=self.entry_price,
            exit_price=exit_price,
            size_usd=self.size_usd,
            pnl=net_pnl,
            pnl_pct=net_pnl / config.initial_capital * 100,
            closed_by=closed_by,
        )
