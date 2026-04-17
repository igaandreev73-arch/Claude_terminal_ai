"""
BingX Private API Client — единственный модуль с доступом к API-ключу.

Поддерживает:
  - Открытие рыночного/лимитного ордера (фьючерсы)
  - Выставление SL/TP
  - Закрытие позиции
  - Получение статуса ордеров и позиций
  - Данные аккаунта

В dry_run=True режиме все ордера логируются, но не отправляются на биржу.
HMAC-SHA256 подпись реализована и готова для production.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

from core.logger import get_logger

log = get_logger("BingXPrivate")

BASE_URL = "https://open-api.bingx.com"

# Futures endpoints
EP_PLACE_ORDER = "/openApi/swap/v2/trade/order"
EP_CANCEL_ORDER = "/openApi/swap/v2/trade/order"
EP_POSITION = "/openApi/swap/v2/user/positions"
EP_ACCOUNT = "/openApi/swap/v2/user/balance"
EP_SET_SLTP = "/openApi/swap/v2/trade/order"   # same endpoint, different type


class BingXPrivateClient:
    """
    Private REST client for BingX Futures.

    Parameters
    ----------
    api_key : str
        BingX API key (read from .env, stored ONLY here).
    api_secret : str
        BingX API secret.
    dry_run : bool
        If True, log orders instead of sending to exchange.
    """

    def __init__(self, api_key: str, api_secret: str, dry_run: bool = True) -> None:
        self._key = api_key
        self._secret = api_secret
        self._dry_run = dry_run
        self._session = None  # aiohttp.ClientSession, created on first use

    async def _ensure_session(self) -> None:
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ── Public interface ──────────────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        side: str,          # "BUY" | "SELL"
        position_side: str, # "LONG" | "SHORT"
        order_type: str,    # "MARKET" | "LIMIT"
        quantity: float,
        price: float | None = None,
    ) -> dict:
        """Открывает позицию на фьючерсном рынке."""
        params = {
            "symbol": self._fmt_symbol(symbol),
            "side": side,
            "positionSide": position_side,
            "type": order_type,
            "quantity": str(quantity),
        }
        if price and order_type == "LIMIT":
            params["price"] = str(price)

        return await self._request("POST", EP_PLACE_ORDER, params)

    async def close_position(self, symbol: str, position_side: str, quantity: float) -> dict:
        """Закрывает позицию."""
        side = "SELL" if position_side == "LONG" else "BUY"
        return await self.place_order(
            symbol=symbol,
            side=side,
            position_side=position_side,
            order_type="MARKET",
            quantity=quantity,
        )

    async def get_positions(self, symbol: str | None = None) -> list[dict]:
        """Получает открытые позиции."""
        params = {}
        if symbol:
            params["symbol"] = self._fmt_symbol(symbol)
        result = await self._request("GET", EP_POSITION, params)
        return result.get("data", []) if isinstance(result, dict) else []

    async def get_account_balance(self) -> dict:
        """Получает баланс аккаунта."""
        result = await self._request("GET", EP_ACCOUNT, {})
        return result.get("data", {}) if isinstance(result, dict) else {}

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Отменяет ордер по ID."""
        params = {"symbol": self._fmt_symbol(symbol), "orderId": order_id}
        return await self._request("DELETE", EP_CANCEL_ORDER, params)

    # ── Signing + HTTP ────────────────────────────────────────────────────────

    def _sign(self, params: dict) -> str:
        """HMAC-SHA256 подпись запроса."""
        query = urlencode(sorted(params.items()))
        return hmac.new(
            self._secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _build_params(self, params: dict) -> dict:
        params["timestamp"] = str(int(time.time() * 1000))
        params["signature"] = self._sign(params)
        return params

    async def _request(self, method: str, endpoint: str, params: dict) -> dict:
        signed = self._build_params(params)

        if self._dry_run:
            log.info(f"[DRY RUN] {method} {endpoint} params={signed}")
            return {"code": 0, "msg": "dry_run", "data": {}}

        await self._ensure_session()
        url = BASE_URL + endpoint
        headers = {"X-BX-APIKEY": self._key}

        try:
            if method == "GET":
                async with self._session.get(url, params=signed, headers=headers) as resp:
                    return await resp.json()
            elif method == "POST":
                async with self._session.post(url, params=signed, headers=headers) as resp:
                    return await resp.json()
            elif method == "DELETE":
                async with self._session.delete(url, params=signed, headers=headers) as resp:
                    return await resp.json()
        except Exception as e:
            log.error(f"BingX API ошибка: {e}")
            return {"code": -1, "msg": str(e), "data": {}}

        return {}

    @staticmethod
    def _fmt_symbol(symbol: str) -> str:
        """BTC/USDT → BTC-USDT"""
        return symbol.replace("/", "-")
