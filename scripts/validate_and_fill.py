"""
Валидация и заполнение пропусков в SPOT свечах.

Алгоритм:
  1. Сканируем 1m свечи каждой пары — находим пропуски > 90 секунд
  2. Для каждого пропуска запрашиваем SPOT API батчами по 7 дней
     (BingX ограничивает один запрос диапазоном <= 7 дней)
  3. Записываем недостающие свечи с source='repair'
  4. Валидируем цены: последние онлайн-свечи сравниваем с API

Расписание (автозапуск):
  - Каждые 6 часов (через cron или systemd timer)
  - При запуске вручную: python3.11 scripts/validate_and_fill.py

Запускать ТОЛЬКО через Spot API — фьючерсные цены отличаются
и не подходят для заполнения спотовой истории.
"""
import asyncio, sqlite3, time, sys
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp, certifi, ssl

DB_PATH  = Path("/opt/collector/data/terminal.db")
SPOT_URL = "https://open-api.bingx.com/openApi/spot/v2/market/kline"
SYMBOLS  = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

# BingX ограничение: максимум 7 дней на один запрос
MAX_WINDOW_MS  = 7 * 24 * 60 * 60 * 1000   # 7 дней в мс
BATCH_SIZE     = 1000                         # свечей за запрос

stats = {
    "gaps_found": 0, "gaps_filled": 0,
    "candles_fetched": 0, "candles_written": 0,
    "price_ok": 0, "price_mismatch": 0,
    "api_errors": 0
}


def _ssl_ctx():
    return ssl.create_default_context(cafile=certifi.where())


def _sym(s: str) -> str:
    return s.replace("/", "-")


async def spot_klines(session, symbol: str, start_ms: int, end_ms: int) -> list:
    """
    Запрашивает 1m свечи через Spot API.
    ВАЖНО: end_ms - start_ms <= 7 дней (ограничение BingX).
    """
    params = {
        "symbol":    _sym(symbol),
        "interval":  "1m",
        "startTime": start_ms,
        "endTime":   min(end_ms, start_ms + MAX_WINDOW_MS),
        "limit":     BATCH_SIZE,
    }
    try:
        async with session.get(
            SPOT_URL, params=params,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as r:
            if r.status != 200:
                stats["api_errors"] += 1
                return []
            data = await r.json()
            if data.get("code") != 0:
                msg = data.get("msg", "")
                print(f"    [API] {symbol}: {msg}", flush=True)
                stats["api_errors"] += 1
                return []
            return data.get("data", [])
    except asyncio.TimeoutError:
        print(f"    [TIMEOUT] {symbol} {start_ms}", flush=True)
        stats["api_errors"] += 1
        return []
    except Exception as e:
        print(f"    [ERROR] {symbol}: {e}", flush=True)
        stats["api_errors"] += 1
        return []


def find_gaps(symbol: str) -> list[tuple[int, int, int]]:
    """
    Возвращает список (gap_start_ms, gap_end_ms, missing_minutes).
    gap_start_ms — первая недостающая минута
    gap_end_ms   — момент после пропуска (где следующая свеча)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute(
            "SELECT open_time FROM candles "
            "WHERE symbol=? AND timeframe='1m' ORDER BY open_time",
            (symbol,)
        )
        times = [r[0] for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        print(f"  [DB ERROR] {symbol}: {e}", flush=True)
        return []

    gaps = []
    for i in range(1, len(times)):
        diff_ms = times[i] - times[i - 1]
        if diff_ms > 90_000:  # пропуск > 90 секунд
            gap_start = times[i - 1] + 60_000   # следующая минута после последней свечи
            gap_end   = times[i]                  # момент следующей существующей свечи
            missing   = int(diff_ms / 60_000) - 1
            gaps.append((gap_start, gap_end, missing))
    return gaps


def write_candles(symbol: str, raw: list) -> int:
    """Записывает свечи в БД. Пропускает дубли (INSERT OR IGNORE)."""
    if not raw:
        return 0
    written = 0
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        now  = int(time.time())
        for c in raw:
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO candles
                    (symbol, timeframe, open_time, market_type,
                     open, high, low, close, volume,
                     is_closed, source, data_trust_score, created_at)
                    VALUES (?, '1m', ?, 'spot', ?, ?, ?, ?, ?, 1, 'repair', 90, ?)
                """, (
                    symbol, int(c[0]),
                    float(c[1]), float(c[2]), float(c[3]),
                    float(c[4]), float(c[5]),
                    now
                ))
                if cur.rowcount > 0:
                    written += 1
            except Exception as e:
                if str(e) != "0":
                    print(f"    [WRITE] {e}", flush=True)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [DB WRITE ERROR] {symbol}: {e}", flush=True)
    return written


async def fill_gap(session, symbol: str, gap_start: int, gap_end: int, missing: int):
    """
    Заполняет один пропуск батчами по 7 дней.
    Каждый батч: window <= 7 дней, limit <= 1000.
    """
    ts_s = datetime.utcfromtimestamp(gap_start / 1000).strftime("%Y-%m-%d %H:%M")
    ts_e = datetime.utcfromtimestamp(gap_end   / 1000).strftime("%Y-%m-%d %H:%M")
    print(f"    Пропуск {ts_s} -> {ts_e} ({missing} мин)", flush=True)

    cursor       = gap_start
    total_fetched = 0
    total_written = 0

    while cursor < gap_end:
        # Окно не более 7 дней И не более gap_end
        window_end = min(cursor + MAX_WINDOW_MS, gap_end)

        candles = await spot_klines(session, symbol, cursor, window_end)
        if candles:
            written = write_candles(symbol, candles)
            total_fetched += len(candles)
            total_written += written
            stats["candles_fetched"] += len(candles)
            stats["candles_written"] += written
            # Следующий батч начинается с последней полученной свечи + 1 мин
            last_ts = int(candles[-1][0])
            cursor  = last_ts + 60_000
        else:
            # Нет данных — двигаемся окном вперёд
            cursor = window_end

        await asyncio.sleep(0.25)   # rate limit

    print(f"      → загружено {total_fetched}, записано {total_written}", flush=True)
    if total_written > 0:
        stats["gaps_filled"] += 1


async def fill_symbol(session, symbol: str):
    """Находит и заполняет все пропуски для одной пары."""
    gaps = find_gaps(symbol)
    if not gaps:
        print(f"  {symbol}: пропусков нет ✅", flush=True)
        return

    stats["gaps_found"] += len(gaps)
    total_missing = sum(g[2] for g in gaps)
    print(f"  {symbol}: {len(gaps)} пропусков, ~{total_missing} недостающих мин", flush=True)

    for gap_start, gap_end, missing in gaps:
        await fill_gap(session, symbol, gap_start, gap_end, missing)
        await asyncio.sleep(0.3)


async def validate_prices(session, symbol: str, sample: int = 5):
    """
    Проверяет цены онлайн-свечей (source NOT IN repair/backfill)
    за последний час против Spot API.
    """
    try:
        cutoff = int((time.time() - 3600) * 1000)
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("""
            SELECT open_time, close FROM candles
            WHERE symbol=? AND timeframe='1m'
              AND source NOT IN ('backfill', 'repair')
              AND open_time > ?
            ORDER BY open_time DESC LIMIT ?
        """, (symbol, cutoff, sample))
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"  [DB VAL ERROR] {symbol}: {e}", flush=True)
        return

    if not rows:
        print(f"  {symbol}: нет онлайн-свечей за последний час", flush=True)
        return

    ok = fail = 0
    for open_time, db_close in rows:
        candles = await spot_klines(session, symbol, open_time, open_time + 60_000)
        if not candles:
            continue
        api_close = float(candles[0][4])
        db_close  = float(db_close)
        diff_pct  = abs(api_close - db_close) / db_close * 100 if db_close else 0
        if diff_pct > 0.05:
            ts = datetime.utcfromtimestamp(open_time / 1000).strftime("%H:%M")
            print(
                f"    ⚠️  {symbol} {ts}: "
                f"DB={db_close:.4f} API={api_close:.4f} Δ={diff_pct:.4f}%",
                flush=True
            )
            fail += 1
            stats["price_mismatch"] += 1
        else:
            ok += 1
            stats["price_ok"] += 1
        await asyncio.sleep(0.15)

    icon = "✅" if fail == 0 else "⚠️"
    print(f"  {symbol}: {icon} совпадений {ok}, несоответствий {fail}", flush=True)


async def main():
    start = time.time()
    print("=" * 55, flush=True)
    print("ВАЛИДАЦИЯ И ЗАПОЛНЕНИЕ ПРОПУСКОВ (SPOT)", flush=True)
    print(f"UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("Метод: Spot API батчами по 7 дней", flush=True)
    print("=" * 55, flush=True)

    ctx  = _ssl_ctx()
    conn = aiohttp.TCPConnector(ssl=ctx)

    async with aiohttp.ClientSession(connector=conn) as session:

        print("\n--- ШАГ 1: ПОИСК И ЗАПОЛНЕНИЕ ПРОПУСКОВ ---", flush=True)
        for sym in SYMBOLS:
            await fill_symbol(session, sym)
            await asyncio.sleep(0.5)

        print("\n--- ШАГ 2: ВАЛИДАЦИЯ ЦЕН (онлайн-свечи) ---", flush=True)
        for sym in SYMBOLS:
            await validate_prices(session, sym, sample=5)
            await asyncio.sleep(0.5)

    elapsed = time.time() - start
    print("\n" + "=" * 55, flush=True)
    print(f"Время выполнения:    {elapsed:.0f} сек", flush=True)
    print(f"Пропусков найдено:   {stats['gaps_found']}", flush=True)
    print(f"Пропусков заполнено: {stats['gaps_filled']}", flush=True)
    print(f"Свечей загружено:    {stats['candles_fetched']:,}", flush=True)
    print(f"Свечей записано:     {stats['candles_written']:,}", flush=True)
    print(f"Цены совпадают:      {stats['price_ok']}", flush=True)
    print(f"Несоответствий:      {stats['price_mismatch']}", flush=True)
    print(f"API ошибок:          {stats['api_errors']}", flush=True)
    print("=" * 55, flush=True)


if __name__ == "__main__":
    asyncio.run(main())