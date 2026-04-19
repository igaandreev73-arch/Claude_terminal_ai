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

# Таймфреймы для агрегации (минут в каждом) — все TF которые мы храним
AGG_TFS: dict[str, int] = {
    "3m":  3,
    "5m":  5,
    "15m": 15,
    "30m": 30,
    "1h":  60,
    "2h":  120,
    "4h":  240,
    "1d":  1440,
}

# Ожидаемое соотношение между соседними TF (для проверки целостности)
# Каждый следующий TF должен содержать МЕНЬШЕ свечей чем предыдущий
_TF_ORDER: list[str] = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"]

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


# ── Проверка и авторемонт целостности БД ──────────────────────────────────────

async def repair_integrity(symbols: list[str], repo: CandlesRepository) -> None:
    """
    Проверяет что все агрегированные TF соответствуют покрытию 1m-данных.
    Нарушение = фактическое кол-во свечей отличается от ожидаемого более чем на 10%.
    При нарушении — удаляет все агрегированные TF и пересчитывает из 1m.
    Запускается автоматически при каждом старте системы.
    """
    log.info("Проверка целостности свечных данных...")
    repaired = 0

    for symbol in symbols:
        count_1m = await repo.count(symbol, "1m")
        if count_1m == 0:
            continue

        violations = []
        for tf, tf_min in AGG_TFS.items():
            actual = await repo.count(symbol, tf)
            expected = count_1m // tf_min
            if expected == 0:
                continue
            # Отклонение > 10% от ожидаемого — нарушение (слишком мало или слишком много)
            deviation = abs(actual - expected) / expected
            if deviation > 0.10:
                violations.append(
                    f"{tf}: факт={actual:,} ожид≈{expected:,} ({deviation:.0%})"
                )

        if not violations:
            log.info(f"{symbol}: OK ({count_1m:,} 1m)")
            continue

        log.warning(f"{symbol}: нарушения пропорций — {'; '.join(violations)}")
        log.info(f"{symbol}: пересчёт всех TF из {count_1m:,} 1m-свечей...")

        for tf in AGG_TFS:
            await repo.delete_timeframe(symbol, tf)

        candles_1m = await repo.get_latest(symbol=symbol, timeframe="1m", limit=10_000_000)
        for tf, tf_min in AGG_TFS.items():
            agg = _aggregate_1m(candles_1m, tf, tf_min)
            if agg:
                await repo.upsert_many(agg)
                log.info(f"  {symbol} {tf}: {len(agg):,}")
        repaired += 1

    if repaired:
        log.info(f"Авторемонт завершён: исправлено {repaired} символов")
    else:
        log.info("Целостность данных в норме")


# ── Обновление свежих свечей из REST (исправляет WS-артефакты) ───────────────

REFRESH_PAGES = 2       # кол-во страниц по MAX_PER_REQUEST (2 × 1440 = 48 часов)


async def refresh_recent(
    symbols: list[str],
    rest_client: BingXRestClient,
    repo: CandlesRepository,
) -> None:
    """
    Перезаписывает последние 48 часов 1m-свечей из REST API и пересчитывает агрегаты.

    Зачем: live WS-свечи снимаются в момент детектирования закрытия (по смене
    open_time следующего тика) — биржа ещё может дообрабатывать последние сделки,
    поэтому volume и цена WS-свечей немного отличаются от финальных REST-значений.
    Два запроса по 1440 свечей = полное покрытие за 48 часов.
    """
    page_ms = MAX_PER_REQUEST * 60 * 1000  # 1440 минут в мс
    log.info(f"Обновление последних {REFRESH_PAGES * MAX_PER_REQUEST} мин свечей из REST...")
    for symbol in symbols:
        try:
            now_ms = int(time.time() * 1000)
            all_candles: list[Candle] = []
            end_ms = now_ms
            for _ in range(REFRESH_PAGES):
                start_ms = end_ms - page_ms
                chunk = await rest_client.fetch_klines(
                    symbol, "1m", limit=MAX_PER_REQUEST,
                    start_time=start_ms, end_time=end_ms,
                )
                if chunk:
                    all_candles.extend(chunk)
                end_ms = start_ms
                await asyncio.sleep(REQUEST_SLEEP)

            if not all_candles:
                continue
            await repo.upsert_many(all_candles)

            for tf, tf_min in AGG_TFS.items():
                agg = _aggregate_1m(all_candles, tf, tf_min)
                if agg:
                    await repo.upsert_many(agg)

            log.info(f"{symbol}: обновлено {len(all_candles)} 1m-свечей + агрегаты")
            await asyncio.sleep(0.3)
        except Exception as e:
            log.error(f"Ошибка обновления {symbol}: {e}")


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
    stop_flag: list[bool] | None = None,
    resume_end_ms: int | None = None,
) -> None:
    """
    Загружает исторические 1m-свечи за указанный период, агрегирует все TF.
    Публикует backfill.progress и backfill.complete/error.

    stop_flag  — мутируемый список [bool]; установите stop_flag[0] = True для мягкой остановки.
    resume_end_ms — если задан, начинаем загрузку с этой позиции (для возобновления).
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
    # resume_end_ms позволяет продолжить с сохранённой позиции
    end_ms   = resume_end_ms if resume_end_ms is not None else now_ms
    page_dur = MAX_PER_REQUEST * 60 * 1000  # 1m × MAX_PER_REQUEST
    done     = 0
    total_saved = 0
    # buffer — очищается каждые CHECKPOINT страниц (только для checkpoint-сохранений в БД)
    buffer: list[Candle] = []
    # all_1m_agg — никогда не очищается, используется для финальной агрегации из памяти
    all_1m_agg: list[Candle] = []
    CHECKPOINT = 10  # сохраняем в БД каждые N страниц

    async def _flush(buf: list[Candle]) -> None:
        """Сохраняет накопленный буфер 1m-свечей в БД."""
        if buf:
            await repo.upsert_many(buf)

    try:
        while end_ms > start_ms:
            # Проверяем флаг остановки
            if stop_flag is not None and stop_flag[0]:
                log.info(f"[{task_id}] Бэкфилл остановлен по запросу пользователя (end_ms={end_ms})")
                # Сохраняем буфер и публикуем паузу
                if buffer:
                    await _flush(buffer)
                    total_saved += len(buffer)
                    buffer.clear()
                await bus.publish("backfill.progress", {
                    "task_id": task_id, "symbol": symbol, "period": period,
                    "fetched": done, "total": total_pages,
                    "percent": min(95, int(done / total_pages * 100)),
                    "current_tf": "1m", "status": "paused",
                    "checkpoint_end_ms": end_ms,
                    "total_saved": total_saved,
                })
                return

            req_start = max(start_ms, end_ms - page_dur)
            try:
                chunk = await rest_client.fetch_klines(
                    symbol, "1m",
                    limit=MAX_PER_REQUEST,
                    start_time=req_start,
                    end_time=end_ms,
                )
                if chunk:
                    buffer.extend(chunk)
                    all_1m_agg.extend(chunk)
            except Exception as e:
                log.warning(f"[{task_id}] Ошибка запроса {symbol} 1m: {e}")

            end_ms = req_start
            done += 1

            # Чекпоинт: сохраняем накопленный буфер каждые CHECKPOINT страниц
            if done % CHECKPOINT == 0 and buffer:
                await _flush(buffer)
                total_saved += len(buffer)
                buffer.clear()
                log.info(f"[{task_id}] Чекпоинт: сохранено {total_saved:,} 1m-свечей")

            # 95% = загрузка, последние 5% = агрегация
            percent = min(95, int(done / total_pages * 100))

            await bus.publish("backfill.progress", {
                "task_id": task_id,
                "symbol": symbol,
                "period": period,
                "fetched": done,
                "total": total_pages,
                "percent": percent,
                "current_tf": "1m",
                "status": "running",
                "total_saved": total_saved,
                "checkpoint_end_ms": end_ms,
            })

            await asyncio.sleep(REQUEST_SLEEP)

        # Сохраняем остаток буфера
        await _flush(buffer)
        total_saved += len(buffer)
        buffer.clear()

        # Агрегируем все TF из накопленных в памяти 1m-свечей (не читаем из БД)
        log.info(f"[{task_id}] Получено {len(all_1m_agg):,} 1m-свечей в памяти, агрегируем все TF...")

        for i, (tf, tf_min) in enumerate(AGG_TFS.items()):
            agg_percent = 95 + i  # 95, 96, 97 … для каждого TF
            await bus.publish("backfill.progress", {
                "task_id": task_id, "symbol": symbol, "period": period,
                "fetched": done, "total": total_pages, "percent": agg_percent,
                "current_tf": tf, "status": "running",
                "total_saved": total_saved,
            })
            agg = _aggregate_1m(all_1m_agg, tf, tf_min)
            if agg:
                await repo.upsert_many(agg)

    except asyncio.CancelledError:
        # При отмене — сохраняем то что успели накопить
        if buffer:
            await _flush(buffer)
            log.warning(f"[{task_id}] Бэкфилл отменён, сохранено {total_saved + len(buffer):,} 1m-свечей")
        else:
            log.warning(f"[{task_id}] Бэкфилл отменён")
        raise
    except Exception as e:
        if buffer:
            await _flush(buffer)
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
        "total_fetched": len(all_1m_agg),
        "total_saved": total_saved,
        "status": "complete",
    })
    log.info(f"[{task_id}] Бэкфилл {symbol} завершён: {len(all_1m_agg)} 1m-свечей + агрегаты")
