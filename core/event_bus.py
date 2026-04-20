import asyncio
import time as _time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from core.logger import get_logger

log = get_logger("EventBus")


@dataclass
class Event:
    type: str
    data: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Тип для async-callback обработчиков
EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._running = False
        self._task: asyncio.Task | None = None
        # ── Метрики для Pulse ──────────────────────────────────────────────
        self._global_window: deque[float] = deque()         # метки всех событий за 60с
        self._type_window: dict[str, deque[float]] = defaultdict(deque)  # по типу
        self.last_event_at: float | None = None
        self.last_latency_ms: float | None = None           # задержка очереди (мс)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event_type: str, data: Any = None) -> None:
        event = Event(type=event_type, data=data)
        await self._queue.put(event)

    async def _dispatch_loop(self) -> None:
        log.info("Event Bus запущен")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            now = _time.time()
            # Измеряем задержку очереди
            self.last_latency_ms = round((now - event.timestamp.timestamp()) * 1000, 1)
            self.last_event_at = now
            # Скользящее окно 60с
            self._global_window.append(now)
            self._type_window[event.type].append(now)
            cutoff = now - 60
            while self._global_window and self._global_window[0] < cutoff:
                self._global_window.popleft()

            handlers = self._subscribers.get(event.type, [])
            if not handlers:
                continue

            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    log.error(f"Ошибка в обработчике '{handler.__qualname__}' для '{event.type}': {e}")

    def events_per_min(self) -> int:
        """Суммарное кол-во событий за последние 60 секунд."""
        return len(self._global_window)

    def events_per_min_prefix(self, prefix: str) -> int:
        """События чей тип начинается с prefix за последние 60 секунд."""
        cutoff = _time.time() - 60
        return sum(
            sum(1 for ts in dq if ts >= cutoff)
            for etype, dq in self._type_window.items()
            if etype.startswith(prefix)
        )

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            await self._task
        log.info("Event Bus остановлен")
