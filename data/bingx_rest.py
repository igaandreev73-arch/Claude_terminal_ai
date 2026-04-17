import aiohttp
from typing import Any

from core.event_bus import EventBus
from core.logger import get_logger
from data.rate_limit_guard import RateLimitGuard, Priority
from data.validator import Candle

log = get_logger("BingXREST")

BASE_URL = "https://open-api.bingx.com"

# BingX использует дефис в символах: BTC-USDT (не BTC/USDT)
def _fmt_symbol(symbol: str) -> str:
    return symbol.replace("/", "-")

# Маппинг наших таймфреймов → BingX формат
TIMEFRAME_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h",
    "1d": "1d", "1W": "1W", "1M": "1M",
}


class BingXRestClient:
    def __init__(self, event_bus: EventBus, rate_guard: RateLimitGuard) -> None:
        self._bus = event_bus
        self._guard = rate_guard
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"Content-Type": "application/json"},
        )
        log.info("BingX REST клиент запущен")

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
        log.info("BingX REST клиент остановлен")

    async def _get(self, path: str, params: dict | None = None, priority: Priority = Priority.MEDIUM) -> Any:
        await self._guard.acquire(priority)
        url = BASE_URL + path
        try:
            assert self._session is not None
            async with self._session.get(url, params=params) as resp:
                if resp.status == 429:
                    log.warning("BingX вернул 429 (rate limit), ждём 5 сек")
                    import asyncio
                    await asyncio.sleep(5)
                    raise RuntimeError("Rate limit 429")
                resp.raise_for_status()
                data = await resp.json()
                return data
        except aiohttp.ClientError as e:
            log.error(f"HTTP ошибка {path}: {e}")
            raise

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]:
        """Загружает исторические свечи с BingX."""
        bingx_tf = TIMEFRAME_MAP.get(timeframe)
        if not bingx_tf:
            raise ValueError(f"Неизвестный таймфрейм: {timeframe}")

        params: dict = {
            "symbol": _fmt_symbol(symbol),
            "interval": bingx_tf,
            "limit": min(limit, 1440),
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        raw = await self._get("/openApi/swap/v3/quote/klines", params, Priority.LOW)

        candles: list[Candle] = []
        # BingX klines format: [openTime, open, high, low, close, volume, closeTime, ...]
        for row in raw.get("data", []):
            try:
                candle = Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=int(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    is_closed=True,
                    source="exchange",
                )
                candles.append(candle)
            except Exception as e:
                log.warning(f"Ошибка валидации свечи {symbol}: {e}")
                await self._bus.publish("data.validation_error", {"symbol": symbol, "error": str(e)})

        log.info(f"Загружено {len(candles)} свечей {symbol} {timeframe}")
        return candles

    async def fetch_open_interest(self, symbol: str) -> dict | None:
        """Загружает открытый интерес."""
        try:
            data = await self._get(
                "/openApi/swap/v2/quote/openInterest",
                {"symbol": _fmt_symbol(symbol)},
                Priority.MEDIUM,
            )
            return data.get("data")
        except Exception as e:
            log.error(f"Ошибка загрузки OI {symbol}: {e}")
            return None

    async def fetch_funding_rate(self, symbol: str) -> dict | None:
        """Загружает ставку финансирования."""
        try:
            data = await self._get(
                "/openApi/swap/v2/quote/fundingRate",
                {"symbol": _fmt_symbol(symbol)},
                Priority.LOW,
            )
            return data.get("data")
        except Exception as e:
            log.error(f"Ошибка загрузки funding rate {symbol}: {e}")
            return None
