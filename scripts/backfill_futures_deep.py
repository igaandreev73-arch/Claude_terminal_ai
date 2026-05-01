"""
Глубокий backfill futures 1m — загружает весь доступный период с BingX v3 API.

Стратегия:
- Использует v3 Swap /openApi/swap/v3/quote/klines (516 дней глубины для 1m)
- Загружает пачками по 1440 свечей (1 день)
- Задержка 0.1 сек между запросами (10 запросов/сек — с запасом от rate limit)
- Сохраняет в БД с market_type='futures'
- При ошибке: retry x3 с паузой 5 сек

Запуск: python scripts/backfill_futures_deep.py
"""
import asyncio
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import aiohttp
import certifi
import ssl

DB_PATH = Path("/opt/collector/data/terminal.db")
BASE_URL = "https://open-api.bingx.com"
ENDPOINT = "/openApi/swap/v3/quote/klines"

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
BATCH_MS = 1440 * 60 * 1000  # 1440 минут = 1 день
DELAY = 0.1  # 10 запросов/сек
RETRY = 3
PAUSE = 5

# Максимальная глубина: 2024-11-30 16:00 UTC = 1732982400000
START_MS = 1732982400000  # 2024-11-30 16:00 UTC
NOW_MS = int(time.time() * 1000)

stats = {"fetched": 0, "written": 0, "errors": 0, "retries": 0}


def _ssl():
    return ssl.create_default_context(cafile=certifi.where())


def _sym(s):
    return s.replace("/", "-")


async def fetch(session, symbol, start_ms, end_ms, attempt=0):
    params = {
        "symbol": _sym(symbol),
        "interval": "1m",
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 1440,
    }
    try:
        async with session.get(
            BASE_URL + ENDPOINT,
            params=params,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            data = await r.json()
            code = data.get("code", 0)
            if code != 0:
                msg = data.get("msg", "")[:60]
                if attempt < RETRY:
                    stats["retries"] += 1
                    print(f"  Retry {attempt+1}/{RETRY} {symbol}: {msg}", flush=True)
                    await asyncio.sleep(PAUSE)
                    return await fetch(session, symbol, start_ms, end_ms, attempt + 1)
                print(f"  FAIL {symbol}: {msg}", flush=True)
                stats["errors"] += 1
                return []
            return data.get("data", [])
    except Exception as e:
        if attempt < RETRY:
            stats["retries"] += 1
            await asyncio.sleep(PAUSE)
            return await fetch(session, symbol, start_ms, end_ms, attempt + 1)
        print(f"  Exception {symbol}: {e}", flush=True)
        stats["errors"] += 1
        return []


def write_batch(symbol, candles):
    """Записывает батч свечей в БД."""
    if not candles:
        return 0
    written = 0
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now_ts = int(time.time())
    for c in candles:
        try:
            open_time = int(c["time"])
            open_p = float(c["open"])
            high = float(c["high"])
            low = float(c["low"])
            close = float(c["close"])
            volume = float(c["volume"])
            cur.execute(
                """INSERT OR IGNORE INTO candles
                   (symbol, timeframe, open_time, market_type,
                    open, high, low, close, volume,
                    is_closed, source, data_trust_score, created_at)
                   VALUES (?, '1m', ?, 'futures',
                           ?, ?, ?, ?, ?,
                           1, 'futures_v3', 99, ?)""",
                (symbol, open_time, open_p, high, low, close, volume, now_ts),
            )
            if cur.rowcount > 0:
                written += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return written


async def backfill_symbol(session, symbol):
    """Загружает все данные для одного символа с START_MS до NOW."""
    print(f"\n{'='*60}", flush=True)
    print(f"📈 {symbol}", flush=True)
    print(f"   Период: {datetime.utcfromtimestamp(START_MS/1000).strftime('%Y-%m-%d')} -> "
          f"{datetime.utcfromtimestamp(NOW_MS/1000).strftime('%Y-%m-%d')}", flush=True)

    cursor = START_MS
    total = 0
    batches = 0
    total_batches = (NOW_MS - START_MS) // BATCH_MS
    print(f"   Всего батчей: ~{total_batches}", flush=True)

    while cursor < NOW_MS:
        end = min(cursor + BATCH_MS, NOW_MS)
        candles = await fetch(session, symbol, cursor, end)
        if candles:
            w = write_batch(symbol, candles)
            total += w
            stats["fetched"] += len(candles)
            stats["written"] += w

        cursor = end
        batches += 1

        # Прогресс каждые 50 батчей
        if batches % 50 == 0:
            pct = (cursor - START_MS) / (NOW_MS - START_MS) * 100
            dt = datetime.utcfromtimestamp(cursor / 1000).strftime("%Y-%m-%d")
            elapsed = time.time() - t0
            rate = stats["fetched"] / max(elapsed, 1)
            eta = (total_batches - batches) * DELAY
            print(f"   {dt} {pct:.0f}% | записано: {stats['written']:,} | "
                  f"{rate:.0f} св/сек | ETA: {eta:.0f}с", flush=True)

        await asyncio.sleep(DELAY)

    elapsed = time.time() - t0
    print(f"   ✅ {symbol} ГОТОВО: {total:,} свечей за {elapsed:.0f} сек", flush=True)
    return total


async def main():
    global t0
    print("=" * 60, flush=True)
    print("ГЛУБОКИЙ BACKFILL FUTURES 1m", flush=True)
    print(f"Endpoint: v3 Swap /openApi/swap/v3/quote/klines", flush=True)
    print(f"Период: {datetime.utcfromtimestamp(START_MS/1000).strftime('%Y-%m-%d')} -> "
          f"{datetime.utcfromtimestamp(NOW_MS/1000).strftime('%Y-%m-%d')}", flush=True)
    print(f"Символы: {', '.join(SYMBOLS)}", flush=True)
    print(f"Задержка: {DELAY}с = {1/DELAY:.0f} запросов/сек", flush=True)
    print("=" * 60, flush=True)

    ctx = _ssl()
    connector = aiohttp.TCPConnector(ssl=ctx)
    async with aiohttp.ClientSession(connector=connector) as session:
        for sym in SYMBOLS:
            t0 = time.time()
            await backfill_symbol(session, sym)

    print("\n" + "=" * 60, flush=True)
    print(f"📊 ИТОГИ", flush=True)
    print(f"   Загружено: {stats['fetched']:,} свечей", flush=True)
    print(f"   Записано:  {stats['written']:,} свечей", flush=True)
    print(f"   Повторов:  {stats['retries']}", flush=True)
    print(f"   Ошибок:    {stats['errors']}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
