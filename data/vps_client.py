"""VPS Client — клиент Desktop для подключения к VPS-сборщику.

Заменяет прямые BingX-подключения на Desktop.
Получает данные через WS (реалтайм) и REST (история) с VPS.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import aiohttp

from core.config import get_config
from core.event_bus import EventBus
from core.logger import get_logger
from data.validator import Candle

log = get_logger("VPSClient")

# Тип для колбэка события
EventHandler = Callable[[str, Any], Awaitable[None]]


class VPSClient:
    """Клиент для получения данных с VPS вместо прямого BingX.

    - WS подключение к VPS :8800/ws — реалтайм события
    - REST запросы к VPS :8800 — история и управление

    Все полученные события публикуются в локальный Event Bus Desktop'а.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._config = get_config()

        # WS
        self._ws_url = self._config.vps_ws_url
        self._api_key = self._config.VPS_API_KEY
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._ws_task: asyncio.Task | None = None
        self._running = False

        # REST base URL
        self._rest_url = self._config.vps_url

        # Состояние подключения
        self.is_connected = False
        self.reconnect_delay = 1.0  # начальная задержка перед реконнектом
        self.max_reconnect_delay = 30.0
        self._reconnect_attempts = 0

        # Heartbeat
        self._last_heartbeat: int = 0  # timestamp ms
        self._last_heartbeat_data: dict = {}

        # Подписчики на сырые события (до публикации в Event Bus)
        self._raw_handlers: list[EventHandler] = []

    def on_raw_event(self, handler: EventHandler) -> None:
        """Подписывает обработчик на сырые события от VPS."""
        self._raw_handlers.append(handler)

    # ── WS: подключение и обработка ─────────────────────────────────────────

    async def connect_ws(self) -> None:
        """Подключается к VPS WebSocket и начинает приём событий."""
        if self._running:
            return
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_loop())

    async def _ws_loop(self) -> None:
        """Цикл подключения с авто-реконнектом."""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"WS connection error: {e}")
                self.is_connected = False

            if not self._running:
                break

            # Экспоненциальная задержка перед реконнектом
            delay = min(self.reconnect_delay, self.max_reconnect_delay)
            log.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts + 1})")
            await asyncio.sleep(delay)
            self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
            self._reconnect_attempts += 1

    async def _connect_and_listen(self) -> None:
        """Подключается к WS и слушает сообщения."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

        # Подключаемся с API-ключом в query параметрах
        ws_url = f"{self._ws_url}?api_key={self._api_key}"
        log.info(f"Connecting to VPS WS: {self._config.VPS_HOST}:{self._config.VPS_PORT}")

        async with self._session.ws_connect(
            ws_url,
            heartbeat=30.0,
            receive_timeout=60.0,
        ) as ws:
            self._ws = ws
            self.is_connected = True
            self.reconnect_delay = 1.0  # сброс задержки при успешном подключении
            self._reconnect_attempts = 0
            log.info("Connected to VPS WS")

            # Публикуем событие о подключении
            await self._event_bus.publish("vps.connected", {
                "host": self._config.VPS_HOST,
                "port": self._config.VPS_PORT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Запускаем ping-задачу
            ping_task = asyncio.create_task(self._ping_loop(ws))

            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._on_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        log.error(f"WS error: {ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        log.info("WS connection closed")
                        break
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
                self.is_connected = False
                self._ws = None

    async def _ping_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Отправляет ping каждые 20 секунд для поддержания соединения."""
        while self._running and not ws.closed:
            try:
                await ws.send_json({"type": "ping"})
                await asyncio.sleep(20)
            except Exception:
                break

    @property
    def seconds_since_heartbeat(self) -> float:
        """Секунд с последнего heartbeat. inf если heartbeat не было."""
        if self._last_heartbeat == 0:
            return float('inf')
        return time.time() - self._last_heartbeat / 1000

    @property
    def is_data_stale(self) -> bool:
        """True, если нет heartbeat >60 сек или WS отключён."""
        if not self.is_connected:
            return True
        return self.seconds_since_heartbeat > 60

    async def _on_message(self, raw: str) -> None:
        """Обрабатывает входящее WS сообщение от VPS."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(f"Invalid JSON from VPS WS: {raw[:100]}")
            return

        msg_type = msg.get("type", "")

        # Heartbeat от VPS
        if msg_type == "heartbeat":
            self._last_heartbeat = msg.get("ts", int(time.time() * 1000))
            self._last_heartbeat_data = msg
            self.is_connected = True
            self._reconnect_attempts = 0
            self.reconnect_delay = 1.0
            return

        # Pong от VPS
        if msg_type == "pong":
            return

        # Состояние системы (ответ на get_state)
        if msg_type == "state":
            await self._event_bus.publish("vps.state", msg)
            return

        # Ошибка
        if msg_type == "error":
            log.warning(f"VPS error: {msg.get('message', '')}")
            return

        # Событие от VPS
        if msg_type == "event":
            event_type = msg.get("event_type", "")
            data = msg.get("data")

            # Уведомляем raw-подписчиков
            for handler in self._raw_handlers:
                try:
                    await handler(event_type, data)
                except Exception as e:
                    log.error(f"Raw handler error for {event_type}: {e}")

            # Публикуем в локальный Event Bus
            await self._event_bus.publish(event_type, data)

    # ── REST: запросы к VPS ─────────────────────────────────────────────────

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Возвращает HTTP-сессию (создаёт если нет)."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _rest_get(self, path: str, params: dict | None = None) -> dict:
        """GET-запрос к REST API VPS с аутентификацией."""
        session = await self._ensure_session()
        headers = {"X-API-Key": self._api_key}
        url = f"{self._rest_url}{path}"
        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                text = await r.text()
                log.error(f"VPS REST error {r.status}: {text[:200]}")
                raise ConnectionError(f"VPS REST error {r.status}: {text[:200]}")
            return await r.json()

    async def get_candles(
        self,
        symbol: str = "BTC/USDT",
        tf: str = "1m",
        limit: int = 500,
        market_type: str = "spot",
    ) -> list[Candle]:
        """Запрашивает исторические свечи с VPS.

        Возвращает список Candle (валидированные).
        """
        data = await self._rest_get("/api/candles", {
            "symbol": symbol,
            "tf": tf,
            "limit": str(limit),
            "market_type": market_type,
        })
        raw_candles = data.get("candles", [])
        candles: list[Candle] = []
        for rc in raw_candles:
            try:
                candle = Candle(
                    symbol=symbol,
                    timeframe=tf,
                    open_time=rc["open_time"],
                    open=rc["open"],
                    high=rc["high"],
                    low=rc["low"],
                    close=rc["close"],
                    volume=rc["volume"],
                    is_closed=rc.get("is_closed", True),
                    source="exchange",
                )
                candles.append(candle)
            except Exception as e:
                log.warning(f"Invalid candle data from VPS: {e}")
        return candles

    async def get_status(self) -> dict:
        """Запрашивает статус VPS."""
        return await self._rest_get("/status")

    async def get_data_status(self) -> dict:
        """Запрашивает статус данных на VPS."""
        return await self._rest_get("/data/status")

    async def get_health(self) -> dict:
        """Запрашивает health-check VPS."""
        return await self._rest_get("/health")

    async def get_symbols(self) -> list[str]:
        """Запрашивает список отслеживаемых символов на VPS."""
        data = await self._rest_get("/symbols")
        return data.get("symbols", [])

    async def start_backfill(self, symbol: str | None = None, days: int = 30) -> dict:
        """Запускает бэкфилл на VPS."""
        session = await self._ensure_session()
        headers = {"X-API-Key": self._api_key}
        payload = {"symbol": symbol, "days": days}
        url = f"{self._rest_url}/backfill"
        async with session.post(url, json=payload, headers=headers) as r:
            if r.status != 200:
                text = await r.text()
                raise ConnectionError(f"Backfill error: {text[:200]}")
            return await r.json()

    async def request_state(self) -> None:
        """Запрашивает полное состояние VPS через WS."""
        if self._ws and not self._ws.closed:
            await self._ws.send_json({
                "type": "command",
                "command": "get_state",
                "payload": {},
            })

    # ── Управление жизненным циклом ─────────────────────────────────────────

    async def start(self) -> None:
        """Запускает VPS клиент."""
        log.info("Starting VPS Client")
        await self.connect_ws()

    async def stop(self) -> None:
        """Останавливает VPS клиент."""
        log.info("Stopping VPS Client")
        self._running = False

        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        self._ws = None
        self.is_connected = False
        log.info("VPS Client stopped")
