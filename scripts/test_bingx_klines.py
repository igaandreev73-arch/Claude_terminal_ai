"""
Диагностика: проверяем BingX klines с startTime/endTime.
Запуск: python scripts/test_bingx_klines.py
"""
import asyncio
import time
import aiohttp
import json

BASE_URL = "https://open-api.bingx.com"

async def fetch(session, params):
    url = BASE_URL + "/openApi/swap/v3/quote/klines"
    async with session.get(url, params=params) as resp:
        status = resp.status
        text = await resp.text()
        try:
            data = json.loads(text)
        except Exception:
            data = text
        return status, data

async def main():
    now_ms = int(time.time() * 1000)
    one_week_ago = now_ms - 7 * 24 * 60 * 60 * 1000
    two_days_ago = now_ms - 2 * 24 * 60 * 60 * 1000
    one_day_ago  = now_ms - 1 * 24 * 60 * 60 * 1000

    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Без времени (должно работать)
        print("\n=== 1. Без startTime/endTime (recent 5 свечей) ===")
        status, data = await fetch(session, {
            "symbol": "BTC-USDT", "interval": "1m", "limit": 5
        })
        print(f"Status: {status}")
        print(f"code: {data.get('code')}, msg: {data.get('msg')}")
        rows = data.get("data") or []
        print(f"Свечей: {len(rows)}")
        if rows:
            print(f"Первая: {rows[0]}")

        # 2. С startTime и endTime — прошлая неделя до вчера
        print("\n=== 2. startTime=2 дня назад, endTime=1 день назад, limit=5 ===")
        status, data = await fetch(session, {
            "symbol": "BTC-USDT", "interval": "1m",
            "startTime": two_days_ago, "endTime": one_day_ago, "limit": 5
        })
        print(f"Status: {status}")
        print(f"code: {data.get('code')}, msg: {data.get('msg')}")
        rows = data.get("data") or []
        print(f"Свечей: {len(rows)}")
        if rows:
            print(f"Первая: {rows[0]}")
        else:
            print("Полный ответ:", json.dumps(data, indent=2)[:500])

        # 3. Только startTime (без endTime)
        print("\n=== 3. Только startTime=2 дня назад, limit=5 ===")
        status, data = await fetch(session, {
            "symbol": "BTC-USDT", "interval": "1m",
            "startTime": two_days_ago, "limit": 5
        })
        print(f"Status: {status}")
        print(f"code: {data.get('code')}, msg: {data.get('msg')}")
        rows = data.get("data") or []
        print(f"Свечей: {len(rows)}")
        if rows:
            print(f"Первая: {rows[0]}")
        else:
            print("Полный ответ:", json.dumps(data, indent=2)[:500])

        # 4. Только endTime (без startTime)
        print("\n=== 4. Только endTime=1 день назад, limit=5 ===")
        status, data = await fetch(session, {
            "symbol": "BTC-USDT", "interval": "1m",
            "endTime": one_day_ago, "limit": 5
        })
        print(f"Status: {status}")
        print(f"code: {data.get('code')}, msg: {data.get('msg')}")
        rows = data.get("data") or []
        print(f"Свечей: {len(rows)}")
        if rows:
            print(f"Первая: {rows[0]}")
        else:
            print("Полный ответ:", json.dumps(data, indent=2)[:500])

        # 5. Проверяем v2 endpoint
        print("\n=== 5. v2 endpoint, только limit=5 ===")
        url2 = BASE_URL + "/openApi/swap/v2/quote/klines"
        async with session.get(url2, params={"symbol": "BTC-USDT", "interval": "1m", "limit": 5}) as resp:
            status = resp.status
            data = await resp.json()
        print(f"Status: {status}")
        print(f"code: {data.get('code')}, msg: {data.get('msg')}")
        rows = data.get("data") or []
        print(f"Свечей: {len(rows)}")
        if rows:
            print(f"Первая: {rows[0]}")

asyncio.run(main())
