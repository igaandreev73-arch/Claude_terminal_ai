"""
Clean spot backfill через /openApi/market/his/v1/kline
- Открытый endpoint (без ключа)
- Лимит: 30 запросов/сек -> задержка 0.04 сек
- Батч: 1000 свечей = ~16.6 часов на батч
- При ошибке: пауза 5 сек и retry x3
"""
import asyncio, sqlite3, time, sys, hmac, hashlib, os
from datetime import datetime
from pathlib import Path
import aiohttp, certifi, ssl

DB_PATH  = Path("/opt/collector/data/terminal.db")
HIS_URL    = "https://open-api.bingx.com/openApi/market/his/v1/kline"
# Читаем ключи напрямую из .env файла
def _load_env():
    key = ""; secret = ""
    try:
        env_path = Path("/opt/collector/.env")
        for line in env_path.read_text().splitlines():
            if line.startswith("BINGX_API_KEY="):
                key = line.split("=", 1)[1].strip()
            elif line.startswith("BINGX_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"  .env read error: {e}", flush=True)
    return key, secret

API_KEY, API_SECRET = _load_env()

def _sign(params: dict) -> str:
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
SYMBOLS  = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
BATCH_MS = 1000 * 60 * 1000   # 1000 минут = 16.6 часов
DELAY    = 0.04                 # 25 запросов/сек (с запасом от 30)
RETRY    = 3                    # попыток при ошибке
PAUSE    = 5                    # пауза при ошибке (сек)

stats = {"fetched": 0, "written": 0, "errors": 0, "retries": 0}

def _ssl(): return ssl.create_default_context(cafile=certifi.where())
def _sym(s): return s.replace("/", "-")

async def fetch(session, symbol, start_ms, end_ms, attempt=0):
    params = {"symbol": _sym(symbol), "interval": "1m",
              "startTime": start_ms, "endTime": end_ms, "limit": 1000}
    try:
        async with session.get(HIS_URL, params=params,
                               timeout=aiohttp.ClientTimeout(total=30)) as r:
            data = await r.json()
            code = data.get("code")
            if code != 0:
                msg = data.get("msg", "")[:60]
                if attempt < RETRY:
                    stats["retries"] += 1
                    print(f"  Retry {attempt+1}/{RETRY} {symbol}: {msg}", flush=True)
                    await asyncio.sleep(PAUSE)
                    return await fetch(session, symbol, start_ms, end_ms, attempt+1)
                print(f"  FAIL {symbol}: {msg}", flush=True)
                stats["errors"] += 1
                return []
            return data.get("data", [])
    except Exception as e:
        if attempt < RETRY:
            stats["retries"] += 1
            await asyncio.sleep(PAUSE)
            return await fetch(session, symbol, start_ms, end_ms, attempt+1)
        print(f"  Exception {symbol}: {e}", flush=True)
        stats["errors"] += 1
        return []

def clean_spot():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM candles WHERE market_type='spot'")
    total = cur.fetchone()[0]
    cur.execute("DELETE FROM candles WHERE market_type='spot'")
    deleted = cur.rowcount
    conn.commit(); conn.close()
    return total, deleted

def write(symbol, raw):
    if not raw: return 0
    written = 0
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    for c in raw:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO candles
                (symbol, timeframe, open_time, market_type,
                 open, high, low, close, volume,
                 is_closed, source, data_trust_score, created_at)
                VALUES (?, '1m', ?, 'spot', ?, ?, ?, ?, ?, 1, 'spot_his', 99, ?)
            """, (symbol, int(c[0]), float(c[1]), float(c[2]),
                  float(c[3]), float(c[4]), float(c[5]), int(time.time())))
            if cur.rowcount > 0: written += 1
        except Exception: pass
    conn.commit(); conn.close()
    return written

async def backfill_symbol(session, symbol, from_ms, to_ms):
    cursor = from_ms; total = 0; batches = 0
    while cursor < to_ms:
        end = min(cursor + BATCH_MS, to_ms)
        candles = await fetch(session, symbol, cursor, end)
        if candles:
            w = write(symbol, candles)
            total += w
            stats["fetched"] += len(candles)
            stats["written"] += w
        cursor = end; batches += 1
        # Прогресс каждые 50 батчей (~35 дней)
        if batches % 50 == 0:
            pct = (cursor - from_ms) / (to_ms - from_ms) * 100
            dt  = datetime.utcfromtimestamp(cursor/1000).strftime("%Y-%m-%d")
            print(f"  {symbol}: {dt} {pct:.0f}% | total={stats['written']:,}", flush=True)
        await asyncio.sleep(DELAY)
    return total

async def main():
    from_ms = 1730073600000  # 2025-10-28 00:00 UTC
    to_ms   = int(time.time() * 1000) - 120_000

    from_dt = datetime.utcfromtimestamp(from_ms/1000).strftime("%Y-%m-%d")
    to_dt   = datetime.utcfromtimestamp(to_ms/1000).strftime("%Y-%m-%d")
    days    = (to_ms - from_ms) / 86400000
    total_batches = int(days * 24 * 60 / 1000 * len(SYMBOLS))
    eta_sec = total_batches * DELAY

    print("=" * 55, flush=True)
    print("CLEAN SPOT BACKFILL — /openApi/market/his/v1/kline", flush=True)
    print(f"Период: {from_dt} -> {to_dt} ({days:.0f} дней)", flush=True)
    print(f"Скорость: 1/{DELAY}сек = {1/DELAY:.0f} запросов/сек", flush=True)
    print(f"Батчей примерно: {total_batches} | ETA: ~{eta_sec:.0f} сек ({eta_sec/60:.1f} мин)", flush=True)
    print("=" * 55, flush=True)

    print(f"\n--- Шаг 1: Очистка spot свечей ---", flush=True)
    total, deleted = clean_spot()
    print(f"  Удалено: {deleted:,} из {total:,}", flush=True)

    print(f"\n--- Шаг 2: Загрузка ---", flush=True)
    ctx  = _ssl()
    conn = aiohttp.TCPConnector(ssl=ctx)
    async with aiohttp.ClientSession(connector=conn) as session:
        for sym in SYMBOLS:
            t0 = time.time()
            print(f"\n{sym}:", flush=True)
            w = await backfill_symbol(session, sym, from_ms, to_ms)
            elapsed = time.time() - t0
            print(f"  {sym} ГОТОВО: записано {w:,} за {elapsed:.0f} сек", flush=True)

    print("\n" + "=" * 55, flush=True)
    print(f"Загружено:  {stats['fetched']:,}", flush=True)
    print(f"Записано:   {stats['written']:,}", flush=True)
    print(f"Повторов:   {stats['retries']}", flush=True)
    print(f"Ошибок:     {stats['errors']}", flush=True)
    print("=" * 55, flush=True)

if __name__ == "__main__":
    asyncio.run(main())