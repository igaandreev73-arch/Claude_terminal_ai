"""Unit tests for Risk Guard."""
import pytest

from execution.risk_guard import RiskConfig, RiskGuard


def make_guard(**kwargs) -> RiskGuard:
    config = RiskConfig(**kwargs)
    guard = RiskGuard(config)
    guard.set_capital(10_000.0)
    return guard


# ── basic allow / block ────────────────────────────────────────────────────────

def test_allows_valid_signal():
    guard = make_guard()
    d = guard.check("BTC/USDT", score=85.0, auto_mode=True, capital=10_000.0, sl_pct=0.02)
    assert d.allowed is True
    assert d.position_size_usd > 0


def test_blocks_low_score_auto():
    guard = make_guard(min_score_auto=80.0)
    d = guard.check("BTC/USDT", score=75.0, auto_mode=True, capital=10_000.0, sl_pct=0.02)
    assert d.allowed is False
    assert "Score" in d.reason


def test_allows_semi_auto_with_lower_score():
    guard = make_guard(min_score_auto=80.0, min_score_semi=60.0)
    d = guard.check("BTC/USDT", score=65.0, auto_mode=False, capital=10_000.0, sl_pct=0.02)
    assert d.allowed is True


def test_blocks_too_many_positions():
    guard = make_guard(max_open_positions=2)
    guard.on_position_opened()
    guard.on_position_opened()
    d = guard.check("BTC/USDT", score=85.0, auto_mode=True, capital=10_000.0, sl_pct=0.02)
    assert d.allowed is False
    assert "позиций" in d.reason


def test_blocks_daily_loss_exceeded():
    guard = make_guard(max_daily_loss_pct=5.0)
    guard.on_position_closed(pnl=-600.0)  # 6% of 10000 > 5%
    d = guard.check("BTC/USDT", score=85.0, auto_mode=True, capital=10_000.0, sl_pct=0.02)
    assert d.allowed is False
    assert "лимит" in d.reason


def test_blocks_excessive_leverage():
    guard = make_guard(max_leverage=10)
    d = guard.check("BTC/USDT", score=85.0, auto_mode=True, capital=10_000.0, sl_pct=0.02, leverage=15)
    assert d.allowed is False
    assert "плечо" in d.reason.lower() or "Плечо" in d.reason


# ── position size ─────────────────────────────────────────────────────────────

def test_position_size_formula():
    # risk 1%, SL 2%, leverage 1 → size = 10000 * 0.01 / 0.02 = 5000
    guard = make_guard(risk_per_trade_pct=1.0)
    d = guard.check("BTC/USDT", score=85.0, auto_mode=True, capital=10_000.0, sl_pct=0.02, leverage=1)
    assert d.allowed is True
    assert d.position_size_usd == pytest.approx(5000.0, rel=0.01)


def test_position_size_with_leverage():
    # leverage=2: size = 10000 * 0.01 / (0.02 / 2) = 10000
    guard = make_guard(risk_per_trade_pct=1.0)
    d = guard.check("BTC/USDT", score=85.0, auto_mode=True, capital=10_000.0, sl_pct=0.02, leverage=2)
    assert d.allowed is True
    assert d.position_size_usd == pytest.approx(10_000.0, rel=0.01)


# ── state tracking ────────────────────────────────────────────────────────────

def test_open_positions_counter():
    guard = make_guard()
    assert guard.get_open_positions() == 0
    guard.on_position_opened()
    guard.on_position_opened()
    assert guard.get_open_positions() == 2
    guard.on_position_closed(pnl=100.0)
    assert guard.get_open_positions() == 1


def test_daily_pnl_tracking():
    guard = make_guard()
    guard.on_position_closed(pnl=200.0)
    guard.on_position_closed(pnl=-100.0)
    assert guard.get_daily_pnl() == pytest.approx(100.0)


def test_positions_floor_at_zero():
    guard = make_guard()
    guard.on_position_closed(pnl=0.0)  # close without open
    assert guard.get_open_positions() == 0
