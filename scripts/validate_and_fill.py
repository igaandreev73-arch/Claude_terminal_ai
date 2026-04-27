"""
Валидация и заполнение пропусков.
Использует Futures API (нет ограничения 7 дней).
Также валидирует цены онлайн-свечей.
"""
import asyncio, sqlite3, time, sys
from datetime import datetime
from pathlib import Path
import aiohttp, certifi, ssl

DB_PATH  = Path("/opt/collector/data/terminal.db")
# Futures API - нет ограничения по периоду
FUTURES_URL = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
# Spot API - только последние 7 дней
SPOT_URL    = "https://open-api.bingx.com/openApi/spot/v2/market/kline"
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

stats = {"gaps_found": 0, "candles_fetched": 0, "candles_written": 0,
         "errors": 0, "price_mismatches": 0, "price_ok": 0}

def _ssl_ctx():
    return ssl.create_default_context(cafile=certifi.where())

def _bingx_symbol(sym: str) -> str:
    return sym.replace("/", "-")

async def fetch_futures_klines(session, symbol: str, start_ms: int, end_ms: int):
    """Futures API — длинная история, батч до 1440 свечей."""
    sym = _bingx_symbol(symbol)
    params = {"symbol": sym, "interval": "1m",
              "startTime": start_ms, "endTime": end_ms, "limit": 1440}
    try:
        async with session.get(FUTURES_URL, params=params,
                               timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200:
                stats["errors"] += 1; return []
            data = await r.json()
            if data.get("code") != 0:
                print(f"    Futures API: {data.get('msg')}", flush=True)
                stats["errors"] += 1; return []
            return data.get("data", [])
    except Exception as e:
        print(f"    Fetch error {symbol}: {e}", flush=True)
        stats["errors"] += 1; return []

async def fetch_spot_klines(session, symbol: str, start_ms: int, end_ms: int):
    """Spot API — только последние 7 дней."""
    sym = _bingx_symbol(symbol)
    params = {"symbol": sym, "interval": "1m",
              "startTime": start_ms, "endTime": end_ms, "limit": 1000}
    try:
        async with session.get(SPOT_URL, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                stats["errors"] += 1; return []
            data = await r.json()
            if data.get("code") != 0:
                stats["errors"] += 1; return []
            return data.get("data", [])
    except Exception as e:
        stats["errors"] += 1; return []

def find_gaps(symbol: str) -> list[tuple[int, int, int]]:
    """Возвращает (gap_start, gap_end, missing_minutes)."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT open_time FROM candles WHERE symbol=? AND timeframe='1m' ORDER BY open_time", (symbol,))
    times = [r[0] for r in cur.fetchall()]
    conn.close()
    gaps = []
    for i in range(1, len(times)):
        diff = (times[i] - times[i-1]) / 60000
        if diff > 1.5:
            gaps.append((times[i-1] + 60000, times[i], int(diff)-1))
    return gaps

def write_candles(symbol: str, raw: list, source: str = "repair") -> int:
    if not raw: return 0
    written = 0
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    for c in raw:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO candles
                (symbol, timeframe, open_time, market_type, open, high, low, close, volume,
                 is_closed, source, data_trust_score, created_at)
                VALUES (?, '1m', ?, 'spot', ?, ?, ?, ?, ?, 1, ?, 90, ?)
            """, (symbol, int(c[0]), float(c[1]), float(c[2]), float(c[3]),
                  float(c[4]), float(c[5]), source, int(time.time())))
            if cur.rowcount > 0: written += 1
        except Exception as e:
            if str(e) != '0': print(f"    Write error: {e}", flush=True)
    conn.commit(); conn.close()
    return written

async def fill_symbol(session, symbol: str):
    gaps = find_gaps(symbol)
    if not gaps:
        print(f"  {symbol}: пропусков нет ✅", flush=True); return
    stats["gaps_found"] += len(gaps)
    now_ms = time.time() * 1000
    seven_days_ms = 7 * 24 * 3600 * 1000
    print(f"  {symbol}: {len(gaps)} пропусков", flush=True)
    for gap_start, gap_end, missing in gaps:
        ts = datetime.utcfromtimestamp(gap_start/1000).strftime("%m-%d %H:%M")
        # Решаем какой API использовать
        use_futures = (now_ms - gap_start) > seven_days_ms
        api_name = "Futures" if use_futures else "Spot"
        fetched_total = 0
        cursor = gap_start
        while cursor < gap_end:
            batch_end = min(cursor + 1440 * 60000, gap_end)
            if use_futures:
                candles = await fetch_futures_klines(session, symbol, cursor, batch_end)
            else:
                candles = await fetch_spot_klines(session, symbol, cursor, batch_end)
            if candles:
                written = write_candles(symbol, candles, source="repair")
                fetched_total += len(candles)
                stats["candles_fetched"] += len(candles)
                stats["candles_written"] += written
            cursor = batch_end
            await asyncio.sleep(0.2)
        print(f"    {ts} ({missing}мин) [{api_name}]: загружено {fetched_total}", flush=True)

async def validate_prices(session, symbol: str):
    """Проверяем последние онлайн-свечи (не backfill/repair)."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cutoff = int((time.time() - 3600) * 1000)  # последний час
    cur.execute("""
        SELECT open_time, close FROM candles
        WHERE symbol=? AND timeframe='1m' AND source NOT IN ('backfill','repair')
        AND open_time > ? ORDER BY open_time DESC LIMIT 5
    """, (symbol, cutoff))
    rows = cur.fetchall(); conn.close()
    if not rows:
        print(f"  {symbol}: нет онлайн-свечей за последний час", flush=True); return
    ok = 0; fail = 0
    for open_time, db_close in rows:
        candles = await fetch_spot_klines(session, symbol, open_time, open_time + 60000)
        if not candles: continue
        api_close = float(candles[0][4])
        diff_pct = abs(api_close - float(db_close)) / float(db_close) * 100
        if diff_pct > 0.05:
            ts = datetime.utcfromtimestamp(open_time/1000).strftime("%H:%M")
            print(f"    ⚠️  {symbol} {ts}: DB={db_close:.4f} API={api_close:.4f} Δ={diff_pct:.4f}%", flush=True)
            fail += 1; stats["price_mismatches"] += 1
        else:
            ok += 1; stats["price_ok"] += 1
        await asyncio.sleep(0.1)
    print(f"  {symbol}: ✅ {ok} совпадений, ❌ {fail} несоответствий", flush=True)

async def main():
    print("=" * 50, flush=True)
    print("ВАЛИДАЦИЯ И ЗАПОЛНЕНИЕ ПРОПУСКОВ", flush=True)
    print(f"UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("=" * 50, flush=True)
    ctx  = _ssl_ctx()
    conn = aiohttp.TCPConnector(ssl=ctx)
    async with aiohttp.ClientSession(connector=conn) as session:
        print("\n--- ШАГ 1: ЗАПОЛНЕНИЕ ПРОПУСКОВ ---", flush=True)
        for sym in SYMBOLS:
            await fill_symbol(session, sym)
            await asyncio.sleep(0.3)
        print("\n--- ШАГ 2: ВАЛИДАЦИЯ ЦЕН ---", flush=True)
        for sym in SYMBOLS:
            await validate_prices(session, sym)
            await asyncio.sleep(0.3)
    print("\n" + "=" * 50, flush=True)
    print(f"Пропусков:    {stats['gaps_found']}", flush=True)
    print(f"Загружено:    {stats['candles_fetched']:,}", flush=True)
    print(f"Записано:     {stats['candles_written']:,}", flush=True)
    print(f"Цены OK:      {stats['price_ok']}", flush=True)
    print(f"Несоответствий: {stats['price_mismatches']}", flush=True)
    print(f"Ошибок:       {stats['errors']}", flush=True)
    print("=" * 50, flush=True)

if __name__ == "__main__":
    asyncio.run(main())