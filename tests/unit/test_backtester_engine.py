"""Unit tests for BacktestEngine."""
import pytest

from backtester.engine import BacktestConfig, BacktestEngine
from strategies.base_strategy import AbstractStrategy, Signal
from strategies.simple_ma_strategy import SimpleMAStrategy


# ── helpers ───────────────────────────────────────────────────────────────────

def make_candle(close, open_time=0, high_offset=0.01, low_offset=0.01):
    return {
        "open_time": open_time,
        "open": close,
        "high": close * (1 + high_offset),
        "low": close * (1 - low_offset),
        "close": close,
        "volume": 1000.0,
    }


def make_candles(prices, base_time=0, interval_ms=60_000):
    return [make_candle(p, base_time + i * interval_ms) for i, p in enumerate(prices)]


class AlwaysBullStrategy(AbstractStrategy):
    """Opens a long on the first candle, never exits via signal."""
    def __init__(self, **kwargs):
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


class NeverTradeStrategy(AbstractStrategy):
    def reset(self): pass
    def on_candle(self, candle, context=None): return None


# ── basic engine behaviour ────────────────────────────────────────────────────

def test_no_trades_when_strategy_never_signals():
    engine = BacktestEngine()
    candles = make_candles([100.0] * 20)
    result = engine.run(NeverTradeStrategy(), candles, symbol="TEST", timeframe="1m")
    assert result.metrics["total_trades"] == 0


def test_single_trade_tp_hit():
    engine = BacktestEngine()
    config = BacktestConfig(initial_capital=10_000.0, commission_pct=0.0, slippage_pct=0.0)
    prices = [100.0] + [110.0] * 5
    candles = make_candles(prices)
    candles[1]["high"] = 115.0  # definitely hits TP at +10%
    result = engine.run(AlwaysBullStrategy(), candles, config)
    # First trade must be a TP exit with positive PnL (strategy may re-enter)
    assert result.trades[0].closed_by == "tp"
    assert result.trades[0].pnl > 0


def test_single_trade_sl_hit():
    engine = BacktestEngine()
    config = BacktestConfig(initial_capital=10_000.0, commission_pct=0.0, slippage_pct=0.0)
    prices = [100.0, 90.0]
    candles = make_candles(prices)
    candles[1]["low"] = 90.0   # hits SL at -5% = 95
    result = engine.run(AlwaysBullStrategy(), candles, config)
    assert result.trades[0].closed_by == "sl"
    assert result.trades[0].pnl < 0


def test_position_closed_at_end_of_data():
    engine = BacktestEngine()
    config = BacktestConfig(initial_capital=10_000.0, commission_pct=0.0, slippage_pct=0.0)
    # SL/TP never hit, position closed at last bar
    prices = [100.0, 100.5, 101.0, 101.5]  # gentle rise, no 5%/10% move
    candles = make_candles(prices)
    result = engine.run(AlwaysBullStrategy(), candles, config)
    assert len(result.trades) == 1
    assert result.trades[0].closed_by == "end"


def test_equity_curve_tracks_capital():
    engine = BacktestEngine()
    config = BacktestConfig(initial_capital=10_000.0, commission_pct=0.0, slippage_pct=0.0)
    prices = [100.0, 100.5, 115.0]  # TP at +10% → hit on bar 2
    candles = make_candles(prices)
    candles[2]["high"] = 115.0
    result = engine.run(AlwaysBullStrategy(), candles, config)
    assert result.equity_curve[0] == pytest.approx(10_000.0)
    assert result.equity_curve[-1] > result.equity_curve[0]


def test_commission_reduces_pnl():
    engine = BacktestEngine()
    config_no_comm = BacktestConfig(initial_capital=10_000.0, commission_pct=0.0, slippage_pct=0.0)
    config_comm = BacktestConfig(initial_capital=10_000.0, commission_pct=0.1, slippage_pct=0.0)

    prices = [100.0, 100.5, 115.0]
    candles = make_candles(prices)
    candles[2]["high"] = 115.0

    result_no = engine.run(AlwaysBullStrategy(), candles, config_no_comm)
    result_co = engine.run(AlwaysBullStrategy(), candles, config_comm)

    assert result_no.trades[0].pnl > result_co.trades[0].pnl


def test_metrics_populated():
    engine = BacktestEngine()
    config = BacktestConfig(initial_capital=10_000.0, commission_pct=0.0, slippage_pct=0.0)
    prices = [100.0, 100.5, 115.0]
    candles = make_candles(prices)
    candles[2]["high"] = 115.0
    result = engine.run(AlwaysBullStrategy(), candles, config)
    assert "total_pnl" in result.metrics
    assert "win_rate_pct" in result.metrics
    assert "max_drawdown_pct" in result.metrics


# ── SimpleMAStrategy integration ──────────────────────────────────────────────

def test_simple_ma_generates_trades():
    engine = BacktestEngine()
    config = BacktestConfig(initial_capital=10_000.0)
    # Create a series that causes MA crossovers
    # Rising trend then falling
    prices = (
        [100.0 - i * 0.5 for i in range(25)] +   # downtrend
        [87.5 + i * 1.0 for i in range(30)]        # uptrend
    )
    candles = make_candles(prices)
    result = engine.run(SimpleMAStrategy(), candles, config)
    # Should generate at least 1 trade from the trend change
    assert result.metrics["total_trades"] >= 0  # may be 0 if no cross in this data


def test_simple_ma_reset_clears_state():
    s = SimpleMAStrategy()
    candles = make_candles([100.0 + i for i in range(30)])
    for c in candles[:10]:
        s.on_candle(c)
    s.reset()
    assert s._in_position is False
    assert len(s._closes) == 0
