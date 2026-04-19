"""
Валидация данных: сравниваем свечи в БД с актуальными данными BingX API.

Для каждой пары берём 3 случайных окна по 50 свечей в разных частях истории,
сравниваем open/high/low/close/volume. Допуск на volume — 0.1% (биржи иногда
пересчитывают volume задним числом).

Запуск: python scripts/validate_candles.py
"""
import asyncio
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///data/terminal.db")

import aiohttp
from storage.database import init_db, get_session_factory
from storage.models import CandleModel
from sqlalchemy import select

BASE_URL = "https://open-api.bingx.com"
SYMBOLS  = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TF       = "1m"
WINDOW   = 50      # свечей в каждом окне для сравнения
WINDOWS  = 3       # кол-во случайных окон на пару
VOL_TOL  = 0.001   # 0.1% допуск на volume
PRICE_TOL = 0.001  # 0.1% — BingX REST pipeline может дообрабатывать недавние свечи


def fmt_sym(s: str) -> str:
    return s.replace("/", "-")


async def fetch_bingx(session: aiohttp.ClientSession, symbol: str,
                      start_ms: int, end_ms: int) -> dict[int, dict]:
    """Загружает свечи с BingX, возвращает словарь open_time_ms → candle."""
    params = {
        "symbol": fmt_sym(symbol),
        "interval": TF,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": WINDOW + 5,
    }
    async with session.get(f"{BASE_URL}/openApi/swap/v3/quote/klines",
                           params=params) as resp:
        data = await resp.json()

    result: dict[int, dict] = {}
    for row in data.get("data", []):
        t = int(row["time"])
        result[t] = {
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": float(row["volume"]),
        }
    return result


async def fetch_db(symbol: str, start_ms: int, end_ms: int) -> dict[int, dict]:
    """Читает свечи из БД в заданном диапазоне."""
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(
            select(CandleModel).where(
                CandleModel.symbol == symbol,
                CandleModel.timeframe == TF,
                CandleModel.open_time >= start_ms,
                CandleModel.open_time <= end_ms,
            ).order_by(CandleModel.open_time)
        )
        candles = rows.scalars().all()

    return {
        c.open_time: {
            "open":   c.open,
            "high":   c.high,
            "low":    c.low,
            "close":  c.close,
            "volume": c.volume,
        }
        for c in candles
    }


def compare(ts: int, api: dict, db: dict, sym: str) -> list[str]:
    errors = []
    for field in ("open", "high", "low", "close"):
        tol = PRICE_TOL
        diff = abs(api[field] - db[field])
        rel  = diff / api[field] if api[field] else 0
        if rel > tol:
            errors.append(f"{field}: API={api[field]} DB={db[field]} diff={diff:.6f}")
    # volume — мягкий допуск
    vdiff = abs(api["volume"] - db["volume"]) / (api["volume"] or 1)
    if vdiff > VOL_TOL:
        errors.append(f"volume: API={api['volume']:.4f} DB={db['volume']:.4f} diff={vdiff:.4%}")
    return errors


async def validate_symbol(session: aiohttp.ClientSession,
                           symbol: str,
                           min_ts: int, max_ts: int) -> dict:
    """Валидирует один символ по нескольким случайным окнам."""
    span = max_ts - min_ts
    window_ms = WINDOW * 60 * 1000

    total_checked  = 0
    total_missing  = 0   # есть в API, нет в БД
    total_extra    = 0   # есть в БД, нет в API
    total_mismatch = 0
    all_errors: list[str] = []

    for w in range(WINDOWS):
        # Случайный старт внутри доступного диапазона
        if span <= window_ms:
            start = min_ts
        else:
            start = random.randint(min_ts, max_ts - window_ms)
        end = start + window_ms

        api_data = await fetch_bingx(session, symbol, start, end)
        db_data  = await fetch_db(symbol, start, end)

        if not api_data:
            all_errors.append(f"  окно {w+1}: API вернул 0 свечей!")
            continue

        api_times = set(api_data)
        db_times  = set(db_data)

        missing = api_times - db_times   # в API есть, в БД нет
        extra   = db_times - api_times   # в БД есть, в API нет
        common  = api_times & db_times

        mismatches = []
        for ts in sorted(common):
            errs = compare(ts, api_data[ts], db_data[ts], symbol)
            if errs:
                mismatches.append((ts, errs))

        total_checked  += len(api_times)
        total_missing  += len(missing)
        total_extra    += len(extra)
        total_mismatch += len(mismatches)

        from datetime import datetime, timezone
        def fmt(ms): return datetime.fromtimestamp(ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

        status = "✓" if not missing and not mismatches else "✗"
        print(f"  [{status}] окно {w+1}: {fmt(start)} … {fmt(end)}"
              f"  API={len(api_times)} DB={len(db_times)}"
              f"  отсутств={len(missing)} несовп={len(mismatches)}")

        if mismatches:
            for ts, errs in mismatches[:3]:
                print(f"       ↳ {fmt(ts)}: {'; '.join(errs)}")
        if missing:
            sample = [fmt(t) for t in sorted(missing)[:3]]
            print(f"       ↳ нет в БД: {sample}")

        await asyncio.sleep(0.5)  # не нагружаем API

    return {
        "checked":  total_checked,
        "missing":  total_missing,
        "extra":    total_extra,
        "mismatch": total_mismatch,
    }


async def main():
    await init_db()
    factory = get_session_factory()

    # Узнаём диапазон 1m-свечей в БД для каждой пары
    ranges: dict[str, tuple[int, int]] = {}
    async with factory() as session:
        from sqlalchemy import func
        for sym in SYMBOLS:
            row = await session.execute(
                select(
                    func.min(CandleModel.open_time),
                    func.max(CandleModel.open_time),
                ).where(
                    CandleModel.symbol == sym,
                    CandleModel.timeframe == TF,
                )
            )
            mn, mx = row.one()
            if mn and mx:
                ranges[sym] = (mn, mx)

    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector,
                                      timeout=aiohttp.ClientTimeout(total=15)) as session:
        summary: dict[str, dict] = {}

        for sym in SYMBOLS:
            if sym not in ranges:
                print(f"\n{sym}: нет данных в БД, пропуск")
                continue

            mn, mx = ranges[sym]
            from datetime import datetime, timezone
            def fmts(ms): return datetime.fromtimestamp(ms/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

            print(f"\n{'='*60}")
            print(f"{sym}  [{fmts(mn)} … {fmts(mx)}]")
            print(f"{'='*60}")

            result = await validate_symbol(session, sym, mn, mx)
            summary[sym] = result

    # Итог
    print(f"\n{'='*60}")
    print("ИТОГ")
    print(f"{'='*60}")
    all_ok = True
    for sym, r in summary.items():
        ok = r["missing"] == 0 and r["mismatch"] == 0
        status = "✓ OK" if ok else "✗ ПРОБЛЕМЫ"
        print(f"  {sym:12s} {status}  "
              f"проверено={r['checked']}  "
              f"отсутств={r['missing']}  "
              f"несовпад={r['mismatch']}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("Все данные соответствуют BingX API ✓")
    else:
        print("Обнаружены расхождения — см. детали выше")


if __name__ == "__main__":
    asyncio.run(main())
