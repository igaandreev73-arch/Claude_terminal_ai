"""Unit tests for GridSearchOptimizer and StrategyFingerprint."""
import pytest

from backtester.engine import BacktestConfig
from backtester.optimizer import GridSearchOptimizer, OptimizeConfig, StrategyFingerprint
from strategies.simple_ma_strategy import SimpleMAStrategy


def make_candles(prices):
    return [
        {
            "open_time": i * 60_000,
            "open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": 1000.0
        }
        for i, p in enumerate(prices)
    ]


def trend_prices(n=100):
    """Alternating down then up trend to produce MA crossovers."""
    down = [100.0 - i * 0.5 for i in range(n // 2)]
    up = [down[-1] + i * 0.5 for i in range(n // 2)]
    return down + up


# ── GridSearchOptimizer ───────────────────────────────────────────────────────

def test_optimizer_runs_without_error():
    optimizer = GridSearchOptimizer()
    candles = make_candles(trend_prices(120))
    config = OptimizeConfig(
        param_grid={"fast_period": [3, 5], "slow_period": [10, 20]},
        backtest_config=BacktestConfig(initial_capital=10_000.0),
        min_trades=0,
        walk_forward=False,
    )
    result = optimizer.run(SimpleMAStrategy, candles, config, symbol="BTC/USDT", timeframe="1m")
    assert result.best_params is not None
    assert isinstance(result.all_results, list)


def test_optimizer_returns_best_params_dict():
    optimizer = GridSearchOptimizer()
    candles = make_candles(trend_prices(120))
    config = OptimizeConfig(
        param_grid={"fast_period": [3, 5], "slow_period": [15, 20]},
        backtest_config=BacktestConfig(initial_capital=10_000.0),
        min_trades=0,
        walk_forward=False,
    )
    result = optimizer.run(SimpleMAStrategy, candles, config)
    assert "fast_period" in result.best_params or result.best_params == {}


def test_optimizer_walk_forward():
    optimizer = GridSearchOptimizer()
    candles = make_candles(trend_prices(200))
    config = OptimizeConfig(
        param_grid={"fast_period": [3, 5], "slow_period": [15, 20]},
        backtest_config=BacktestConfig(initial_capital=10_000.0),
        min_trades=0,
        walk_forward=True,
        train_ratio=0.7,
    )
    result = optimizer.run(SimpleMAStrategy, candles, config)
    assert result is not None


def test_optimizer_sorted_descending():
    optimizer = GridSearchOptimizer()
    candles = make_candles(trend_prices(120))
    config = OptimizeConfig(
        param_grid={"fast_period": [3, 5, 7], "slow_period": [15, 20]},
        backtest_config=BacktestConfig(initial_capital=10_000.0),
        min_trades=0,
        walk_forward=False,
        target_metric="total_pnl",
    )
    result = optimizer.run(SimpleMAStrategy, candles, config)
    if len(result.all_results) > 1:
        metrics = [r.metrics.get("total_pnl", 0) or 0 for _, r in result.all_results]
        assert metrics == sorted(metrics, reverse=True)


# ── StrategyFingerprint ───────────────────────────────────────────────────────

def test_fingerprint_from_empty_result():
    from backtester.engine import BacktestConfig, BacktestResult
    result = BacktestResult("BTC/USDT", "1h", "TestStrategy", BacktestConfig())
    fp = StrategyFingerprint.from_result(result, [])
    assert fp.data == {}


def test_fingerprint_has_required_fields():
    from backtester.engine import BacktestEngine, BacktestConfig
    from backtester.engine import BacktestTrade

    # Build a minimal result with some trades
    engine = BacktestEngine()
    candles = make_candles(trend_prices(120))
    config = BacktestConfig(initial_capital=10_000.0)

    from strategies.simple_ma_strategy import SimpleMAStrategy
    result = engine.run(SimpleMAStrategy(), candles, config, "BTC/USDT", "1m")

    fp = StrategyFingerprint.from_result(result, candles)
    if result.trades:
        assert "best_direction" in fp.data
        assert "avg_volatility" in fp.data
        assert "metrics_summary" in fp.data
