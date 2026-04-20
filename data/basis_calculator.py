"""
Basis Calculator — базис спот/фьючерс каждую минуту.

Базис = Фьючерсная цена − Спотовая цена
Базис % = Базис / Спотовая цена × 100

Слушает события закрытых свечей обоих рынков, публикует:
  - futures.basis.updated  →  {symbol, timestamp, spot, futures, basis, basis_pct}

Сохраняет в таблицу futures_metrics.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from core.event_bus import EventBus

log = get_logger("BasisCalc")


class BasisCalculator:
    def __init__(self, event_bus: "EventBus") -> None:
        self._bus = event_bus
        # Последние закрытые цены по символу
        self._spot_prices: dict[str, float] = {}
        self._futures_prices: dict[str, float] = {}
        # Кэш последнего базиса (для Pulse / внешнего доступа)
        self.last_basis: dict[str, dict] = {}

    async def start(self) -> None:
        self._bus.subscribe("candle.1m.closed",         self._on_spot_candle)
        self._bus.subscribe("futures.candle.1m.closed", self._on_futures_candle)
        log.info("BasisCalculator запущен")

    async def stop(self) -> None:
        log.info("BasisCalculator остановлен")

    async def _on_spot_candle(self, event) -> None:
        d = event.data if hasattr(event, "data") else event
        symbol = d.get("symbol", "")
        close = d.get("close", 0.0)
        if symbol and close:
            self._spot_prices[symbol] = float(close)
            await self._maybe_publish(symbol, int(d.get("open_time", time.time() * 1000)))

    async def _on_futures_candle(self, event) -> None:
        d = event.data if hasattr(event, "data") else event
        symbol = d.get("symbol", "")
        close = d.get("close", 0.0)
        if symbol and close:
            self._futures_prices[symbol] = float(close)
            await self._maybe_publish(symbol, int(d.get("open_time", time.time() * 1000)))

    async def _maybe_publish(self, symbol: str, open_time: int) -> None:
        spot = self._spot_prices.get(symbol)
        fut  = self._futures_prices.get(symbol)
        if spot is None or fut is None:
            return

        basis = fut - spot
        basis_pct = (basis / spot * 100) if spot else 0.0

        result = {
            "symbol":    symbol,
            "timestamp": open_time,
            "spot":      round(spot, 6),
            "futures":   round(fut, 6),
            "basis":     round(basis, 6),
            "basis_pct": round(basis_pct, 4),
        }
        self.last_basis[symbol] = result
        await self._bus.publish("futures.basis.updated", result)
        await self._save(result)

    async def _save(self, data: dict) -> None:
        try:
            from storage.database import get_session_factory
            from storage.models import FuturesMetricsModel
            from sqlalchemy.dialects.sqlite import insert

            factory = get_session_factory()
            async with factory() as session:
                stmt = insert(FuturesMetricsModel).values(
                    symbol=data["symbol"],
                    timestamp=data["timestamp"],
                    basis=data["basis"],
                    basis_pct=data["basis_pct"],
                ).on_conflict_do_update(
                    index_elements=["symbol", "timestamp"],
                    set_={"basis": data["basis"], "basis_pct": data["basis_pct"]},
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            log.debug(f"basis save error: {e}")
