"""
Проверка Open Interest и Funding Rate history endpoint'ов BingX.

Запуск: python scripts/test_bingx_oi_funding.py
"""
import asyncio
import aiohttp
import json
from datetime import datetime, timezone

BASE_URL = "https://open-api.bingx.com"
NOW_MS = int(datetime.now(timezone.utc).timestamp() * 1000)
WEEK_AGO = NOW_MS - 7 * 24 * 60 * 60 * 1000
MONTH_AGO = NOW_MS - 30 * 24 * 60 * 60 * 1000


async def fetch_json(session, endpoint, params):
    url = BASE_URL + endpoint
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            return resp.status, data
    except Exception as e:
        return 0, {"error": str(e)}


async def main():
    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        print("=" * 80)
        print("ПРОВЕРКА OPEN INTEREST И FUNDING RATE ENDPOINT'ОВ")
        print(f"Сейчас: {datetime.fromtimestamp(NOW_MS/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print("=" * 80)

        # === 1. Open Interest — текущий ===
        print("\n=== 1. Open Interest (текущий) ===")
        status, data = await fetch_json(session, "/openApi/swap/v2/quote/openInterest", {
            "symbol": "BTC-USDT"
        })
        print(f"Status: {status}")
        print(f"Ответ: {json.dumps(data, indent=2)[:500]}")

        # === 2. Open Interest — с startTime (возможно, history) ===
        print("\n=== 2. Open Interest с startTime (проверка history) ===")
        status, data = await fetch_json(session, "/openApi/swap/v2/quote/openInterest", {
            "symbol": "BTC-USDT",
            "startTime": str(MONTH_AGO)
        })
        print(f"Status: {status}")
        print(f"Ответ: {json.dumps(data, indent=2)[:500]}")

        # === 3. Open Interest History (если есть такой endpoint) ===
        print("\n=== 3. Open Interest History (предполагаемый endpoint) ===")
        for endpoint in [
            "/openApi/swap/v2/quote/openInterest/history",
            "/openApi/swap/v2/quote/openInterestHistory",
            "/openApi/swap/v3/quote/openInterest/history",
        ]:
            status, data = await fetch_json(session, endpoint, {
                "symbol": "BTC-USDT",
                "period": "1d",
                "limit": 3,
            })
            print(f"\n  Endpoint: {endpoint}")
            print(f"  Status: {status}")
            print(f"  Ответ: {json.dumps(data, indent=2)[:300]}")

        # === 4. Funding Rate — текущий ===
        print("\n=== 4. Funding Rate (текущий) ===")
        status, data = await fetch_json(session, "/openApi/swap/v2/quote/fundingRate", {
            "symbol": "BTC-USDT"
        })
        print(f"Status: {status}")
        print(f"Ответ: {json.dumps(data, indent=2)[:500]}")

        # === 5. Funding Rate History ===
        print("\n=== 5. Funding Rate History ===")
        for endpoint in [
            "/openApi/swap/v2/quote/fundingRateHistory",
            "/openApi/swap/v2/quote/fundingRate/history",
            "/openApi/swap/v3/quote/fundingRateHistory",
        ]:
            status, data = await fetch_json(session, endpoint, {
                "symbol": "BTC-USDT",
                "limit": 3,
            })
            print(f"\n  Endpoint: {endpoint}")
            print(f"  Status: {status}")
            print(f"  Ответ: {json.dumps(data, indent=2)[:300]}")

        # === 6. Premium Index ===
        print("\n=== 6. Premium Index ===")
        status, data = await fetch_json(session, "/openApi/swap/v2/quote/premiumIndex", {
            "symbol": "BTC-USDT"
        })
        print(f"Status: {status}")
        print(f"Ответ: {json.dumps(data, indent=2)[:500]}")

        print("\n" + "=" * 80)
        print("ГОТОВО")
        print("=" * 80)


asyncio.run(main())
