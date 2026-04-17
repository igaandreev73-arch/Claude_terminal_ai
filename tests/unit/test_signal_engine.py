"""Unit tests for Signal Engine."""
import asyncio
import pytest

from core.event_bus import Event, EventBus
from signals.signal_engine import SignalEngine, SCORE_MIN_SIGNAL


def mtf_event(symbol, direction, score, auto_eligible=False):
    return Event("mtf.score.updated", {
        "symbol": symbol, "direction": direction,
        "score": score, "actionable": score >= 60,
        "auto_eligible": auto_eligible, "ta_signals_count": 3,
    })


def div_event(symbol, direction, corr=0.85):
    return Event("correlation.divergence", {
        "symbol": symbol, "direction": direction,
        "correlation": corr, "reference": "BTC/USDT",
        "sym_move_pct": -2.0, "ref_move_pct": 2.0,
    })


@pytest.mark.asyncio
async def test_signal_generated_above_threshold():
    bus = EventBus()
    await bus.start()
    engine = SignalEngine(bus)
    await engine.start()

    received = []
    bus.subscribe("signal.generated", lambda e: received.append(e.data))

    await engine._on_mtf_score(mtf_event("BTC/USDT", "bull", score=75.0))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["symbol"] == "BTC/USDT"
    assert received[0]["direction"] == "bull"
    await bus.stop()


@pytest.mark.asyncio
async def test_no_signal_below_threshold():
    bus = EventBus()
    engine = SignalEngine(bus)
    await engine.start()

    received = []
    bus.subscribe("signal.generated", lambda e: received.append(e.data))

    await engine._on_mtf_score(mtf_event("BTC/USDT", "bull", score=SCORE_MIN_SIGNAL - 1))
    assert received == []


@pytest.mark.asyncio
async def test_duplicate_signal_ignored():
    bus = EventBus()
    await bus.start()
    engine = SignalEngine(bus)
    await engine.start()

    received = []
    bus.subscribe("signal.generated", lambda e: received.append(e.data))

    await engine._on_mtf_score(mtf_event("BTC/USDT", "bull", score=75.0))
    await engine._on_mtf_score(mtf_event("BTC/USDT", "bull", score=78.0))  # same pair+direction
    await asyncio.sleep(0.05)

    assert len(received) == 1
    await bus.stop()


@pytest.mark.asyncio
async def test_different_direction_not_duplicate():
    bus = EventBus()
    await bus.start()
    engine = SignalEngine(bus)
    await engine.start()

    received = []
    bus.subscribe("signal.generated", lambda e: received.append(e.data))

    await engine._on_mtf_score(mtf_event("BTC/USDT", "bull", score=75.0))
    await engine._on_mtf_score(mtf_event("BTC/USDT", "bear", score=70.0))
    await asyncio.sleep(0.05)

    assert len(received) == 2
    await bus.stop()


@pytest.mark.asyncio
async def test_divergence_generates_signal():
    bus = EventBus()
    await bus.start()
    engine = SignalEngine(bus)
    await engine.start()

    received = []
    bus.subscribe("signal.generated", lambda e: received.append(e.data))

    await engine._on_divergence(div_event("SOL/USDT", "bull"))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["source"] == "divergence"
    await bus.stop()


@pytest.mark.asyncio
async def test_divergence_low_correlation_ignored():
    bus = EventBus()
    engine = SignalEngine(bus)
    await engine.start()

    received = []
    bus.subscribe("signal.generated", lambda e: received.append(e.data))

    await engine._on_divergence(div_event("SOL/USDT", "bull", corr=0.5))
    assert received == []


@pytest.mark.asyncio
async def test_get_queue_returns_active_signals():
    bus = EventBus()
    engine = SignalEngine(bus)
    await engine.start()

    await engine._on_mtf_score(mtf_event("BTC/USDT", "bull", score=75.0))
    await engine._on_mtf_score(mtf_event("ETH/USDT", "bear", score=70.0))

    queue = engine.get_queue()
    assert len(queue) == 2


@pytest.mark.asyncio
async def test_mark_executed_removes_from_queue():
    bus = EventBus()
    await bus.start()
    engine = SignalEngine(bus)
    await engine.start()

    await engine._on_mtf_score(mtf_event("BTC/USDT", "bull", score=75.0))
    queue = engine.get_queue()
    assert len(queue) == 1

    signal_id = queue[0].id
    await engine.mark_executed(signal_id)

    assert len(engine.get_queue()) == 0
    await bus.stop()


@pytest.mark.asyncio
async def test_signal_expired_published_on_tick():
    from datetime import timedelta
    bus = EventBus()
    await bus.start()
    engine = SignalEngine(bus)
    await engine.start()

    # Create signal manually with past expiry
    await engine._on_mtf_score(mtf_event("BTC/USDT", "bull", score=75.0))
    queue = engine.get_queue()
    assert len(queue) == 1

    # Expire it manually
    from datetime import datetime, timezone
    signal = queue[0]
    signal.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    expired = []
    bus.subscribe("signal.expired", lambda e: expired.append(e.data))

    await engine.tick()
    await asyncio.sleep(0.05)

    assert len(expired) == 1
    assert expired[0]["symbol"] == "BTC/USDT"
    assert len(engine.get_queue()) == 0
    await bus.stop()
