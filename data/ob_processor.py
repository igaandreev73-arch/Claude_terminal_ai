"""
Order Book Processor.

Обязанности:
- Поддерживает актуальную копию стакана по каждому символу
- Вычисляет imbalance, walls, slippage
- Детектирует spoofing
- Периодически сохраняет снимки в БД через Event Bus
"""
import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field

from core.event_bus import Event, EventBus
from core.logger import get_logger
from data.validator import OrderBookSnapshot, OrderBookLevel

log = get_logger("OBProcessor")

IMBALANCE_BULL_THRESHOLD = 0.3     # > +0.3 → давление покупателей
IMBALANCE_BEAR_THRESHOLD = -0.3    # < -0.3 → давление продавцов
SPOOF_SIZE_MULTIPLIER = 5.0        # ордер считается "крупным" если > 5× средний
SPOOF_TTL_SEC = 2.0                # исчез за < 2 сек без исполнения → спуф
WALL_SIZE_MULTIPLIER = 10.0        # стена = объём > 10× средний
SNAPSHOT_INTERVAL_SEC = 10.0       # периодический снимок каждые 10 сек


@dataclass
class PriceLevel:
    price: float
    quantity: float


@dataclass
class _SpyOrder:
    """Отслеживаемый крупный ордер."""
    price: float
    quantity: float
    side: str          # 'bid' | 'ask'
    seen_at: float     # monotonic time


@dataclass
class OrderBook:
    symbol: str
    bids: dict[float, float] = field(default_factory=dict)  # price → qty
    asks: dict[float, float] = field(default_factory=dict)
    last_update: float = 0.0

    def apply_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        self.bids = {lvl.price: lvl.quantity for lvl in snapshot.bids}
        self.asks = {lvl.price: lvl.quantity for lvl in snapshot.asks}
        self.last_update = time.monotonic()

    def apply_diff(self, bids: list[list], asks: list[list]) -> None:
        """Применяет инкрементальный апдейт. qty=0 → удалить уровень."""
        for price, qty in bids:
            price, qty = float(price), float(qty)
            if qty == 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = qty
        for price, qty in asks:
            price, qty = float(price), float(qty)
            if qty == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = qty
        self.last_update = time.monotonic()

    def best_bid(self) -> float | None:
        return max(self.bids) if self.bids else None

    def best_ask(self) -> float | None:
        return min(self.asks) if self.asks else None

    def spread(self) -> float | None:
        bb, ba = self.best_bid(), self.best_ask()
        if bb and ba:
            return ba - bb
        return None

    def bid_volume(self, depth: int = 20) -> float:
        top = sorted(self.bids.keys(), reverse=True)[:depth]
        return sum(self.bids[p] for p in top)

    def ask_volume(self, depth: int = 20) -> float:
        top = sorted(self.asks.keys())[:depth]
        return sum(self.asks[p] for p in top)

    def imbalance(self, depth: int = 20) -> float:
        bv = self.bid_volume(depth)
        av = self.ask_volume(depth)
        total = bv + av
        if total == 0:
            return 0.0
        return (bv - av) / total

    def slippage_estimate(self, side: str, qty: float) -> dict:
        """
        Рассчитывает проскальзывание при покупке/продаже qty контрактов.
        side: 'buy' | 'sell'
        Возвращает: {'avg_price', 'worst_price', 'slippage_pct', 'levels_consumed'}
        """
        if side == "buy":
            levels = sorted(self.asks.keys())
            side_book = self.asks
        else:
            levels = sorted(self.bids.keys(), reverse=True)
            side_book = self.bids

        if not levels:
            return {"avg_price": None, "worst_price": None, "slippage_pct": None, "levels_consumed": 0}

        best_price = levels[0]
        remaining = qty
        total_cost = 0.0
        levels_consumed = 0
        worst_price = best_price

        for price in levels:
            available = side_book[price]
            filled = min(remaining, available)
            total_cost += filled * price
            remaining -= filled
            worst_price = price
            levels_consumed += 1
            if remaining <= 0:
                break

        filled_qty = qty - remaining
        avg_price = total_cost / filled_qty if filled_qty > 0 else best_price
        slippage_pct = abs(avg_price - best_price) / best_price * 100 if best_price else 0.0

        return {
            "avg_price": round(avg_price, 8),
            "worst_price": worst_price,
            "slippage_pct": round(slippage_pct, 4),
            "levels_consumed": levels_consumed,
            "unfilled_qty": round(remaining, 8),
        }

    def liquidity_walls(self, multiplier: float = WALL_SIZE_MULTIPLIER) -> dict:
        """Находит уровни с аномально большим объёмом."""
        all_bids = list(self.bids.values())
        all_asks = list(self.asks.values())
        avg_bid = sum(all_bids) / len(all_bids) if all_bids else 0
        avg_ask = sum(all_asks) / len(all_asks) if all_asks else 0

        walls = {
            "bid_walls": [
                {"price": p, "qty": q}
                for p, q in self.bids.items()
                if avg_bid > 0 and q >= avg_bid * multiplier
            ],
            "ask_walls": [
                {"price": p, "qty": q}
                for p, q in self.asks.items()
                if avg_ask > 0 and q >= avg_ask * multiplier
            ],
        }
        return walls

    def to_snapshot_dict(self, depth: int = 5) -> dict:
        top_bids = sorted(self.bids.keys(), reverse=True)[:depth]
        top_asks = sorted(self.asks.keys())[:depth]
        return {
            "bids_top5": [[p, self.bids[p]] for p in top_bids],
            "asks_top5": [[p, self.asks[p]] for p in top_asks],
            "bid_volume": self.bid_volume(),
            "ask_volume": self.ask_volume(),
            "imbalance": self.imbalance(),
        }


class SpoofDetector:
    """
    Отслеживает крупные ордера. Если ордер исчез за < SPOOF_TTL_SEC
    без исполнения (quantity → 0) — это потенциальный спуф.
    """

    def __init__(self) -> None:
        # {symbol: {side: {price: _SpyOrder}}}
        self._watched: dict[str, dict[str, dict[float, _SpyOrder]]] = defaultdict(
            lambda: {"bid": {}, "ask": {}}
        )

    def avg_order_size(self, book: OrderBook, side: str) -> float:
        levels = list(book.bids.values()) if side == "bid" else list(book.asks.values())
        if not levels:
            return 0.0
        return sum(levels) / len(levels)

    def update(self, symbol: str, book: OrderBook, bids: list[list], asks: list[list]) -> list[dict]:
        """
        Вызывается после каждого diff-апдейта.
        Возвращает список обнаруженных спуфов (может быть пустым).
        """
        spoofs = []
        now = time.monotonic()

        avg_bid = self.avg_order_size(book, "bid")
        avg_ask = self.avg_order_size(book, "ask")

        def _process(updates: list[list], side: str, avg: float):
            watched = self._watched[symbol][side]
            for price, qty in updates:
                price, qty = float(price), float(qty)
                if qty == 0:
                    # Ордер исчез — проверяем не был ли он под наблюдением
                    if price in watched:
                        spy = watched.pop(price)
                        elapsed = now - spy.seen_at
                        if elapsed < SPOOF_TTL_SEC:
                            spoofs.append({
                                "symbol": symbol,
                                "side": side,
                                "price": price,
                                "quantity": spy.quantity,
                                "lived_sec": round(elapsed, 3),
                            })
                elif avg > 0 and qty >= avg * SPOOF_SIZE_MULTIPLIER:
                    # Новый крупный ордер — начинаем отслеживать
                    watched[price] = _SpyOrder(price=price, quantity=qty, side=side, seen_at=now)

            # Чистим устаревшие записи (> TTL*3)
            stale = [p for p, s in watched.items() if now - s.seen_at > SPOOF_TTL_SEC * 3]
            for p in stale:
                watched.pop(p, None)

        _process(bids, "bid", avg_bid)
        _process(asks, "ask", avg_ask)
        return spoofs


class OBProcessor:
    """Главный процессор стакана. Подписывается на orderbook.update из Event Bus."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._books: dict[str, OrderBook] = {}
        self._spoof_detector = SpoofDetector()
        self._snapshot_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._bus.subscribe("orderbook.update", self._on_ob_update)
        self._snapshot_task = asyncio.create_task(self._periodic_snapshot())
        log.info("OB Processor запущен")

    async def stop(self) -> None:
        self._running = False
        if self._snapshot_task:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass
        log.info("OB Processor остановлен")

    def get_book(self, symbol: str) -> OrderBook | None:
        return self._books.get(symbol)

    async def _on_ob_update(self, event: Event) -> None:
        snapshot: OrderBookSnapshot = event.data
        symbol = snapshot.symbol

        if symbol not in self._books:
            self._books[symbol] = OrderBook(symbol=symbol)

        book = self._books[symbol]

        # Конвертируем в формат diff [[price, qty], ...]
        bids_diff = [[lvl.price, lvl.quantity] for lvl in snapshot.bids]
        asks_diff = [[lvl.price, lvl.quantity] for lvl in snapshot.asks]

        # Применяем обновление
        book.apply_diff(bids_diff, asks_diff)

        # Спуф детектор
        spoofs = self._spoof_detector.update(symbol, book, bids_diff, asks_diff)
        for spoof in spoofs:
            log.warning(f"SPOOF обнаружен: {spoof}")
            await self._bus.publish("ob.spoof_detected", spoof)

        # Публикуем обновлённое состояние стакана
        imbalance = book.imbalance()
        await self._bus.publish("ob.state_updated", {
            "symbol": symbol,
            "imbalance": imbalance,
            "bid_volume": book.bid_volume(),
            "ask_volume": book.ask_volume(),
            "best_bid": book.best_bid(),
            "best_ask": book.best_ask(),
            "spread": book.spread(),
        })

        # Публикуем сигнал давления если imbalance превышает порог
        if imbalance > IMBALANCE_BULL_THRESHOLD:
            await self._bus.publish("ob.pressure", {"symbol": symbol, "direction": "bull", "imbalance": imbalance})
        elif imbalance < IMBALANCE_BEAR_THRESHOLD:
            await self._bus.publish("ob.pressure", {"symbol": symbol, "direction": "bear", "imbalance": imbalance})

    async def _periodic_snapshot(self) -> None:
        """Каждые 10 секунд сохраняет снимок всех стаканов."""
        while self._running:
            await asyncio.sleep(SNAPSHOT_INTERVAL_SEC)
            for symbol, book in self._books.items():
                if not book.bids and not book.asks:
                    continue
                snap = book.to_snapshot_dict()
                snap["symbol"] = symbol
                snap["timestamp"] = int(time.time() * 1000)
                snap["trigger"] = "periodic"
                await self._bus.publish("ob.snapshot", snap)

    async def calc_slippage(self, symbol: str, side: str, qty: float) -> dict | None:
        """Публичный метод для запроса slippage перед сделкой."""
        book = self._books.get(symbol)
        if not book:
            log.warning(f"Стакан для {symbol} не найден")
            return None
        result = book.slippage_estimate(side, qty)
        # Сохраняем pre-trade снимок
        snap = book.to_snapshot_dict(depth=20)
        snap["symbol"] = symbol
        snap["timestamp"] = int(time.time() * 1000)
        snap["trigger"] = "pre_trade"
        await self._bus.publish("ob.snapshot", snap)
        return result
