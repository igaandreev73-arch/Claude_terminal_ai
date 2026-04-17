"""
Загрузка исторических данных с BingX.
Запуск: python scripts/sync_history.py --symbols BTC/USDT ETH/USDT --days 30

Загружает 1m-свечи за указанное количество дней и сохраняет в БД.
"""
import asyncio
import argparse
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.event_bus import EventBus
from core.logger import get_logger, setup_logger
from data.bingx_rest import BingXRestClient
from data.rate_limit_guard import RateLimitGuard
from storage.database import init_db, close_db
from storage.repositories.candles_repo import CandlesRepository

log = get_logger("sync_history")

BATCH_SIZE = 1440       # максимум за один запрос (1 день)
MS_PER_MINUTE = 60_000


async def sync_symbol(
    client: BingXRestClient,
    repo: CandlesRepository,
    symbol: str,
    days: int,
) -> None:
    log.info(f"Синхронизация {symbol} за {days} дней...")
    end_time = int(time.time() * 1000)
    start_time = end_time - days * 24 * 60 * MS_PER_MINUTE

    total = 0
    current = start_time

    while current < end_time:
        batch_end = min(current + BATCH_SIZE * MS_PER_MINUTE, end_time)
        try:
            candles = await client.fetch_klines(
                symbol=symbol,
                timeframe="1m",
                limit=BATCH_SIZE,
                start_time=current,
                end_time=batch_end,
            )
            if candles:
                saved = await repo.upsert_many(candles)
                total += saved
                log.info(f"{symbol}: сохранено {saved} свечей (всего: {total})")
                current = candles[-1].open_time + MS_PER_MINUTE
            else:
                current = batch_end
        except Exception as e:
            log.error(f"Ошибка при загрузке {symbol}: {e}")
            await asyncio.sleep(5)
            current = batch_end

    log.info(f"{symbol}: синхронизация завершена, итого {total} свечей")


async def main(symbols: list[str], days: int) -> None:
    setup_logger()
    await init_db()

    bus = EventBus()
    guard = RateLimitGuard()
    client = BingXRestClient(bus, guard)
    repo = CandlesRepository()

    await client.start()
    try:
        for symbol in symbols:
            await sync_symbol(client, repo, symbol, days)
    finally:
        await client.stop()
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Синхронизация исторических данных BingX")
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT"], help="Торговые пары")
    parser.add_argument("--days", type=int, default=30, help="Количество дней истории")
    args = parser.parse_args()
    asyncio.run(main(args.symbols, args.days))
