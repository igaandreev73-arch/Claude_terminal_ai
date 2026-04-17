"""
Grid Search optimizer + Strategy Fingerprint.

GridSearchOptimizer:
  - Runs the strategy on a single candle series with every param combination
  - Returns a ranked list of BacktestResult sorted by a target metric
  - Uses walk-forward validation to reduce overfitting

StrategyFingerprint:
  - Analyses best-performing param set across different market conditions
  - Reports which regime / volatility / session the strategy prefers
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

from backtester.engine import BacktestConfig, BacktestEngine, BacktestResult
from core.logger import get_logger
from strategies.base_strategy import AbstractStrategy

log = get_logger("Optimizer")


@dataclass
class OptimizeConfig:
    param_grid: dict[str, list[Any]]         # {"rsi_period": [10, 14, 20], ...}
    backtest_config: BacktestConfig = field(default_factory=BacktestConfig)
    target_metric: str = "sharpe_ratio"      # metric to maximise
    min_trades: int = 10                     # skip results with fewer trades
    # Walk-forward: train on first train_ratio of data, validate on rest
    walk_forward: bool = True
    train_ratio: float = 0.7


@dataclass
class OptimizeResult:
    best_params: dict
    best_metric: float
    best_result: BacktestResult
    all_results: list[tuple[dict, BacktestResult]]   # (params, result), sorted desc
    fingerprint: "StrategyFingerprint"


class GridSearchOptimizer:
    def __init__(self, engine: BacktestEngine | None = None) -> None:
        self._engine = engine or BacktestEngine()

    def run(
        self,
        strategy_cls: type[AbstractStrategy],
        candles: list[dict],
        config: OptimizeConfig,
        symbol: str = "",
        timeframe: str = "",
    ) -> OptimizeResult:
        if config.walk_forward:
            split = int(len(candles) * config.train_ratio)
            train_candles = candles[:split]
            val_candles = candles[split:]
        else:
            train_candles = candles
            val_candles = candles

        param_names = list(config.param_grid.keys())
        param_values = list(config.param_grid.values())
        combinations = list(itertools.product(*param_values))

        log.info(f"Grid search: {len(combinations)} комбинаций для {strategy_cls.__name__}")

        scored: list[tuple[dict, BacktestResult]] = []

        for combo in combinations:
            params = dict(zip(param_names, combo))
            strategy = strategy_cls(params=params)

            # Train on training set
            train_result = self._engine.run(
                strategy, train_candles, config.backtest_config, symbol, timeframe
            )

            if train_result.metrics["total_trades"] < config.min_trades:
                continue

            # Validate on validation set
            strategy.reset()
            strategy.params = params
            val_result = self._engine.run(
                strategy, val_candles, config.backtest_config, symbol, timeframe
            )

            # Score on validation set (avoid overfitting to train)
            metric_val = val_result.metrics.get(config.target_metric, 0.0) or 0.0
            scored.append((params, val_result))

        if not scored:
            log.warning("Оптимизация не нашла валидных комбинаций")
            # Return default
            default_strategy = strategy_cls()
            default_result = self._engine.run(
                default_strategy, candles, config.backtest_config, symbol, timeframe
            )
            return OptimizeResult(
                best_params={},
                best_metric=0.0,
                best_result=default_result,
                all_results=[({}, default_result)],
                fingerprint=StrategyFingerprint({}),
            )

        # Sort by target metric descending
        scored.sort(
            key=lambda x: x[1].metrics.get(config.target_metric, 0.0) or 0.0,
            reverse=True,
        )

        best_params, best_result = scored[0]
        best_metric = best_result.metrics.get(config.target_metric, 0.0) or 0.0

        fingerprint = StrategyFingerprint.from_result(best_result, candles)

        log.info(
            f"Лучшие параметры: {best_params}, "
            f"{config.target_metric}={best_metric:.4f}"
        )

        return OptimizeResult(
            best_params=best_params,
            best_metric=best_metric,
            best_result=best_result,
            all_results=scored,
            fingerprint=fingerprint,
        )


@dataclass
class StrategyFingerprint:
    """
    Profile of conditions under which a strategy performs best.
    Built from the equity curve and trade list of the best backtest run.
    """
    data: dict = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: BacktestResult, candles: list[dict]) -> "StrategyFingerprint":
        trades = result.trades
        if not trades or not candles:
            return cls({})

        # Volatility profile: classify each trade's entry candle volatility
        close_prices = [c["close"] for c in candles]
        if len(close_prices) >= 2:
            returns = [
                abs(close_prices[i] - close_prices[i - 1]) / close_prices[i - 1]
                for i in range(1, len(close_prices))
            ]
            avg_vol = sum(returns) / len(returns) if returns else 0.0
        else:
            avg_vol = 0.0

        # Win-rate by direction
        longs = [t for t in trades if t.direction == "long"]
        shorts = [t for t in trades if t.direction == "short"]
        long_wr = sum(1 for t in longs if t.pnl > 0) / len(longs) * 100 if longs else 0.0
        short_wr = sum(1 for t in shorts if t.pnl > 0) / len(shorts) * 100 if shorts else 0.0

        best_direction = "long" if long_wr >= short_wr else "short"
        avg_volatility = "low" if avg_vol < 0.005 else "medium" if avg_vol < 0.015 else "high"

        # Close reason breakdown
        sl_count = sum(1 for t in trades if t.closed_by == "sl")
        tp_count = sum(1 for t in trades if t.closed_by == "tp")

        data = {
            "strategy": result.strategy_name,
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "best_direction": best_direction,
            "long_win_rate_pct": round(long_wr, 1),
            "short_win_rate_pct": round(short_wr, 1),
            "avg_volatility": avg_volatility,
            "sl_exits_pct": round(sl_count / len(trades) * 100, 1),
            "tp_exits_pct": round(tp_count / len(trades) * 100, 1),
            "metrics_summary": {
                "win_rate_pct": result.metrics.get("win_rate_pct"),
                "sharpe_ratio": result.metrics.get("sharpe_ratio"),
                "max_drawdown_pct": result.metrics.get("max_drawdown_pct"),
                "profit_factor": result.metrics.get("profit_factor"),
            },
        }

        return cls(data)
