import asyncio
import time
import pytest
from data.rate_limit_guard import RateLimitGuard, Priority


async def test_acquire_does_not_exceed_limit():
    guard = RateLimitGuard(max_per_sec=5)
    start = time.monotonic()
    for _ in range(5):
        await guard.acquire()
    elapsed = time.monotonic() - start
    # 5 запросов в пределах 1 сек — должны пройти быстро
    assert elapsed < 1.0


async def test_throttling_on_overflow():
    guard = RateLimitGuard(max_per_sec=3)
    start = time.monotonic()
    for _ in range(4):
        await guard.acquire()
    elapsed = time.monotonic() - start
    # 4-й запрос должен быть задержан (> 0.5 сек суммарно)
    assert elapsed > 0.5


async def test_stats_tracked():
    guard = RateLimitGuard(max_per_sec=10)
    for _ in range(3):
        await guard.acquire(Priority.LOW)
    stats = guard.stats()
    assert stats["total_requests"] == 3


async def test_high_priority_acquires_same_as_low():
    guard = RateLimitGuard(max_per_sec=10)
    await guard.acquire(Priority.HIGH)
    await guard.acquire(Priority.LOW)
    assert guard.stats()["total_requests"] == 2
