"""
Валидация и заполнение пропусков через Spot API.
BingX Spot ограничен 7 днями — запрашиваем последовательными батчами по 7 дней.
Валидирует цены онлайн-свечей (source != backfill/repair) vs текущий API.
"""
import asyncio, sqlite3, time, sys
from datetime import datetime, timezone
from pathlib import Path
import aiohttp, certifi, ssl

DB_PATH  = Path("/opt/collector/data/terminal.db")
SPOT_URL = "https://open-api.bingx.com/openApi/spot/v2/market/kline"
SYMBOLS  = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
SEVEN_DAYS_MS = 7 * 24 * 3600 * 1000

stats = {
    "gaps_found": 0, "candles_fetched": 0,
    "candles_written": 0, "errors": 0,
    "price_ok": 0, "price_fail": 0,
    "skipped_too_old": 0
}


def _ssl_ctx():
    return ssl.create_default_context(cafile=certifi.where())


def _sym(s: str) -> str:
    return s.replace("/", "-")


async def fetch_spot(session, symbol: str, start_ms: int, end_ms: int) -> list:
    """Spot API — батч до 1000 свечей, диапазон не более 7 дней."""
    params = {
        "symbol":    _sym(symbol),
        "interval":  "1m",
        "startTime": start_ms,
        "endTime":   end_ms,
        "limit":     1000,
    }
    try:
        async with session.get(
            SPOT_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as r:
            if r.status != 200:
                stats["errors"] += 1
                return []
            data = await r.json()
            if data.get("code") != 0:
                msg = data.get("msg", "")
                if "7 days" in msg or "range" in msg.lower():
                    pass  # ожидаемо — диапазон вне 7 дней
                else:
                    print(f"    API: {msg}", flush=True)
                stats["errors"] += 1
                return []
            return data.get("data", []) or []
    except Exception as e:
        print(f"    Fetch error {symbol}: {e}", flush=True)
        stats["errors"] += 1
        return []


def find_gaps(symbol: str) -> list[tuple[int, int, int]]:
    """(gap_start_ms, gap_end_ms, missing_minutes)"""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(
        "SELECT open_time FROM candles WHERE symbol=? AND timeframe='1m' ORDER BY open_time",
        (symbol,)
    )
    times = [r[0] for r in cur.fetchall()]
    conn.close()
    gaps = []
    for i in range(1, len(times)):
        diff = (times[i] - times[i-1]) / 60000
        if diff > 1.5:
            gaps.append((times[i-1] + 60000, times[i], int(diff) - 1))
    return gaps


def write_candles(symbol: str, raw: list) -> int:
    if not raw:
        return 0
    written = 0
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    now  = int(time.time())
    for c in raw:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO candles
                (symbol, timeframe, open_time, market_type, open, high, low, close, volume,
                 is_closed, source, data_trust_score, created_at)
                VALUES (?, '1m', ?, 'spot', ?, ?, ?, ?, ?, 1, 'repair', 90, ?)
            """, (
                symbol, int(c[0]),
                float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]),
                now
            ))
            if cur.rowcount > 0:
                written += 1
        except Exception as e:
            err = str(e)
            if err != "0":
                print(f"    Write err: {err}", flush=True)
    conn.commit()
    conn.close()
    return written


async def fill_symbol(session, symbol: str):
    """Заполняет пропуски батчами по 7 дней через Spot API."""
    gaps = find_gaps(symbol)
    if not gaps:
        print(f"  {symbol}: пропусков нет ✅", flush=True)
        return

    now_ms = int(time.time() * 1000)
    accessible = [(s, e, m) for s, e, m in gaps if (now_ms - s) <= SEVEN_DAYS_MS]
    skipped    = len(gaps) - len(accessible)

    stats["gaps_found"] += len(gaps)
    if skipped > 0:
        stats["skipped_too_old"] += skipped

    print(
        f"  {symbol}: {len(gaps)} пропусков "
        f"({len(accessible)} доступны через Spot API, {skipped} старше 7 дней — пропуск)",
        flush=True
    )

    for gap_start, gap_end, missing in accessible:
        ts_s = datetime.utcfromtimestamp(gap_start / 1000).strftime("%m-%d %H:%M")
        ts_e = datetime.utcfromtimestamp(gap_end   / 1000).strftime("%m-%d %H:%M")
        fetched_total = 0
        cursor = gap_start

        while cursor < gap_end:
            # Батч не более 7 дней и не более 1000 свечей (= ~16.6 часов)
            batch_end = min(cursor + 1000 * 60_000, gap_end)
            candles   = await fetch_spot(session, symbol, cursor, batch_end)
            if candles:
                written = write_candles(symbol, candles)
                fetched_total          += len(candles)
                stats["candles_fetched"] += len(candles)
                stats["candles_written"] += written
            cursor = batch_end
            await asyncio.sleep(0.25)

        print(f"    {ts_s}->{ts_e} ({missing}мин): загружено {fetched_total}", flush=True)


async def validate_prices(session, symbol: str, sample: int = 5):
    """
    Проверяем цены закрытия онлайн-свечей (source NOT IN backfill/repair)
    последнего часа против текущего Spot API.
    """
    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.cursor()
    cutoff = int((time.time() - 3600) * 1000)
    cur.execute("""
        SELECT open_time, close FROM candles
        WHERE symbol=? AND timeframe='1m'
          AND source NOT IN ('backfill','repair')
          AND open_time > ?
        ORDER BY open_time DESC LIMIT ?
    """, (symbol, cutoff, sample))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"  {symbol}: нет онлайн-свечей за последний час", flush=True)
        return

    ok = fail = 0
    for open_time, db_close in rows:
        candles = await fetch_spot(session, symbol, open_time, open_time + 60_000)
        if not candles:
            continue
        api_close = float(candles[0][4])
        db_close  = float(db_close)
        diff_pct  = abs(api_close - db_close) / db_close * 100 if db_close else 0

        if diff_pct > 0.05:
            ts = datetime.utcfromtimestamp(open_time / 1000).strftime("%H:%M")
            print(
                f"    ⚠️  {symbol} {ts}: "
                f"DB={db_close:.5f} API={api_close:.5f} Δ={diff_pct:.4f}%",
                flush=True
            )
            fail += 1
            stats["price_fail"] += 1
        else:
            ok += 1
            stats["price_ok"] += 1

        await asyncio.sleep(0.1)

    status = "✅" if fail == 0 else "⚠️ "
    print(f"  {symbol}: {status} {ok} OK, {fail} расхождений", flush=True)


async def main():
    print("=" * 52, flush=True)
    print("ВАЛИДАЦИЯ ДАННЫХ (Spot API, батчи 7 дней)", flush=True)
    print(f"UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("=" * 52, flush=True)

    ctx  = _ssl_ctx()
    conn = aiohttp.TCPConnector(ssl=ctx)

    async with aiohttp.ClientSession(connector=conn) as session:

        print("\n--- ШАГ 1: ЗАПОЛНЕНИЕ ПРОПУСКОВ ---", flush=True)
        for sym in SYMBOLS:
            await fill_symbol(session, sym)
            await asyncio.sleep(0.3)

        print("\n--- ШАГ 2: ВАЛИДАЦИЯ ЦЕН ОНЛАЙН-СВЕЧЕЙ ---", flush=True)
        for sym in SYMBOLS:
            await validate_prices(session, sym, sample=5)
            await asyncio.sleep(0.3)

    print("\n" + "=" * 52, flush=True)
    print(f"Пропусков найдено:      {stats['gaps_found']}", flush=True)
    print(f"  из них старше 7 дней: {stats['skipped_too_old']}", flush=True)
    print(f"Свечей загружено:       {stats['candles_fetched']:,}", flush=True)
    print(f"Свечей записано (новых):{stats['candles_written']:,}", flush=True)
    print(f"Цены совпали:           {stats['price_ok']}", flush=True)
    print(f"Цены расходятся:        {stats['price_fail']}", flush=True)
    print(f"Ошибок API:             {stats['errors']}", flush=True)
    print("=" * 52, flush=True)


if __name__ == "__main__":
    asyncio.run(main())