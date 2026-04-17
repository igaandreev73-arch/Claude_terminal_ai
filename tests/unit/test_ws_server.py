"""Unit tests for WebSocket server helpers (serialisation, message structure)."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from core.event_bus import Event, EventBus
from execution.bingx_private import BingXPrivateClient
from execution.execution_engine import ExecutionEngine, ExecutionMode
from execution.risk_guard import RiskGuard
from signals.signal_engine import SignalEngine
from ui.ws_server import WSServer, _serialise


# ── _serialise ────────────────────────────────────────────────────────────────

def test_serialise_dict():
    assert _serialise({"a": 1}) == {"a": 1}


def test_serialise_datetime():
    dt = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert "2026-04-17" in _serialise(dt)


def test_serialise_object_with_dict():
    class Obj:
        def __init__(self):
            self.foo = "bar"
            self._private = "skip"
    result = _serialise(Obj())
    assert result == {"foo": "bar"}


def test_serialise_nested():
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    obj = {"ts": dt, "value": 42}
    result = _serialise(obj)
    assert "2026" in result["ts"]
    assert result["value"] == 42


# ── WSServer construction ─────────────────────────────────────────────────────

def make_server(port=9999):
    bus = EventBus()
    sig = SignalEngine(bus)
    guard = RiskGuard()
    api = BingXPrivateClient("k", "s", dry_run=True)
    exe = ExecutionEngine(bus, guard, api)
    return WSServer(bus, sig, exe, host="localhost", port=port)


def test_server_creates_without_error():
    server = make_server()
    assert server._host == "localhost"
    assert server._port == 9999


def test_server_no_clients_initially():
    server = make_server()
    assert len(list(server._clients)) == 0


# ── Event broadcast logic ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_skips_when_no_clients():
    server = make_server()
    # Should not raise even with no clients
    await server._broadcast({"type": "event", "event_type": "test", "data": {}})


@pytest.mark.asyncio
async def test_on_event_formats_correctly():
    server = make_server()

    broadcast_calls = []

    async def fake_broadcast(msg):
        broadcast_calls.append(msg)

    server._broadcast = fake_broadcast

    # Add a dummy client so the guard `if not self._clients` doesn't short-circuit
    dummy = MagicMock()
    server._clients.add(dummy)

    event = Event("signal.generated", {"symbol": "BTC/USDT", "score": 85.0})
    await server._on_event(event)

    assert len(broadcast_calls) == 1
    msg = broadcast_calls[0]
    assert msg["type"] == "event"
    assert msg["event_type"] == "signal.generated"
    assert "ts" in msg


# ── Command routing ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_pong():
    server = make_server()

    sent = []
    ws_mock = AsyncMock()
    ws_mock.send_str = AsyncMock(side_effect=lambda s: sent.append(s))

    server._send = AsyncMock(side_effect=lambda ws, msg: sent.append(msg))

    await server._handle_command(ws_mock, {"type": "ping"})
    assert any(m.get("type") == "pong" for m in sent)


@pytest.mark.asyncio
async def test_get_state_command_sends_state():
    server = make_server()

    sent = []
    server._send_state = AsyncMock(side_effect=lambda ws: sent.append("state_sent"))

    ws_mock = AsyncMock()
    await server._handle_command(ws_mock, {"type": "command", "command": "get_state", "payload": {}})
    assert "state_sent" in sent


@pytest.mark.asyncio
async def test_set_mode_command():
    server = make_server()
    ws_mock = AsyncMock()

    sent = []
    server._send = AsyncMock(side_effect=lambda ws, msg: sent.append(msg))

    await server._handle_command(ws_mock, {
        "type": "command",
        "command": "set_mode",
        "payload": {"mode": "auto"},
    })

    assert server._execution_engine.mode == ExecutionMode.AUTO
    assert any(m.get("type") == "mode_changed" for m in sent)


@pytest.mark.asyncio
async def test_unknown_command_is_ignored():
    server = make_server()
    ws_mock = AsyncMock()
    # Should not raise
    await server._handle_command(ws_mock, {"type": "command", "command": "unknown", "payload": {}})
