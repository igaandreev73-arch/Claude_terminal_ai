"""
Demo Mode (Paper Trading) — runs a strategy on live market data without real execution.

Subscribes to candle events, feeds them to the strategy, and simulates
position management exactly as the BacktestEngine does — but in real-time.

Publishes:
  demo.trade.opened   — paper position opened
  demo.trade.closed   — paper position closed (with PnL)
  demo.stats.updated  — running performance stats
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backtester.engine import BacktestConfig, _Position
from backtester.metrics import compute_metrics
from core.event_bus import Event, EventBus
from core.logger import get_logger
from strategies.base_strategy import AbstractStrategy

log = get_logger("DemoMode")


class DemoMode:
    """
    Paper trading engine driven by live candle events.

    Usage:
        demo = DemoMode(event_bus, strategy, timeframe="1h")
        await demo.start()
    """

    def __init__(
        self,
        event_bus: EventBus,
        strategy: AbstractStrategy,
        timeframe: str = "1h",
        config: BacktestConfig | None = None,
    ) -> None:
        self._bus = event_bus
        self._strategy = strategy
        self._tf = timeframe
        self._config = config or BacktestConfig()

        self._capital = self._config.initial_capital
        self._position: _Position | None = None
        self._trades: list[dict] = []
        self._trade_counter = 0

    async def start(self) -> None:
        self._bus.subscribe(f"candle.{self._tf}.closed", self._on_candle)
        log.info(
            f"Demo Mode запущен: {self._strategy.name} на {self._tf}, "
            f"капитал={self._capital:.2f}"
        )

    async def stop(self) -> None:
        log.info(f"Demo Mode остановлен. Сделок: {len(self._trades)}")

    async def _on_candle(self, event: Event) -> None:
        candle = event.data
        if hasattr(candle, "__dict__"):
            candle = candle.__dict__

        # Check exits first
        if self._position is not None:
            exit_info = self._position.check_exit(candle)
            if exit_info:
                await self._close_position(candle, exit_info["price"], exit_info["reason"])

        # Ask strategy for signal
        signal = self._strategy.on_candle(candle)

        if signal is not None and self._position is None:
            entry_price = candle["close"] * (
                1 + self._config.slippage_pct / 100
                if signal.direction == "long"
                else 1 - self._config.slippage_pct / 100
            )
            size_usd = self._capital * signal.size_pct * self._config.leverage
            self._position = _Position(
                direction=signal.direction,
                entry_price=entry_price,
                entry_time=candle["open_time"],
                size_usd=size_usd,
                sl_pct=signal.sl_pct,
                tp_pct=signal.tp_pct,
            )
            self._trade_counter += 1
            trade_id = f"demo_{self._trade_counter}"

            log.info(
                f"[Demo] Открыта {signal.direction.upper()} позиция "
                f"@ {entry_price:.4f}, size={size_usd:.2f}"
            )
            await self._bus.publish("demo.trade.opened", {
                "trade_id": trade_id,
                "direction": signal.direction,
                "entry_price": entry_price,
                "size_usd": size_usd,
                "sl_price": self._position.sl_price,
                "tp_price": self._position.tp_price,
                "strategy": self._strategy.name,
                "timeframe": self._tf,
            })

    async def _close_position(self, candle: dict, exit_price: float, reason: str) -> None:
        assert self._position is not None

        trade = self._position.to_trade(
            exit_price=exit_price,
            exit_time=candle["open_time"],
            closed_by=reason,
            config=self._config,
        )
        self._capital += trade.pnl
        self._strategy.on_close({
            "direction": trade.direction, "pnl": trade.pnl, "closed_by": reason
        })

        trade_dict = {
            "trade_id": f"demo_{self._trade_counter}",
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "size_usd": trade.size_usd,
            "pnl": trade.pnl,
            "pnl_pct": trade.pnl_pct,
            "closed_by": reason,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
        }
        self._trades.append(trade_dict)
        self._position = None

        log.info(
            f"[Demo] Закрыта позиция ({reason}): PnL={trade.pnl:.4f} "
            f"({trade.pnl_pct:.2f}%), капитал={self._capital:.2f}"
        )

        await self._bus.publish("demo.trade.closed", trade_dict)
        await self._publish_stats()

    async def _publish_stats(self) -> None:
        metrics = compute_metrics(self._trades, self._config.initial_capital)
        await self._bus.publish("demo.stats.updated", {
            "strategy": self._strategy.name,
            "timeframe": self._tf,
            "capital": round(self._capital, 2),
            **metrics,
        })

    def get_stats(self) -> dict:
        """Synchronously returns current demo stats."""
        metrics = compute_metrics(self._trades, self._config.initial_capital)
        return {
            "strategy": self._strategy.name,
            "capital": round(self._capital, 2),
            "open_position": self._position is not None,
            **metrics,
        }
