"""Unit tests for backtester metrics."""
import pytest

from backtester.metrics import compute_metrics, _max_drawdown, _sharpe_ratio


def make_trade(pnl, entry_time=0, exit_time=86_400_000, direction="long"):
    return {"pnl": pnl, "entry_time": entry_time, "exit_time": exit_time, "direction": direction}


# ── compute_metrics ───────────────────────────────────────────────────────────

def test_empty_trades_returns_zeros():
    m = compute_metrics([], 10_000.0)
    assert m["total_trades"] == 0
    assert m["total_pnl"] == 0.0
    assert m["win_rate_pct"] == 0.0


def test_all_winning_trades():
    trades = [make_trade(100.0), make_trade(200.0), make_trade(50.0)]
    m = compute_metrics(trades, 10_000.0)
    assert m["win_rate_pct"] == 100.0
    assert m["total_pnl"] == pytest.approx(350.0)
    assert m["total_pnl_pct"] == pytest.approx(3.5)
    assert m["gross_loss"] == 0.0


def test_all_losing_trades():
    trades = [make_trade(-100.0), make_trade(-50.0)]
    m = compute_metrics(trades, 10_000.0)
    assert m["win_rate_pct"] == 0.0
    assert m["total_pnl"] == pytest.approx(-150.0)
    assert m["profit_factor"] == pytest.approx(0.0)  # no gross profit → 0


def test_mixed_win_rate():
    trades = [make_trade(100.0), make_trade(-50.0), make_trade(100.0), make_trade(-50.0)]
    m = compute_metrics(trades, 10_000.0)
    assert m["win_rate_pct"] == 50.0
    assert m["total_trades"] == 4


def test_profit_factor():
    trades = [make_trade(200.0), make_trade(-100.0)]
    m = compute_metrics(trades, 10_000.0)
    assert m["profit_factor"] == pytest.approx(2.0)


def test_best_worst_trade():
    trades = [make_trade(500.0), make_trade(-300.0), make_trade(100.0)]
    m = compute_metrics(trades, 10_000.0)
    assert m["best_trade_pnl"] == pytest.approx(500.0)
    assert m["worst_trade_pnl"] == pytest.approx(-300.0)


def test_avg_trade_duration():
    trades = [
        make_trade(100.0, entry_time=0, exit_time=3_600_000),    # 1h = 3600s
        make_trade(50.0, entry_time=0, exit_time=7_200_000),     # 2h = 7200s
    ]
    m = compute_metrics(trades, 10_000.0)
    assert m["avg_trade_duration_sec"] == pytest.approx(5400.0)  # 1.5h


# ── _max_drawdown ─────────────────────────────────────────────────────────────

def test_max_drawdown_no_drawdown():
    pnls = [100.0, 200.0, 300.0]
    assert _max_drawdown(pnls, 10_000.0) == pytest.approx(0.0)


def test_max_drawdown_with_loss():
    # Start 10000, +500 → peak 10500, then -1000 → equity 9500 → dd=10%
    pnls = [500.0, -1000.0, 200.0]
    dd = _max_drawdown(pnls, 10_000.0)
    assert dd == pytest.approx(10.0)  # 1000/10000


def test_max_drawdown_single_trade_loss():
    pnls = [-500.0]
    dd = _max_drawdown(pnls, 10_000.0)
    assert dd == pytest.approx(5.0)  # 500/10000


# ── _sharpe_ratio ─────────────────────────────────────────────────────────────

def test_sharpe_single_trade_returns_zero():
    assert _sharpe_ratio([100.0], 10_000.0) == 0.0


def test_sharpe_constant_returns_zero():
    # No variance → std=0 → sharpe=0
    assert _sharpe_ratio([100.0, 100.0, 100.0], 10_000.0) == 0.0


def test_sharpe_positive_for_consistent_wins():
    pnls = [100.0] * 20
    # Mean return > 0, std near 0 → high sharpe (but constant → std=0 → 0)
    # Use slightly varied wins to get actual sharpe
    pnls = [100.0 + i * 0.1 for i in range(20)]
    s = _sharpe_ratio(pnls, 10_000.0)
    assert s > 0
