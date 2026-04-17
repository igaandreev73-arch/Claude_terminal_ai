"""
Performance metrics for backtest results.

All functions are pure — no side effects, no state.
"""
from __future__ import annotations

import math
from typing import Any


def compute_metrics(trades: list[dict], initial_capital: float) -> dict[str, Any]:
    """
    Compute full performance metrics from a list of closed trades.

    Each trade dict must have:
      pnl (float), entry_time (int ms), exit_time (int ms), direction (str)

    Returns a metrics dict with all PRD-required fields.
    """
    if not trades:
        return _empty_metrics()

    pnls = [t["pnl"] for t in trades]
    total_pnl = sum(pnls)
    total_pnl_pct = total_pnl / initial_capital * 100

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls) * 100

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    max_drawdown = _max_drawdown(pnls, initial_capital)
    sharpe = _sharpe_ratio(pnls, initial_capital)

    durations_sec = [
        (t["exit_time"] - t["entry_time"]) / 1000
        for t in trades
        if t.get("exit_time") is not None and t.get("entry_time") is not None
    ]
    avg_duration_sec = sum(durations_sec) / len(durations_sec) if durations_sec else 0.0

    best_trade = max(pnls)
    worst_trade = min(pnls)

    # Trades per month: use total span from first entry to last exit
    trades_per_month = _trades_per_month(trades)

    return {
        "total_trades": len(trades),
        "win_rate_pct": round(win_rate, 2),
        "total_pnl": round(total_pnl, 4),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else None,
        "max_drawdown_pct": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe, 4),
        "avg_trade_duration_sec": round(avg_duration_sec, 1),
        "best_trade_pnl": round(best_trade, 4),
        "worst_trade_pnl": round(worst_trade, 4),
        "trades_per_month": round(trades_per_month, 2),
        "gross_profit": round(gross_profit, 4),
        "gross_loss": round(gross_loss, 4),
    }


def _max_drawdown(pnls: list[float], initial_capital: float) -> float:
    """Maximum drawdown as % of initial capital."""
    peak = initial_capital
    equity = initial_capital
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / initial_capital * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _sharpe_ratio(pnls: list[float], initial_capital: float, risk_free: float = 0.0) -> float:
    """Annualised Sharpe ratio (assumes each trade is one period)."""
    n = len(pnls)
    if n < 2:
        return 0.0
    returns = [p / initial_capital for p in pnls]
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
    std_r = math.sqrt(variance) if variance > 0 else 0.0
    if std_r == 0:
        return 0.0
    # Annualise assuming ~252 trades/year (daily equivalent)
    return (mean_r - risk_free) / std_r * math.sqrt(252)


def _trades_per_month(trades: list[dict]) -> float:
    if len(trades) < 2:
        return 0.0
    first = min(t["entry_time"] for t in trades)
    last = max(t.get("exit_time") or t["entry_time"] for t in trades)
    span_ms = last - first
    if span_ms <= 0:
        return 0.0
    months = span_ms / (1000 * 60 * 60 * 24 * 30.44)
    return len(trades) / months if months > 0 else 0.0


def _empty_metrics() -> dict:
    return {
        "total_trades": 0,
        "win_rate_pct": 0.0,
        "total_pnl": 0.0,
        "total_pnl_pct": 0.0,
        "profit_factor": None,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "avg_trade_duration_sec": 0.0,
        "best_trade_pnl": 0.0,
        "worst_trade_pnl": 0.0,
        "trades_per_month": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
    }
