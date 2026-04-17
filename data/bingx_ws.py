import asyncio
import gzip
import json
import uuid
from typing import Callable, Awaitable

import aiohttp

from core.event_bus import EventBus
from core.logger import get_logger
from data.validator import Candle, Trade, OrderBookSnapshot, OrderBookLevel

log = get_logger("BingXWS")

WS_URL = "wss://open-api-ws.bingx.com/market"
PING_INTERVAL = 20        # BingX требует heartbeat каждые 20-30 сек
RECONNECT_BASE_DELAY = 5  # начальная задержка реконнекта
RECONNECT_MAX_DELAY = 60


def _fmt_symbol(symbol: str) -> str:
    return symbol.replace("/", "-")


class BingXWebSocket:
    """
    Поддерживает одно WS-соединение на BingX market stream.
    Подписывается на kline_1m, depth20, trade для заданных символов.
    Все данные публикует в Event Bus.
    """

    def __init__(self, event_bus: EventBus, symbols: list[str]) -> None:
        self._bus = event_bus
        self._symbols = symbols
        self._running = False
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        # ThreadedResolver uses OS socket.getaddrinfo — respects VPN/system DNS
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        self._session = aiohttp.ClientSession(connector=connector)
        self._task = asyncio.create_task(self._run_loop())
        log.info(f"BingX WS запущен для символов: {self._symbols}")

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("BingX WS остановлен")

    async def _run_loop(self) -> None:
        delay = RECONNECT_BASE_DELAY
        while self._running:
            try:
                await self._connect_and_listen()
                delay = RECONNECT_BASE_DELAY  # сброс при успешном подключении
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"WS ошибка: {e}. Реконнект через {delay}с")
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _connect_and_listen(self) -> None:
        assert self._session is not None
        async with self._session.ws_connect(WS_URL, heartbeat=None) as ws:
            self._ws = ws
            log.info("WS подключён к BingX")
            await self._subscribe_all(ws)

            ping_task = asyncio.create_task(self._ping_loop(ws))
            try:
                async for msg in ws:
                    if not self._running:
                        break
                    await self._handle_message(msg)
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    async def _subscribe_all(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        for symbol in self._symbols:
            bx = _fmt_symbol(symbol)
            for stream in [f"{bx}@kline_1min", f"{bx}@depth20", f"{bx}@trade"]:
                msg = {"id": str(uuid.uuid4()), "reqType": "sub", "dataType": stream}
                await ws.send_str(json.dumps(msg))
                log.debug(f"Подписка: {stream}")

    async def _ping_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while not ws.closed:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await ws.ping()
            except Exception:
                break

    async def _handle_message(self, msg: aiohttp.WSMessage) -> None:
        if msg.type == aiohttp.WSMsgType.BINARY:
            try:
                text = gzip.decompress(msg.data).decode("utf-8")
            except Exception:
                return
            # BingX pong response
            if text == "Pong":
                return
            await self._parse_json(text)
        elif msg.type == aiohttp.WSMsgType.TEXT:
            await self._parse_json(msg.data)
        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
            log.warning(f"WS сообщение: {msg.type}")
            raise ConnectionError("WS закрыт")

    async def _parse_json(self, text: str) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return

        data_type: str = data.get("dataType", "")

        if "@kline_1m" in data_type or "@kline_1min" in data_type:
            await self._on_kline(data)
        elif "@depth20" in data_type:
            await self._on_depth(data)
        elif "@trade" in data_type:
            await self._on_trade(data)

    async def _on_kline(self, data: dict) -> None:
        log.debug(f"kline raw: {data}")
        symbol_raw: str = data.get("dataType", "").split("@")[0]  # "BTC-USDT"
        symbol = symbol_raw.replace("-", "/")
        # BingX perpetual swap kline: data.data.K.{t,T,o,h,l,c,v,x}
        kline = data.get("data", {}).get("K", data.get("data", {}))

        try:
            candle = Candle(
                symbol=symbol,
                timeframe="1m",
                open_time=int(kline.get("t", 0)),
                open=float(kline.get("o", 0)),
                high=float(kline.get("h", 0)),
                low=float(kline.get("l", 0)),
                close=float(kline.get("c", 0)),
                volume=float(kline.get("v", 0)),
                is_closed=bool(kline.get("x", False)),
                source="exchange",
            )
        except Exception as e:
            log.warning(f"Ошибка валидации kline {symbol}: {e}")
            await self._bus.publish("data.validation_error", {"symbol": symbol, "error": str(e)})
            return

        event_type = "candle.1m.closed" if candle.is_closed else "candle.1m.tick"
        await self._bus.publish(event_type, candle)

    async def _on_depth(self, data: dict) -> None:
        symbol_raw: str = data.get("dataType", "").split("@")[0]
        symbol = symbol_raw.replace("-", "/")
        depth = data.get("data", {})

        try:
            bids = [OrderBookLevel(price=float(b[0]), quantity=float(b[1])) for b in depth.get("bids", [])]
            asks = [OrderBookLevel(price=float(a[0]), quantity=float(a[1])) for a in depth.get("asks", [])]
            snapshot = OrderBookSnapshot(
                symbol=symbol,
                timestamp=int(data.get("ts", 0)),
                bids=bids,
                asks=asks,
            )
            await self._bus.publish("orderbook.update", snapshot)
        except Exception as e:
            log.warning(f"Ошибка обработки стакана {symbol}: {e}")

    async def _on_trade(self, data: dict) -> None:
        symbol_raw: str = data.get("dataType", "").split("@")[0]
        symbol = symbol_raw.replace("-", "/")
        t = data.get("data", {})

        try:
            trade = Trade(
                symbol=symbol,
                timestamp=int(t.get("T", 0)),
                price=float(t.get("p", 0)),
                quantity=float(t.get("q", 0)),
                side="buy" if t.get("m") is False else "sell",
                trade_id=str(t.get("t", "")),
            )
            await self._bus.publish("trade.raw", trade)
        except Exception as e:
            log.warning(f"Ошибка обработки сделки {symbol}: {e}")
