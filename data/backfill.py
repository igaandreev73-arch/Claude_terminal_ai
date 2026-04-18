"""
Исторический backfill свечей.

При старте системы проверяет количество свечей в БД и догружает
недостающую историю через BingX REST API для каждого символа и таймфрейма.
"""
from __future__ import annotations

import asyncio

from core.logger import get_logger
from data.bingx_rest import BingXRestClient
from storage.repositories.candles_repo import CandlesRepository

log = get_logger("Backfill")

# Сколько свечей хотим иметь в БД для каждого таймфрейма
TARGET_CANDLES: dict[str, int] = {
    "1m":  1440,   # ~1 день
    "5m":  1440,   # ~5 дней
    "15m": 1000,   # ~10 дней
    "1h":  720,    # ~30 дней
    "4h":  500,    # ~83 дня
    "1d":  365,    # ~1 год
}

# BingX возвращает максимум 1440 свечей за запрос
MAX_PER_REQUEST = 1440


async def run_backfill(
    symbols: list[str],
    rest_client: BingXRestClient,
    repo: CandlesRepository,
) -> None:
    """Запускает бэкфилл для всех символов и таймфреймов."""
    log.info(f"Запуск исторического бэкфилла для {len(symbols)} символов...")

    for symbol in symbols:
        for tf, target in TARGET_CANDLES.items():
            try:
                await _backfill_one(symbol, tf, target, rest_client, repo)
                # Небольшая пауза между запросами чтобы не давить rate limit
                await asyncio.sleep(0.3)
            except Exception as e:
                log.error(f"Ошибка бэкфилла {symbol} {tf}: {e}")

    log.info("Бэкфилл завершён")


async def _backfill_one(
    symbol: str,
    tf: str,
    target: int,
    rest_client: BingXRestClient,
    repo: CandlesRepository,
) -> None:
    existing = await repo.count(symbol, tf)
    if existing >= target:
        log.debug(f"{symbol} {tf}: {existing} свечей — бэкфилл не нужен")
        return

    need = target - existing
    # Запрашиваем нужное количество (не больше лимита API)
    limit = min(need, MAX_PER_REQUEST)

    log.info(f"{symbol} {tf}: в БД {existing}, нужно {target} → загружаем {limit} свечей")
    candles = await rest_client.fetch_klines(symbol, tf, limit=limit)

    if not candles:
        log.warning(f"{symbol} {tf}: API вернул 0 свечей")
        return

    saved = await repo.upsert_many(candles)
    log.info(f"{symbol} {tf}: сохранено {saved} свечей")
