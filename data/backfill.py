"""
Исторический backfill свечей.

Стратегия: загружаем ТОЛЬКО 1m свечи с API, остальные TF агрегируем локально.
Это гарантирует консистентность данных: 5m всегда кратно 1m и т.д.
"""
from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from core.logger import get_logger
from data.bingx_rest import BingXRestClient
from data.validator import Candle
from storage.repositories.candles_repo import CandlesRepository

if TYPE_CHECKING:
    from core.event_bus import EventBus

log = get_logger("Backfill")

# Сколько 1m-свечей хотим при старте
TARGET_1M = 2000

# Период → минуты
PERIOD_MINUTES: dict[str, int] = {
    "1w":  7  * 24 * 60,
    "1mo": 30 * 24 * 60,
    "1y":  365 * 24 * 60,
    "all": 3  * 365 * 24 * 60,
}

# Таймфреймы для агрегации (минут в каждом)
AGG_TFS: dict[str, int] = {
    "5m":  5,
    "15m": 15,
    "1h":  60,
    "4h":  240,
    "1d":  1440,
}

MAX_PER_REQUEST = 1440   # BingX max limit
REQUEST_SLEEP   = 0.45   # ~20 req/s max


# ── Агрегация ─────────────────────────────────────────────────────────────────

def _aggregate_1m(candles_1m: list[Candle], tf: str, tf_minutes: int) -> list[Candle]:
    """Агрегирует 1m-свечи в свечи таймфрейма tf."""
    buckets: dict[int, list[Candle]] = defaultdict(list)
    for c in candles_1m:
        # Ключ — начало окна в ms, выровненное по tf_minutes
        bucket_min = (c.open_time // 60_000 // tf_minutes) * tf_minutes
        buckets[bucket_min * 60_000].append(c)

    result: list[Candle] = []
    for bucket_ts in sorted(buckets):
        group = sorted(buckets[bucket_ts], key=lambda x: x.open_time)
        # Пропускаем неполные свечи (нет смысла хранить незакрытую)
        if len(group) < tf_minutes:
            continue
        result.append(Candle(
            symbol=group[0].symbol,
            timeframe=tf,
            open_time=bucket_ts,
            open=group[0].open,
            high=max(c.high for c in group),
            low=min(c.low for c in group),
            close=group[-1].close,
            volume=sum(c.volume for c in group),
            is_closed=True,
            source="aggregated",
        ))
    return result


async def _save_with_aggregates(candles_1m: list[Candle], repo: CandlesRepository) -> None:
    """Сохраняет 1m-свечи и все агрегированные TF."""
    if not candles_1m:
        return
    await repo.upsert_many(candles_1m)
    for tf, tf_min in AGG_TFS.items():
        agg = _aggregate_1m(candles_1m, tf, tf_min)
        if agg:
            await repo.upsert_many(agg)
            log.debug(f"Агрегировано {len(agg)} свечей {tf}")


# ── Авто-бэкфилл при старте ──────────────────────────────────────────────────

async def run_backfill(
    symbols: list[str],
    rest_client: BingXRestClient,
    repo: CandlesRepository,
) -> None:
    """Загружает последние TARGET_1M 1m-свечей и агрегирует все TF."""
    log.info(f"Запуск стартового бэкфилла для {len(symbols)} символов...")
    for symbol in symbols:
        try:
            existing = await repo.count(symbol, "1m")
            if existing >= TARGET_1M:
                log.info(f"{symbol}: в БД {existing} 1m-свечей, бэкфилл не нужен")
                continue

            log.info(f"{symbol}: загружаем {TARGET_1M} 1m-свечей...")
            candles = await rest_client.fetch_klines(symbol, "1m", limit=TARGET_1M)
            if candles:
                await _save_with_aggregates(candles, repo)
                log.info(f"{symbol}: сохранено {len(candles)} 1m + агрегаты")
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"Ошибка стартового бэкфилла {symbol}: {e}")

    log.info("Стартовый бэкфилл завершён")


# ── Ручной бэкфилл по запросу пользователя ───────────────────────────────────

async def run_manual_backfill(
    symbol: str,
    period: str,
    rest_client: BingXRestClient,
    repo: CandlesRepository,
    bus: "EventBus",
    task_id: str,
) -> None:
    """
    Загружает исторические 1m-свечи за указанный период, агрегирует все TF.
    Публикует backfill.progress и backfill.complete/error.
    """
    period_min = PERIOD_MINUTES.get(period, PERIOD_MINUTES["1w"])
    total_pages = max(1, math.ceil(period_min / MAX_PER_REQUEST))

    log.info(f"[{task_id}] Ручной бэкфилл {symbol} период={period}: ~{total_pages} запросов (только 1m)")

    await bus.publish("backfill.progress", {
        "task_id": task_id,
        "symbol": symbol,
        "period": period,
        "fetched": 0,
        "total": total_pages,
        "percent": 0,
        "current_tf": "1m",
        "status": "running",
    })

    now_ms   = int(time.time() * 1000)
    start_ms = now_ms - period_min * 60 * 1000
    end_ms   = now_ms
    page_dur = MAX_PER_REQUEST * 60 * 1000  # 1m × MAX_PER_REQUEST
    done     = 0
    all_1m: list[Candle] = []

    try:
        while end_ms > start_ms:
            req_start = max(start_ms, end_ms - page_dur)
            try:
                chunk = await rest_client.fetch_klines(
                    symbol, "1m",
                    limit=MAX_PER_REQUEST,
                    start_time=req_start,
                    end_time=end_ms,
                )
                if chunk:
                    all_1m.extend(chunk)
            except Exception as e:
                log.warning(f"[{task_id}] Ошибка запроса {symbol} 1m: {e}")

            end_ms = req_start
            done += 1
            percent = min(99, int(done / total_pages * 100))

            await bus.publish("backfill.progress", {
                "task_id": task_id,
                "symbol": symbol,
                "period": period,
                "fetched": done,
                "total": total_pages,
                "percent": percent,
                "current_tf": "1m",
                "status": "running",
            })

            await asyncio.sleep(REQUEST_SLEEP)

        # Сохраняем все 1m-свечи и агрегируем
        log.info(f"[{task_id}] Получено {len(all_1m)} 1m-свечей, агрегируем и сохраняем...")
        await _save_with_aggregates(all_1m, repo)

    except asyncio.CancelledError:
        log.warning(f"[{task_id}] Бэкфилл отменён")
        raise
    except Exception as e:
        log.error(f"[{task_id}] Критическая ошибка бэкфилла: {e}")
        await bus.publish("backfill.error", {
            "task_id": task_id,
            "symbol": symbol,
            "error": str(e),
        })
        return

    await bus.publish("backfill.complete", {
        "task_id": task_id,
        "symbol": symbol,
        "period": period,
        "total_fetched": len(all_1m),
        "status": "complete",
    })
    log.info(f"[{task_id}] Бэкфилл {symbol} завершён: {len(all_1m)} 1m-свечей + агрегаты")
