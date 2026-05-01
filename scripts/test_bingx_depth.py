"""
Быстрое исследование глубины BingX API — минимальное количество запросов.
Проверяет:
1. v3 Swap — все таймфреймы (1m, 5m, 15m, 1h, 1d, 1W)
2. v2 Swap — 1m
3. Spot Historical — 1m
4. Mark Price — 1m

Запуск: python scripts/test_bingx_depth.py
"""
import asyncio
import time
import aiohttp
import json
from datetime import datetime, timezone

BASE_URL = "https://open-api.bingx.com"
NOW_MS = int(time.time() * 1000)

# Ключевые даты для проверки (минимум)
KEY_DATES = [
    ("2020-01", 1577836800000),
    ("2021-01", 1609459200000),
    ("2022-01", 1640995200000),
    ("2023-01", 1672531200000),
    ("2024-01", 1704067200000),
    ("2024-06", 1719792000000),
    ("2024-09", 1727740800000),
    ("2024-12", 1733011200000),
    ("2025-03", 1743465600000),
    ("2025-06", 1748736000000),
    ("2025-09", 1756684800000),
    ("2025-12", 1764633600000),
    ("2026-03", 1775088000000),
]

INTERVALS = ["1m", "5m", "15m", "1h", "1d", "1W"]

ENDPOINTS = {
    "v3_swap": "/openApi/swap/v3/quote/klines",
    "v2_swap": "/openApi/swap/v2/quote/klines",
    "v3_mark": "/openApi/swap/v3/markPriceKlines",
    "spot_his": "/openApi/market/his/v1/kline",
}


async def fetch_one(session, endpoint, params):
    url = BASE_URL + endpoint
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            return data.get("data") or []
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


async def check_dates(session, endpoint, interval, dates):
    """Проверяет наличие данных по списку дат."""
    results = []
    for label, ts in dates:
        params = {"symbol": "BTC-USDT", "interval": interval, "startTime": ts, "limit": 1}
        rows = await fetch_one(session, endpoint, params)
        if rows and isinstance(rows, list) and len(rows) > 0:
            candle = rows[0] if isinstance(rows[0], dict) else {}
            ct = candle.get("time", candle.get("t", "?"))
            results.append((label, True, ct))
        else:
            results.append((label, False, None))
    return results


async def find_earliest(session, endpoint, interval, lo_ms, hi_ms):
    """Бинарный поиск самой ранней свечи в диапазоне [lo_ms, hi_ms]."""
    earliest = None
    for _ in range(30):
        mid = (lo_ms + hi_ms) // 2
        params = {"symbol": "BTC-USDT", "interval": interval, "startTime": mid, "limit": 1}
        rows = await fetch_one(session, endpoint, params)
        if rows and isinstance(rows, list) and len(rows) > 0:
            candle = rows[0] if isinstance(rows[0], dict) else {}
            earliest = candle.get("time", candle.get("t"))
            hi_ms = mid
        else:
            lo_ms = mid + 1
    return earliest


async def main():
    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        print("=" * 80)
        print(f"ИССЛЕДОВАНИЕ ГЛУБИНЫ ДАННЫХ BINGX API")
        now_dt = datetime.fromtimestamp(NOW_MS / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"Текущее время: {now_dt}")
        print("=" * 80)

        # === 1. v3 Swap — все таймфреймы ===
        print("\n=== 1. v3 Swap Klines ===")
        for interval in INTERVALS:
            print(f"\n--- {interval} ---")
            results = await check_dates(session, ENDPOINTS["v3_swap"], interval, KEY_DATES)
            for label, ok, ts in results:
                print(f"  {label}: {'OK' if ok else '--'}  {ts if ok else ''}")

            # Бинарный поиск
            earliest = await find_earliest(session, ENDPOINTS["v3_swap"], interval, 1719792000000, NOW_MS)
            if earliest:
                dt = datetime.fromtimestamp(earliest / 1000, tz=timezone.utc)
                days = (NOW_MS - earliest) // (24 * 60 * 60 * 1000)
                print(f"  >>> Ранняя: {dt.strftime('%Y-%m-%d %H:%M UTC')} ({days} дн. назад)")
            else:
                print(f"  >>> НЕТ ДАННЫХ")

        # === 2. v2 Swap — 1m ===
        print("\n=== 2. v2 Swap Klines (1m) ===")
        results = await check_dates(session, ENDPOINTS["v2_swap"], "1m", KEY_DATES)
        for label, ok, ts in results:
            print(f"  {label}: {'OK' if ok else '--'}  {ts if ok else ''}")
        earliest = await find_earliest(session, ENDPOINTS["v2_swap"], "1m", 1719792000000, NOW_MS)
        if earliest:
            dt = datetime.fromtimestamp(earliest / 1000, tz=timezone.utc)
            days = (NOW_MS - earliest) // (24 * 60 * 60 * 1000)
            print(f"  >>> Ранняя: {dt.strftime('%Y-%m-%d %H:%M UTC')} ({days} дн. назад)")

        # === 3. Spot Historical K-line — 1m ===
        print("\n=== 3. Spot Historical K-line (1m) ===")
        # Сначала проверим, работает ли endpoint
        params_now = {"symbol": "BTC-USDT", "interval": "1m", "limit": 1}
        rows = await fetch_one(session, ENDPOINTS["spot_his"], params_now)
        if rows and isinstance(rows, list) and len(rows) > 0:
            print(f"  Endpoint работает. Последняя: {rows[0]}")
            results = await check_dates(session, ENDPOINTS["spot_his"], "1m", KEY_DATES)
            for label, ok, ts in results:
                print(f"  {label}: {'OK' if ok else '--'}  {ts if ok else ''}")
            earliest = await find_earliest(session, ENDPOINTS["spot_his"], "1m", 1577836800000, NOW_MS)
            if earliest:
                dt = datetime.fromtimestamp(earliest / 1000, tz=timezone.utc)
                days = (NOW_MS - earliest) // (24 * 60 * 60 * 1000)
                print(f"  >>> Ранняя: {dt.strftime('%Y-%m-%d %H:%M UTC')} ({days} дн. назад)")
        else:
            print(f"  Endpoint НЕ работает или другой формат ответа")

        # === 4. Mark Price Klines — 1m ===
        print("\n=== 4. Mark Price Klines (1m) ===")
        params_now = {"symbol": "BTC-USDT", "interval": "1m", "limit": 1}
        rows = await fetch_one(session, ENDPOINTS["v3_mark"], params_now)
        if rows and isinstance(rows, list) and len(rows) > 0:
            print(f"  Endpoint работает. Последняя: {rows[0]}")
            results = await check_dates(session, ENDPOINTS["v3_mark"], "1m", KEY_DATES)
            for label, ok, ts in results:
                print(f"  {label}: {'OK' if ok else '--'}  {ts if ok else ''}")
            earliest = await find_earliest(session, ENDPOINTS["v3_mark"], "1m", 1719792000000, NOW_MS)
            if earliest:
                dt = datetime.fromtimestamp(earliest / 1000, tz=timezone.utc)
                days = (NOW_MS - earliest) // (24 * 60 * 60 * 1000)
                print(f"  >>> Ранняя: {dt.strftime('%Y-%m-%d %H:%M UTC')} ({days} дн. назад)")
        else:
            print(f"  Endpoint НЕ работает или другой формат ответа")

        print("\n" + "=" * 80)
        print("ГОТОВО")
        print("=" * 80)


asyncio.run(main())
