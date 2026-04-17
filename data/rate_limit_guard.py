import asyncio
import time
from collections import deque
from enum import IntEnum

from core.logger import get_logger

log = get_logger("RateLimitGuard")

# BingX лимиты: 20 запросов/сек на IP
MAX_REQUESTS_PER_SEC = 20
WINDOW_SEC = 1.0


class Priority(IntEnum):
    HIGH = 1    # исполнение ордеров, аккаунт
    MEDIUM = 2  # актуальные рыночные данные
    LOW = 3     # исторические данные, синхронизация


class RateLimitGuard:
    def __init__(self, max_per_sec: int = MAX_REQUESTS_PER_SEC) -> None:
        self._max = max_per_sec
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._total_requests = 0
        self._throttled_count = 0

    async def acquire(self, priority: Priority = Priority.MEDIUM) -> None:
        async with self._lock:
            now = time.monotonic()

            # Удаляем метки старше 1 секунды
            while self._timestamps and self._timestamps[0] < now - WINDOW_SEC:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max:
                wait = WINDOW_SEC - (now - self._timestamps[0])
                self._throttled_count += 1
                log.debug(f"Rate limit: жду {wait:.3f}с (приоритет={priority.name})")
                await asyncio.sleep(wait)
                # После ожидания чистим снова
                now = time.monotonic()
                while self._timestamps and self._timestamps[0] < now - WINDOW_SEC:
                    self._timestamps.popleft()

            self._timestamps.append(time.monotonic())
            self._total_requests += 1

    def stats(self) -> dict:
        return {
            "total_requests": self._total_requests,
            "throttled": self._throttled_count,
            "current_window": len(self._timestamps),
        }
