"""
WebSocket Server — мост между Python бэкендом и React фронтендом.

Протокол (JSON):
  Server → Client:
    {"type": "event",  "event_type": str, "data": any, "ts": iso}
    {"type": "state",  "positions": [...], "signals": [...], "health": {...}}
    {"type": "pong"}

  Client → Server:
    {"type": "ping"}
    {"type": "command", "command": str, "payload": {}}

Команды от клиента:
  confirm_signal  — подтвердить сигнал (semi-auto)
  reject_signal   — отклонить сигнал
  close_position  — закрыть позицию
  set_mode        — изменить режим исполнения
  get_state       — запросить текущее состояние системы

Публикует: нет (только проксирует события шины)
"""
from __future__ import annotations

import json
import weakref
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web_ws import WebSocketResponse

from core.event_bus import Event, EventBus
from core.logger import get_logger

if TYPE_CHECKING:
    from execution.execution_engine import ExecutionEngine
    from signals.signal_engine import SignalEngine

log = get_logger("WSServer")

# События которые транслируются во фронтенд
BROADCAST_EVENTS = {
    "candle.1m.closed",
    "ta.*",
    "smc.bos.detected", "smc.choch.detected", "smc.fvg.detected",
    "volume.cvd.updated",
    "ob.state_updated", "ob.spoof_detected",
    "mtf.score.updated",
    "correlation.updated", "correlation.divergence",
    "signal.generated", "signal.expired", "signal.executed",
    "anomaly.flash_crash", "anomaly.price_spike", "anomaly.ob_manip", "anomaly.slippage",
    "execution.signal_received", "execution.position_opened", "execution.position_closed",
    "execution.pending", "execution.confirmed", "execution.rejected", "execution.blocked",
    "demo.trade.opened", "demo.trade.closed", "demo.stats.updated",
    "HEALTH_UPDATE",
}


class WSServer:
    def __init__(
        self,
        event_bus: EventBus,
        signal_engine: "SignalEngine",
        execution_engine: "ExecutionEngine",
        host: str = "localhost",
        port: int = 8765,
    ) -> None:
        self._bus = event_bus
        self._signal_engine = signal_engine
        self._execution_engine = execution_engine
        self._host = host
        self._port = port
        self._clients: weakref.WeakSet[WebSocketResponse] = weakref.WeakSet()
        self._app = web.Application()
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        # Подписываемся на все события шины
        for event_type in BROADCAST_EVENTS:
            self._bus.subscribe(event_type, self._on_event)

        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/health", self._health_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        log.info(f"WebSocket сервер запущен: ws://{self._host}:{self._port}/ws")

    async def stop(self) -> None:
        for ws in list(self._clients):
            await ws.close()
        if self._runner:
            await self._runner.cleanup()
        log.info("WebSocket сервер остановлен")

    # ── HTTP handlers ─────────────────────────────────────────────────────────

    async def _health_handler(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "clients": len(list(self._clients))})

    async def _ws_handler(self, request: web.Request) -> WebSocketResponse:
        ws = WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._clients.add(ws)
        log.info(f"WS клиент подключился. Всего: {len(list(self._clients))}")

        try:
            await self._send_state(ws)

            async for msg in ws:
                from aiohttp import WSMsgType
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_command(ws, data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            self._clients.discard(ws)
            log.info(f"WS клиент отключился. Осталось: {len(list(self._clients))}")

        return ws

    # ── Command handling ──────────────────────────────────────────────────────

    async def _handle_command(self, ws: WebSocketResponse, msg: dict) -> None:
        msg_type = msg.get("type")
        command = msg.get("command", "")
        payload = msg.get("payload", {})

        if msg_type == "ping":
            await self._send(ws, {"type": "pong"})
            return

        if msg_type != "command":
            return

        if command == "confirm_signal":
            await self._execution_engine.confirm(payload.get("signal_id", ""))

        elif command == "reject_signal":
            await self._execution_engine.reject(payload.get("signal_id", ""))

        elif command == "close_position":
            await self._execution_engine.close_position(
                payload.get("symbol", ""), reason="user_ui"
            )

        elif command == "set_mode":
            from execution.execution_engine import ExecutionMode
            try:
                mode = ExecutionMode(payload.get("mode", "alert_only"))
                self._execution_engine.set_mode(mode)
                await self._send(ws, {"type": "mode_changed", "mode": mode.value})
            except ValueError:
                pass

        elif command == "get_state":
            await self._send_state(ws)

        elif command == "get_db_stats":
            await self._send_db_stats(ws)

    async def _send_db_stats(self, ws: WebSocketResponse) -> None:
        """Собирает статистику по таблицам БД и отправляет клиенту."""
        from datetime import datetime, timezone
        from sqlalchemy import func, select, text
        from storage.database import get_session_factory
        from storage.models import CandleModel, OrderBookSnapshotModel

        factory = get_session_factory()

        def ts_to_iso(ts: int | None) -> str | None:
            if ts is None:
                return None
            # open_time хранится в миллисекундах
            try:
                return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            except Exception:
                return None

        candles_stats: list[dict] = []
        ob_stats: list[dict] = []

        try:
            async with factory() as session:
                # Свечи — группировка по symbol + timeframe
                rows = await session.execute(
                    select(
                        CandleModel.symbol,
                        CandleModel.timeframe,
                        func.count().label("count"),
                        func.min(CandleModel.open_time).label("min_ts"),
                        func.max(CandleModel.open_time).label("max_ts"),
                        func.sum(
                            (CandleModel.open <= 0).cast(text("INTEGER"))
                        ).label("invalid"),
                    ).group_by(CandleModel.symbol, CandleModel.timeframe)
                    .order_by(CandleModel.symbol, CandleModel.timeframe)
                )
                for r in rows:
                    candles_stats.append({
                        "symbol":    r.symbol,
                        "timeframe": r.timeframe,
                        "count":     r.count,
                        "from":      ts_to_iso(r.min_ts),
                        "to":        ts_to_iso(r.max_ts),
                        "invalid":   r.invalid or 0,
                        "ok":        r.count - (r.invalid or 0),
                    })

                # Стакан — группировка по symbol
                ob_rows = await session.execute(
                    select(
                        OrderBookSnapshotModel.symbol,
                        func.count().label("count"),
                        func.min(OrderBookSnapshotModel.timestamp).label("min_ts"),
                        func.max(OrderBookSnapshotModel.timestamp).label("max_ts"),
                        func.avg(OrderBookSnapshotModel.imbalance).label("avg_imbalance"),
                    ).group_by(OrderBookSnapshotModel.symbol)
                    .order_by(OrderBookSnapshotModel.symbol)
                )
                for r in ob_rows:
                    ob_stats.append({
                        "symbol":        r.symbol,
                        "count":         r.count,
                        "from":          ts_to_iso(r.min_ts),
                        "to":            ts_to_iso(r.max_ts),
                        "avg_imbalance": round(r.avg_imbalance or 0, 4),
                    })

        except Exception as e:
            log.error(f"Ошибка получения статистики БД: {e}")

        await self._send(ws, {
            "type":    "db_stats",
            "candles": candles_stats,
            "orderbook": ob_stats,
        })

    # ── Event forwarding ──────────────────────────────────────────────────────

    async def _on_event(self, event: Event) -> None:
        if not self._clients:
            return
        message = {
            "type": "event",
            "event_type": event.type,
            "data": _serialise(event.data),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        await self._broadcast(message)

    async def _broadcast(self, message: dict) -> None:
        payload = json.dumps(message, default=str)
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def _send(self, ws: WebSocketResponse, message: dict) -> None:
        try:
            await ws.send_str(json.dumps(message, default=str))
        except Exception:
            pass

    async def _send_state(self, ws: WebSocketResponse) -> None:
        """Отправляет текущее состояние системы при подключении клиента."""
        signals = [
            {
                "id": s.id,
                "symbol": s.symbol,
                "direction": s.direction,
                "score": s.score,
                "source": s.source,
                "auto_eligible": s.auto_eligible,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in self._signal_engine.get_queue()
        ]
        positions = self._execution_engine.get_positions()
        mode = self._execution_engine.mode.value

        await self._send(ws, {
            "type": "state",
            "positions": positions,
            "signals": signals,
            "mode": mode,
        })


def _serialise(data):
    """Делает данные JSON-сериализуемыми (рекурсивно)."""
    if hasattr(data, "isoformat"):
        return data.isoformat()
    if isinstance(data, dict):
        return {k: _serialise(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_serialise(v) for v in data]
    if hasattr(data, "__dict__"):
        return {k: _serialise(v) for k, v in data.__dict__.items()
                if not k.startswith("_")}
    return data
