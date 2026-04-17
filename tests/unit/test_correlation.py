"""Unit tests for Correlation Engine."""
import pytest

from analytics.correlation import (
    CorrelationEngine,
    _check_divergence,
    _market_regime,
    pearson,
    pct_changes,
)
from core.event_bus import Event, EventBus


# ── pearson ───────────────────────────────────────────────────────────────────

def test_pearson_perfect_positive():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert pearson(xs, xs) == pytest.approx(1.0, abs=1e-5)


def test_pearson_perfect_negative():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [5.0, 4.0, 3.0, 2.0, 1.0]
    assert pearson(xs, ys) == pytest.approx(-1.0, abs=1e-5)


def test_pearson_zero_correlation():
    xs = [1.0, 2.0, 1.0, 2.0]
    ys = [2.0, 1.0, 2.0, 1.0]
    result = pearson(xs, ys)
    assert result == pytest.approx(-1.0, abs=1e-5)


def test_pearson_returns_none_for_short_list():
    assert pearson([1.0], [1.0]) is None


def test_pearson_returns_none_for_mismatched_lengths():
    assert pearson([1.0, 2.0], [1.0]) is None


def test_pearson_returns_none_for_constant_series():
    assert pearson([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) is None


# ── pct_changes ───────────────────────────────────────────────────────────────

def test_pct_changes_basic():
    prices = [100.0, 110.0, 99.0]
    changes = pct_changes(prices)
    assert len(changes) == 2
    assert changes[0] == pytest.approx(0.1)
    assert changes[1] == pytest.approx(-0.1, rel=1e-4)


def test_pct_changes_empty_for_one_price():
    assert pct_changes([100.0]) == []


# ── _market_regime ────────────────────────────────────────────────────────────

def test_regime_following():
    assert _market_regime(0.75) == "following"


def test_regime_inverse():
    assert _market_regime(-0.80) == "inverse"


def test_regime_independent():
    assert _market_regime(0.3) == "independent"
    assert _market_regime(-0.3) == "independent"


def test_regime_boundary_following():
    assert _market_regime(0.7) == "following"


# ── _check_divergence ─────────────────────────────────────────────────────────

def _make_changes(n, value):
    return [value] * n


def test_divergence_detected():
    # BTC went up, symbol went down — divergence
    changes_sym = _make_changes(10, -0.02)  # symbol falling
    changes_ref = _make_changes(10, 0.02)   # BTC rising
    result = _check_divergence(changes_sym, changes_ref, corr=0.85)
    assert result is not None
    assert result["direction"] == "bear"


def test_divergence_not_detected_low_correlation():
    changes_sym = _make_changes(10, -0.02)
    changes_ref = _make_changes(10, 0.02)
    result = _check_divergence(changes_sym, changes_ref, corr=0.5)
    assert result is None


def test_divergence_not_detected_same_direction():
    changes_sym = _make_changes(10, 0.02)
    changes_ref = _make_changes(10, 0.02)
    result = _check_divergence(changes_sym, changes_ref, corr=0.85)
    assert result is None


def test_divergence_not_detected_small_move():
    changes_sym = _make_changes(10, -0.001)  # below DIVERGENCE_DELTA
    changes_ref = _make_changes(10, 0.001)
    result = _check_divergence(changes_sym, changes_ref, corr=0.85)
    assert result is None


def test_divergence_bull_direction():
    # Symbol going up, BTC going down → bull divergence
    changes_sym = _make_changes(10, 0.02)
    changes_ref = _make_changes(10, -0.02)
    result = _check_divergence(changes_sym, changes_ref, corr=0.85)
    assert result is not None
    assert result["direction"] == "bull"


# ── CorrelationEngine ─────────────────────────────────────────────────────────

def _candle_event(symbol, close):
    from data.validator import Candle
    candle = Candle(
        symbol=symbol,
        timeframe="1m",
        open_time=1_000_000,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=100.0,
    )
    return Event("candle.1m.closed", candle)


@pytest.mark.asyncio
async def test_engine_accumulates_closes():
    bus = EventBus()
    engine = CorrelationEngine(bus, ["BTC/USDT", "SOL/USDT"])
    await engine.start()

    for i in range(5):
        await engine._on_candle(_candle_event("BTC/USDT", 30000.0 + i))

    assert len(engine._closes["BTC/USDT"]) == 5


@pytest.mark.asyncio
async def test_engine_no_calc_below_min_window():
    bus = EventBus()
    await bus.start()
    engine = CorrelationEngine(bus, ["SOL/USDT"])
    await engine.start()

    received = []
    bus.subscribe("correlation.updated", lambda e: received.append(e.data))

    # Feed only 5 candles — below MIN_WINDOW=20
    for i in range(5):
        await engine._on_candle(_candle_event("SOL/USDT", 100.0 + i))

    import asyncio
    await asyncio.sleep(0.05)
    assert received == []

    await bus.stop()


@pytest.mark.asyncio
async def test_engine_publishes_after_min_window():
    bus = EventBus()
    await bus.start()
    engine = CorrelationEngine(bus, ["SOL/USDT"])
    await engine.start()

    received = []
    bus.subscribe("correlation.updated", lambda e: received.append(e.data))

    # Feed MIN_WINDOW+ candles for both SOL and BTC reference
    prices_btc = [30000.0 + i * 10 for i in range(25)]
    prices_sol = [100.0 + i * 0.3 for i in range(25)]

    for p in prices_btc:
        await engine._on_candle(_candle_event("BTC/USDT", p))
    for p in prices_sol:
        await engine._on_candle(_candle_event("SOL/USDT", p))

    import asyncio
    await asyncio.sleep(0.05)
    assert len(received) > 0
    assert received[-1]["symbol"] == "SOL/USDT"

    await bus.stop()


@pytest.mark.asyncio
async def test_engine_get_correlation_sync():
    bus = EventBus()
    engine = CorrelationEngine(bus, ["SOL/USDT"])
    await engine.start()

    prices_btc = [30000.0 + i * 10 for i in range(25)]
    prices_sol = [100.0 + i * 0.3 for i in range(25)]

    for p in prices_btc:
        engine._closes["BTC/USDT"].append(p)
    for p in prices_sol:
        engine._closes["SOL/USDT"].append(p)

    corr = engine.get_correlation("SOL/USDT", "BTC/USDT")
    assert corr is not None
    assert -1.0 <= corr <= 1.0


@pytest.mark.asyncio
async def test_engine_matrix_published():
    bus = EventBus()
    await bus.start()
    engine = CorrelationEngine(bus, ["BTC/USDT", "ETH/USDT"])
    await engine.start()

    matrix_events = []
    bus.subscribe("correlation.matrix", lambda e: matrix_events.append(e.data))

    # Fill enough data and trigger matrix (every MATRIX_INTERVAL=20 updates)
    for sym in ("BTC/USDT", "ETH/USDT"):
        for i in range(25):
            engine._closes[sym].append(1000.0 + i)

    # Manually trigger matrix
    await engine._publish_matrix()

    import asyncio
    await asyncio.sleep(0.05)

    assert len(matrix_events) > 0
    matrix = matrix_events[0]["matrix"]
    assert "BTC/USDT" in matrix
    assert matrix["BTC/USDT"]["BTC/USDT"] == 1.0

    await bus.stop()


@pytest.mark.asyncio
async def test_engine_ignores_non_tracked_symbols():
    bus = EventBus()
    engine = CorrelationEngine(bus, ["BTC/USDT"])
    await engine.start()

    # Send ETH candle — not in tracked symbols, update_count should not increment
    count_before = engine._update_count
    await engine._on_candle(_candle_event("ETH/USDT", 2000.0))
    assert engine._update_count == count_before
