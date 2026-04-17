"""Unit tests for ExecutionEngine — all three modes + anomaly reactions."""
import asyncio
import pytest

from core.event_bus import Event, EventBus
from execution.bingx_private import BingXPrivateClient
from execution.execution_engine import ExecutionEngine, ExecutionMode
from execution.risk_guard import RiskConfig, RiskGuard


def make_engine(bus, mode=ExecutionMode.AUTO, capital=10_000.0):
    guard = RiskGuard(RiskConfig(min_score_auto=80.0, min_score_semi=60.0, max_open_positions=3))
    api = BingXPrivateClient("key", "secret", dry_run=True)
    engine = ExecutionEngine(bus, guard, api, initial_capital=capital, mode=mode)
    return engine


def signal_event(symbol="BTC/USDT", direction="bull", score=85.0, auto_eligible=True):
    return Event("signal.generated", {
        "id": "sig1", "symbol": symbol, "direction": direction,
        "score": score, "auto_eligible": auto_eligible,
    })


# ── AUTO mode ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_mode_opens_position():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.AUTO)
    await engine.start()

    opened = []
    bus.subscribe("execution.position_opened", lambda e: opened.append(e.data))

    await engine._on_signal(signal_event(score=85.0, auto_eligible=True))
    await asyncio.sleep(0.05)

    assert len(opened) == 1
    assert opened[0]["symbol"] == "BTC/USDT"
    await bus.stop()


@pytest.mark.asyncio
async def test_auto_mode_blocks_low_score():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.AUTO)
    await engine.start()

    blocked = []
    bus.subscribe("execution.blocked", lambda e: blocked.append(e.data))

    await engine._on_signal(signal_event(score=70.0, auto_eligible=False))
    await asyncio.sleep(0.05)

    assert len(blocked) == 1
    await bus.stop()


@pytest.mark.asyncio
async def test_auto_mode_does_not_open_second_position_same_symbol():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.AUTO)
    await engine.start()

    opened = []
    blocked = []
    bus.subscribe("execution.position_opened", lambda e: opened.append(e.data))
    bus.subscribe("execution.blocked", lambda e: blocked.append(e.data))

    await engine._on_signal(signal_event(score=85.0, auto_eligible=True))
    await engine._on_signal(signal_event(score=85.0, auto_eligible=True))  # duplicate symbol
    await asyncio.sleep(0.05)

    assert len(opened) == 1
    assert len(blocked) == 1
    await bus.stop()


# ── SEMI_AUTO mode ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_semi_auto_pending_on_signal():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.SEMI_AUTO)
    await engine.start()

    pending = []
    bus.subscribe("execution.pending", lambda e: pending.append(e.data))

    await engine._on_signal(signal_event(score=65.0, auto_eligible=False))
    await asyncio.sleep(0.05)

    assert len(pending) == 1
    assert pending[0]["symbol"] == "BTC/USDT"
    await bus.stop()


@pytest.mark.asyncio
async def test_semi_auto_confirm_opens_position():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.SEMI_AUTO)
    await engine.start()

    opened = []
    confirmed = []
    bus.subscribe("execution.position_opened", lambda e: opened.append(e.data))
    bus.subscribe("execution.confirmed", lambda e: confirmed.append(e.data))

    await engine._on_signal(signal_event(score=65.0, auto_eligible=False))
    await asyncio.sleep(0.05)

    signal_id = list(engine._pending.keys())[0]
    await engine.confirm(signal_id)
    await asyncio.sleep(0.05)

    assert len(confirmed) == 1
    assert len(opened) == 1
    await bus.stop()


@pytest.mark.asyncio
async def test_semi_auto_reject():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.SEMI_AUTO)
    await engine.start()

    rejected = []
    bus.subscribe("execution.rejected", lambda e: rejected.append(e.data))

    await engine._on_signal(signal_event(score=65.0, auto_eligible=False))
    await asyncio.sleep(0.05)

    signal_id = list(engine._pending.keys())[0]
    await engine.reject(signal_id)
    await asyncio.sleep(0.05)

    assert len(rejected) == 1
    assert rejected[0]["reason"] == "user"
    await bus.stop()


# ── ALERT_ONLY mode ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alert_only_does_not_open_position():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.ALERT_ONLY)
    await engine.start()

    opened = []
    bus.subscribe("execution.position_opened", lambda e: opened.append(e.data))

    await engine._on_signal(signal_event(score=90.0, auto_eligible=True))
    await asyncio.sleep(0.05)

    assert len(opened) == 0
    await bus.stop()


# ── Anomaly reactions ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flash_crash_blocks_new_entries():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.AUTO)
    await engine.start()

    blocked = []
    bus.subscribe("execution.blocked", lambda e: blocked.append(e.data))

    await engine._on_flash_crash(Event("anomaly.flash_crash", {"symbol": "BTC/USDT", "drop_pct": 5.0}))
    await engine._on_signal(signal_event(score=90.0, auto_eligible=True))
    await asyncio.sleep(0.05)

    assert len(blocked) == 1
    assert "Flash crash" in blocked[0]["reason"]
    await bus.stop()


# ── Mode switching ────────────────────────────────────────────────────────────

def test_mode_switch_without_restart():
    bus = EventBus()
    engine = make_engine(bus, mode=ExecutionMode.AUTO)
    assert engine.mode == ExecutionMode.AUTO
    engine.set_mode(ExecutionMode.ALERT_ONLY)
    assert engine.mode == ExecutionMode.ALERT_ONLY


# ── Close position ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_close_position():
    bus = EventBus()
    await bus.start()
    engine = make_engine(bus, mode=ExecutionMode.AUTO)
    await engine.start()

    await engine._on_signal(signal_event(score=85.0, auto_eligible=True))
    await asyncio.sleep(0.05)
    assert "BTC/USDT" in engine._positions

    closed_events = []
    bus.subscribe("execution.position_closed", lambda e: closed_events.append(e.data))

    await engine.close_position("BTC/USDT", reason="manual")
    await asyncio.sleep(0.05)

    assert "BTC/USDT" not in engine._positions
    assert len(closed_events) == 1
    await bus.stop()
