"""
BingX Futures WebSocket клиент.

Подписывается на фьючерсные потоки:
  - {symbol}@kline_1min   → свечи реального времени (фьючерс)
  - {symbol}@depth20      → стакан фьючерса
  - {symbol}@trade        → поток сделок для CVD

Публикует события в EventBus:
  - futures.candle.1m.tick / futures.candle.1m.closed
  - futures.orderbook.update
  - futures.trade.raw

Примечание: канал @forceOrder не поддерживается BingX Futures API.
Ликвидации доступны только через REST: GET /openApi/swap/v2/trade/forceOrders
"""
from __future__ import annotations

import asyncio
import gzip
import json
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import ssl
import certifi
import aiohttp

from core.logger import get_logger

if TYPE_CHECKING:
    from core.event_bus import EventBus

log = get_logger("FuturesWS")

# BingX использует единый WS эндпоинт для spot и futures (swap)
WS_URL = "wss://open-api-ws.bingx.com/market"
PING_INTERVAL = 20          # секунд
MAX_RECONNECT_DELAY = 60    # секунд
MIN_RECONNECT_DELAY = 3
MSG_TIMEOUT = 300           # 5 минут без сообщений → принудительный разрыв


class BingXFuturesWebSocket:
    """
    WebSocket клиент для фьючерсных данных BingX.
    Отдельный от спотового — потоки независимы.
    """

    def __init__(self, event_bus: "EventBus", symbols: list[str]) -> None:
        self._bus = event_bus
        self._symbols = symbols
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False
        self._reconnect_delay = MIN_RECONNECT_DELAY
        # Кэш последних цен для расчёта базиса (доступен внешнему коду)
        self.last_prices: dict[str, float] = {}
        # Статистика для Watchdog / Pulse
        self.last_message_at: float = 0.0
        self.messages_per_min: int = 0
        self._msg_count_window: list[float] = []
        self.status: str = "disconnected"   # connected / degraded / disconnected / dead

    async def start(self) -> None:
        self._running = True
        log.info(f"Futures WS запуск: {self._symbols}")
        while self._running:
            try:
                await self._connect_and_run()
                self._reconnect_delay = MIN_RECONNECT_DELAY
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(f"Futures WS ошибка: {e}. Переподключение через {self._reconnect_delay}с")
                self.status = "disconnected"
                await self._bus.publish("futures.ws.disconnected", {
                    "symbols": self._symbols,
                    "error": str(e),
                    "reconnect_in": self._reconnect_delay,
                })
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, MAX_RECONNECT_DELAY)

    async def stop(self) -> None:
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        log.info("Futures WS остановлен")

    async def _connect_and_run(self) -> None:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver(), ssl=ssl_ctx)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.ws_connect(
                WS_URL,
                heartbeat=PING_INTERVAL,
                receive_timeout=60,
            ) as ws:
                self._ws = ws
                self.status = "connected"
                self.last_message_at = time.time()
                log.info("Futures WS подключён")
                await self._bus.publish("futures.ws.connected", {"symbols": self._symbols})

                await self._subscribe(ws)
                ping_task = asyncio.create_task(self._ping_loop(ws))
                # Фоновая задача: принудительный разрыв, если нет данных > MSG_TIMEOUT
                stale_watchdog = asyncio.create_task(self._stale_watchdog(ws))

                try:
                    async for msg in ws:
                        if not self._running:
                            break
                        self._track_message()
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            await self._handle_message(gzip.decompress(msg.data))
                        elif msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg.data.encode())
                        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                            break
                finally:
                    ping_task.cancel()
                    stale_watchdog.cancel()
                    self.status = "disconnected"

    async def _stale_watchdog(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Принудительно закрывает соединение, если от сервера нет данных > MSG_TIMEOUT."""
        while not ws.closed:
            await asyncio.sleep(30)
            elapsed = time.time() - self.last_message_at
            if elapsed > MSG_TIMEOUT and not ws.closed:
                log.warning(
                    f"Futures WS: нет данных {elapsed:.0f}с (> {MSG_TIMEOUT}с). "
                    f"Принудительный разрыв для переподключения."
                )
                await ws.close()
                break

    async def _subscribe(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        for symbol in self._symbols:
            # Нормализуем символ: BTC/USDT → BTC-USDT
            sym = symbol.replace("/", "-")
            streams = [
                f"{sym}@kline_1min",
                f"{sym}@depth20",
                f"{sym}@trade",
            ]
            for stream in streams:
                payload = {"id": f"sub-{stream}", "reqType": "sub", "dataType": stream}
                await ws.send_str(json.dumps(payload))
                await asyncio.sleep(0.05)
        log.info(f"Futures WS подписки отправлены: {self._symbols}")

    async def _ping_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while not ws.closed:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await ws.send_str("Ping")
            except Exception:
                break

    def _track_message(self) -> None:
        now = time.time()
        self.last_message_at = now
        self._msg_count_window = [t for t in self._msg_count_window if now - t < 60]
        self._msg_count_window.append(now)
        self.messages_per_min = len(self._msg_count_window)

    async def _handle_message(self, raw: bytes) -> None:
        # BingX шлёт Ping (не Pong) — фильтруем до парсинга JSON
        raw_str = raw.decode(errors="replace").strip()
        if raw_str in ("Ping", "Pong"):
            return

        try:
            data = json.loads(raw)
        except Exception as e:
            log.warning(f"Futures WS: ошибка парсинга сообщения: {e}. Данные: {raw[:200]}")
            return

        if isinstance(data, dict) and data.get("msg") in ("Ping", "Pong"):
            return

        # DEBUG: логируем первые 10 не-Ping сообщений для диагностики
        if not hasattr(self, '_debug_count'):
            self._debug_count = 0
        if self._debug_count < 10:
            self._debug_count += 1
            log.info(f"Futures WS DEBUG #{self._debug_count}: {raw_str[:300]}")

        data_type: str = data.get("dataType", "")
        payload = data.get("data", {})

        # ── Свеча ─────────────────────────────────────────────────────────────
        if "@kline_" in data_type:
            await self._on_kline(data_type, payload)

        # ── Стакан ────────────────────────────────────────────────────────────
        elif "@depth" in data_type:
            await self._on_depth(data_type, payload)

        # ── Поток сделок ──────────────────────────────────────────────────────
        elif "@trade" in data_type:
            await self._on_trade(data_type, payload)

    async def _on_kline(self, data_type: str, payload: dict) -> None:
        # dataType: "BTC-USDT@kline_1min"
        symbol = data_type.split("@")[0].replace("-", "/")
        c = payload if isinstance(payload, dict) else {}
        if not c:
            return

        try:
            open_time = int(c.get("T", c.get("startTime", 0)))
            close_price = float(c.get("c", c.get("close", 0)))
            is_closed = bool(c.get("n", c.get("closed", False)))
        except (ValueError, TypeError):
            return

        self.last_prices[symbol] = close_price

        candle = {
            "symbol": symbol,
            "timeframe": "1m",
            "open_time": open_time,
            "open":   float(c.get("o", c.get("open", 0))),
            "high":   float(c.get("h", c.get("high", 0))),
            "low":    float(c.get("l", c.get("low", 0))),
            "close":  close_price,
            "volume": float(c.get("v", c.get("volume", 0))),
            "is_closed": is_closed,
            "market_type": "futures",
        }
        event_type = "futures.candle.1m.closed" if is_closed else "futures.candle.1m.tick"
        await self._bus.publish(event_type, candle)

    async def _on_depth(self, data_type: str, payload: dict) -> None:
        symbol = data_type.split("@")[0].replace("-", "/")
        await self._bus.publish("futures.orderbook.update", {
            "symbol": symbol,
            "bids": payload.get("bids", []),
            "asks": payload.get("asks", []),
            "ts": int(time.time() * 1000),
            "market_type": "futures",
        })

    async def _on_trade(self, data_type: str, payload: dict) -> None:
        symbol = data_type.split("@")[0].replace("-", "/")
        if isinstance(payload, list):
            for t in payload:
                await self._emit_trade(symbol, t)
        else:
            await self._emit_trade(symbol, payload)

    async def _emit_trade(self, symbol: str, t: dict) -> None:
        try:
            await self._bus.publish("futures.trade.raw", {
                "symbol": symbol,
                "timestamp": int(t.get("T", t.get("time", 0))),
                "price":    float(t.get("p", t.get("price", 0))),
                "quantity": float(t.get("q", t.get("qty", 0))),
                "side":     "buy" if t.get("m", t.get("buyerMaker", False)) else "sell",
                "trade_id": str(t.get("t", t.get("id", ""))),
                "market_type": "futures",
            })
        except (ValueError, TypeError):
            pass

