"""Unit tests for DemoMode (paper trading)."""
import asyncio
import pytest

from backtester.demo_mode import DemoMode
from backtester.engine import BacktestConfig
from core.event_bus import Event, EventBus
from strategies.base_strategy import AbstractStrategy, Signal
from strategies.simple_ma_strategy import SimpleMAStrategy


class ImmediateLongStrategy(AbstractStrategy):
    """Opens a long on first candle, stays in."""
    def __init__(self):
        super().__init__()
        self._opened = False

    def reset(self):
        self._opened = False

    def on_candle(self, candle, context=None):
        if not self._opened:
            self._opened = True
            return Signal(direction="long", sl_pct=0.05, tp_pct=0.10)
        return None

    def on_close(self, trade):
        self._opened = False


def make_candle_event(close, open_time=0, tf="1h"):
    candle = {
        "open_time": open_time,
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1000.0,
    }
    return Event(f"candle.{tf}.closed", candle)


@pytest.mark.asyncio
async def test_demo_mode_opens_position():
    bus = EventBus()
    await bus.start()

    strategy = ImmediateLongStrategy()
    demo = DemoMode(bus, strategy, timeframe="1h", config=BacktestConfig(initial_capital=1000.0))
    await demo.start()

    opened = []
    bus.subscribe("demo.trade.opened", lambda e: opened.append(e.data))

    await demo._on_candle(make_candle_event(100.0, 0))
    await asyncio.sleep(0.05)

    assert len(opened) == 1
    assert opened[0]["direction"] == "long"
    await bus.stop()


@pytest.mark.asyncio
async def test_demo_mode_tp_closes_position():
    bus = EventBus()
    await bus.start()

    strategy = ImmediateLongStrategy()
    config = BacktestConfig(initial_capital=1000.0, commission_pct=0.0, slippage_pct=0.0)
    demo = DemoMode(bus, strategy, timeframe="1h", config=config)
    await demo.start()

    closed = []
    bus.subscribe("demo.trade.closed", lambda e: closed.append(e.data))

    # Open at 100
    await demo._on_candle(make_candle_event(100.0, 0))
    # TP at +10% = 110; set high=115 to trigger TP
    candle_tp = {
        "open_time": 3_600_000, "open": 105.0, "high": 115.0, "low": 102.0,
        "close": 110.0, "volume": 1000.0,
    }
    await demo._on_candle(Event("candle.1h.closed", candle_tp))
    await asyncio.sleep(0.05)

    assert len(closed) == 1
    assert closed[0]["closed_by"] == "tp"
    assert closed[0]["pnl"] > 0
    await bus.stop()


@pytest.mark.asyncio
async def test_demo_mode_sl_closes_position():
    bus = EventBus()
    await bus.start()

    strategy = ImmediateLongStrategy()
    config = BacktestConfig(initial_capital=1000.0, commission_pct=0.0, slippage_pct=0.0)
    demo = DemoMode(bus, strategy, timeframe="1h", config=config)
    await demo.start()

    closed = []
    bus.subscribe("demo.trade.closed", lambda e: closed.append(e.data))

    await demo._on_candle(make_candle_event(100.0, 0))
    # SL at -5% = 95; set low=90 to trigger SL
    candle_sl = {
        "open_time": 3_600_000, "open": 98.0, "high": 99.0, "low": 90.0,
        "close": 93.0, "volume": 1000.0,
    }
    await demo._on_candle(Event("candle.1h.closed", candle_sl))
    await asyncio.sleep(0.05)

    assert len(closed) == 1
    assert closed[0]["closed_by"] == "sl"
    assert closed[0]["pnl"] < 0
    await bus.stop()


@pytest.mark.asyncio
async def test_demo_mode_stats_published_after_close():
    bus = EventBus()
    await bus.start()

    strategy = ImmediateLongStrategy()
    config = BacktestConfig(initial_capital=1000.0, commission_pct=0.0, slippage_pct=0.0)
    demo = DemoMode(bus, strategy, timeframe="1h", config=config)
    await demo.start()

    stats = []
    bus.subscribe("demo.stats.updated", lambda e: stats.append(e.data))

    await demo._on_candle(make_candle_event(100.0, 0))
    candle_tp = {
        "open_time": 3_600_000, "open": 105.0, "high": 115.0, "low": 102.0,
        "close": 110.0, "volume": 1000.0,
    }
    await demo._on_candle(Event("candle.1h.closed", candle_tp))
    await asyncio.sleep(0.05)

    assert len(stats) >= 1
    assert "total_trades" in stats[0]
    assert "capital" in stats[0]
    await bus.stop()


@pytest.mark.asyncio
async def test_demo_mode_get_stats_sync():
    bus = EventBus()
    strategy = ImmediateLongStrategy()
    demo = DemoMode(bus, strategy, timeframe="1h")
    stats = demo.get_stats()
    assert stats["total_trades"] == 0
    assert stats["capital"] > 0
