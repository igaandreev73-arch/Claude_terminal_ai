"""
Watchdog — мониторинг WebSocket соединений.

Три уровня диагностики для каждого WS:
  1. Ping/Pong — heartbeat каждые 30с
  2. Message count — если нет сообщений 5с → деградация
  3. Price checksum — сравнение последней WS-цены с REST

Четыре стадии эскалации:
  NORMAL    → зелёный, тихий лог
  DEGRADED  → жёлтый, запись в ленту событий, мягкое переподключение
  LOST      → красный, алёрт, экспоненциальный backoff переподключений
  DEAD      → мигающий красный, торговля переходит в alert_only, нужно ручное вмешательство

Для невосстанавливаемых данных (ликвидации):
  При стадии DEGRADED — немедленно фиксируем data_gap в БД.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable, Awaitable

from core.logger import get_logger

if TYPE_CHECKING:
    from core.event_bus import EventBus

log = get_logger("Watchdog")

CHECK_INTERVAL = 5          # секунд между проверками
MSG_SILENCE_DEGRADED = 5    # секунд молчания → DEGRADED
MSG_SILENCE_LOST = 30       # секунд молчания → LOST
PRICE_DRIFT_PCT = 0.5       # % расхождения WS vs REST → деградация
MAX_RECONNECT_ATTEMPTS = 10
BACKOFF_BASE = 3            # секунд, удваивается


class WatchdogStage(str, Enum):
    NORMAL   = "normal"
    DEGRADED = "degraded"
    LOST     = "lost"
    DEAD     = "dead"


@dataclass
class ConnectionInfo:
    name: str                           # "spot_ws" | "futures_ws" | ...
    market_type: str                    # "spot" | "futures"
    is_critical: bool = False           # если True → невосстанавливаемые данные
    stage: WatchdogStage = WatchdogStage.NORMAL
    last_message_at: float = field(default_factory=time.time)
    last_rest_price: dict[str, float] = field(default_factory=dict)
    last_ws_price: dict[str, float] = field(default_factory=dict)
    reconnect_attempts: int = 0
    degraded_since: float | None = None
    lost_since: float | None = None
    # Функция переподключения (устанавливается снаружи)
    reconnect_fn: Callable[[], Awaitable[None]] | None = None


class Watchdog:
    """
    Центральный сторожевой таймер для всех WS-соединений.
    Регистрирует соединения через register(), затем запускается через start().
    """

    def __init__(self, event_bus: "EventBus", rest_client=None) -> None:
        self._bus = event_bus
        self._rest = rest_client
        self._connections: dict[str, ConnectionInfo] = {}
        self._running = False
        # Публичный статус для Pulse
        self.statuses: dict[str, dict] = {}

    def register(
        self,
        name: str,
        market_type: str = "spot",
        is_critical: bool = False,
        reconnect_fn: Callable[[], Awaitable[None]] | None = None,
    ) -> ConnectionInfo:
        info = ConnectionInfo(
            name=name,
            market_type=market_type,
            is_critical=is_critical,
            reconnect_fn=reconnect_fn,
        )
        self._connections[name] = info
        log.info(f"Watchdog: зарегистрировано соединение '{name}' (critical={is_critical})")
        return info

    def update_message_time(self, name: str) -> None:
        """Вызывается каждый раз когда WS получает сообщение."""
        if name in self._connections:
            self._connections[name].last_message_at = time.time()

    def update_ws_price(self, name: str, symbol: str, price: float) -> None:
        if name in self._connections:
            self._connections[name].last_ws_price[symbol] = price

    def update_rest_price(self, name: str, symbol: str, price: float) -> None:
        if name in self._connections:
            self._connections[name].last_rest_price[symbol] = price

    async def start(self) -> None:
        self._running = True
        log.info("Watchdog запущен")
        while self._running:
            await asyncio.sleep(CHECK_INTERVAL)
            for conn in list(self._connections.values()):
                await self._check(conn)

    async def stop(self) -> None:
        self._running = False
        log.info("Watchdog остановлен")

    # ── Диагностика ───────────────────────────────────────────────────────────

    async def _check(self, conn: ConnectionInfo) -> None:
        now = time.time()
        silence = now - conn.last_message_at

        # ── Уровень 2: счётчик сообщений ──────────────────────────────────────
        level2_ok = silence < MSG_SILENCE_DEGRADED

        # ── Уровень 3: контрольная сумма цен ──────────────────────────────────
        level3_ok = self._check_price_drift(conn)

        # ── Определяем новую стадию ───────────────────────────────────────────
        if silence >= MSG_SILENCE_LOST and not level3_ok:
            new_stage = WatchdogStage.LOST
        elif not level2_ok or not level3_ok:
            new_stage = WatchdogStage.DEGRADED
        else:
            new_stage = WatchdogStage.NORMAL

        # Проверяем DEAD: LOST слишком долго без успешного переподключения
        if (conn.stage == WatchdogStage.LOST and
                conn.reconnect_attempts >= MAX_RECONNECT_ATTEMPTS):
            new_stage = WatchdogStage.DEAD

        await self._transition(conn, new_stage, silence)
        self._update_public_status(conn, silence)

    def _check_price_drift(self, conn: ConnectionInfo) -> bool:
        """Уровень 3: сравнение WS-цены с REST-ценой."""
        for symbol, ws_price in conn.last_ws_price.items():
            rest_price = conn.last_rest_price.get(symbol)
            if rest_price and rest_price > 0 and ws_price > 0:
                drift_pct = abs(ws_price - rest_price) / rest_price * 100
                if drift_pct > PRICE_DRIFT_PCT:
                    log.warning(
                        f"[{conn.name}] Расхождение цены {symbol}: "
                        f"WS={ws_price:.4f} REST={rest_price:.4f} drift={drift_pct:.2f}%"
                    )
                    return False
        return True

    async def _transition(
        self, conn: ConnectionInfo, new_stage: WatchdogStage, silence: float
    ) -> None:
        if new_stage == conn.stage:
            # Стадия та же — попытка переподключения если LOST
            if conn.stage == WatchdogStage.LOST:
                await self._try_reconnect(conn)
            return

        old_stage = conn.stage
        conn.stage = new_stage
        log.info(f"[{conn.name}] {old_stage.value} → {new_stage.value} (молчание={silence:.1f}с)")

        if new_stage == WatchdogStage.DEGRADED:
            conn.degraded_since = time.time()
            await self._on_degraded(conn)

        elif new_stage == WatchdogStage.LOST:
            conn.lost_since = time.time()
            conn.reconnect_attempts = 0
            await self._on_lost(conn)
            await self._try_reconnect(conn)

        elif new_stage == WatchdogStage.DEAD:
            await self._on_dead(conn)

        elif new_stage == WatchdogStage.NORMAL:
            conn.reconnect_attempts = 0
            conn.degraded_since = None
            conn.lost_since = None
            await self._on_recovered(conn)

    async def _on_degraded(self, conn: ConnectionInfo) -> None:
        await self._bus.publish("watchdog.degraded", {
            "connection": conn.name,
            "market_type": conn.market_type,
            "is_critical": conn.is_critical,
            "since": conn.degraded_since,
        })
        # Для невосстанавливаемых данных — немедленно фиксируем data_gap
        if conn.is_critical:
            await self._record_data_gap(conn, "ws_degraded")

    async def _on_lost(self, conn: ConnectionInfo) -> None:
        await self._bus.publish("watchdog.lost", {
            "connection": conn.name,
            "market_type": conn.market_type,
            "is_critical": conn.is_critical,
            "since": conn.lost_since,
        })
        if conn.is_critical:
            await self._record_data_gap(conn, "ws_disconnect")

    async def _on_dead(self, conn: ConnectionInfo) -> None:
        log.error(f"[{conn.name}] DEAD — все попытки переподключения исчерпаны")
        await self._bus.publish("watchdog.dead", {
            "connection": conn.name,
            "market_type": conn.market_type,
            "is_critical": conn.is_critical,
            "reconnect_attempts": conn.reconnect_attempts,
        })

    async def _on_recovered(self, conn: ConnectionInfo) -> None:
        await self._bus.publish("watchdog.recovered", {
            "connection": conn.name,
            "market_type": conn.market_type,
        })
        # Закрываем data_gap если был открыт
        if conn.is_critical:
            await self._close_data_gap(conn)

    async def _try_reconnect(self, conn: ConnectionInfo) -> None:
        if conn.reconnect_fn is None:
            return
        if conn.reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            return

        delay = BACKOFF_BASE * (2 ** min(conn.reconnect_attempts, 7))
        conn.reconnect_attempts += 1
        log.info(f"[{conn.name}] Переподключение #{conn.reconnect_attempts} через {delay}с...")

        await self._bus.publish("watchdog.reconnecting", {
            "connection": conn.name,
            "attempt": conn.reconnect_attempts,
            "delay": delay,
        })

        await asyncio.sleep(delay)
        try:
            await conn.reconnect_fn()
            log.info(f"[{conn.name}] Переподключение #{conn.reconnect_attempts} успешно")
        except Exception as e:
            log.warning(f"[{conn.name}] Переподключение #{conn.reconnect_attempts} провалилось: {e}")

    # ── Работа с data_gaps ────────────────────────────────────────────────────

    async def _record_data_gap(self, conn: ConnectionInfo, cause: str) -> None:
        try:
            from storage.database import get_session_factory
            from storage.models import DataGapModel
            import time as _time

            now_ms = int(_time.time() * 1000)
            factory = get_session_factory()
            async with factory() as session:
                gap = DataGapModel(
                    symbol="ALL",
                    data_type="liquidations" if conn.is_critical else "candles",
                    market_type=conn.market_type,
                    gap_start=now_ms,
                    gap_end=now_ms,
                    cause=cause,
                    recoverable=False if conn.is_critical else True,
                    recovery_status="pending",
                    detected_at=int(_time.time()),
                )
                session.add(gap)
                await session.commit()
        except Exception as e:
            log.debug(f"record_data_gap error: {e}")

    async def _close_data_gap(self, conn: ConnectionInfo) -> None:
        """Обновляет gap_end у последнего открытого пропуска этого соединения."""
        try:
            from storage.database import get_session_factory
            from storage.models import DataGapModel
            from sqlalchemy import select, desc
            import time as _time

            factory = get_session_factory()
            async with factory() as session:
                stmt = (
                    select(DataGapModel)
                    .where(
                        DataGapModel.market_type == conn.market_type,
                        DataGapModel.recovery_status == "pending",
                    )
                    .order_by(desc(DataGapModel.detected_at))
                    .limit(1)
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
                if row:
                    row.gap_end = int(_time.time() * 1000)
                    row.recovery_status = "recovered"
                    row.recovered_at = int(_time.time())
                    await session.commit()
        except Exception as e:
            log.debug(f"close_data_gap error: {e}")

    # ── Публичный статус для Pulse ────────────────────────────────────────────

    def _update_public_status(self, conn: ConnectionInfo, silence: float) -> None:
        self.statuses[conn.name] = {
            "name": conn.name,
            "market_type": conn.market_type,
            "is_critical": conn.is_critical,
            "stage": conn.stage.value,
            "silence_sec": round(silence, 1),
            "reconnect_attempts": conn.reconnect_attempts,
            "degraded_since": conn.degraded_since,
            "lost_since": conn.lost_since,
            "last_message_at": conn.last_message_at,
        }

    def get_all_statuses(self) -> list[dict]:
        return list(self.statuses.values())
