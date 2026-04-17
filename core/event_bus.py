import asyncio
from collections import defaultdict
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

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)
        log.debug(f"Подписка на событие '{event_type}': {handler.__qualname__}")

    async def publish(self, event_type: str, data: Any = None) -> None:
        event = Event(type=event_type, data=data)
        await self._queue.put(event)
        log.debug(f"Событие опубликовано: '{event_type}'")

    async def _dispatch_loop(self) -> None:
        log.info("Event Bus запущен")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            handlers = self._subscribers.get(event.type, [])
            if not handlers:
                log.debug(f"Нет подписчиков для события '{event.type}'")
                continue

            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    log.error(f"Ошибка в обработчике '{handler.__qualname__}' для '{event.type}': {e}")

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            await self._task
        log.info("Event Bus остановлен")
