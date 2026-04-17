import asyncio
import time
import pytest
from data.ob_processor import OrderBook, SpoofDetector, OBProcessor, SPOOF_TTL_SEC
from data.validator import OrderBookSnapshot, OrderBookLevel
from core.event_bus import EventBus


# ─── OrderBook юнит-тесты ───────────────────────────────────────────────────

def make_book(bids: dict, asks: dict) -> OrderBook:
    ob = OrderBook(symbol="BTC/USDT")
    ob.bids = dict(bids)
    ob.asks = dict(asks)
    return ob


def test_best_bid_ask():
    ob = make_book({40000: 1, 39999: 2}, {40001: 1, 40002: 2})
    assert ob.best_bid() == 40000.0
    assert ob.best_ask() == 40001.0


def test_spread():
    ob = make_book({40000: 1}, {40010: 1})
    assert ob.spread() == pytest.approx(10.0)


def test_imbalance_bull():
    ob = make_book({40000: 100}, {40001: 10})
    imb = ob.imbalance()
    assert imb > 0.3


def test_imbalance_bear():
    ob = make_book({40000: 10}, {40001: 100})
    imb = ob.imbalance()
    assert imb < -0.3


def test_imbalance_neutral():
    ob = make_book({40000: 50}, {40001: 50})
    assert ob.imbalance() == pytest.approx(0.0)


def test_apply_diff_add_and_remove():
    ob = OrderBook(symbol="BTC/USDT")
    ob.apply_diff([[40000, 5], [39999, 3]], [[40001, 2]])
    assert ob.bids[40000] == 5
    assert ob.asks[40001] == 2
    # Удаление уровня
    ob.apply_diff([[40000, 0]], [])
    assert 40000 not in ob.bids


def test_slippage_buy_consumes_levels():
    ob = make_book({}, {40001: 5, 40002: 5, 40003: 10})
    result = ob.slippage_estimate("buy", qty=12)
    assert result["levels_consumed"] == 3
    assert result["slippage_pct"] > 0


def test_slippage_sell_no_asks():
    ob = make_book({40000: 5, 39999: 5}, {})
    result = ob.slippage_estimate("buy", qty=5)
    # Нет asks → возвращает None avg_price
    assert result["avg_price"] is None


def test_liquidity_walls():
    # 10 мелких ордеров + 1 стена: avg = (10 + 1000) / 11 ≈ 91.8; 1000 >= 91.8*5 = 459 → True
    small = {40001 + i: 10 for i in range(10)}
    small[40099] = 1000
    ob = make_book({}, small)
    walls = ob.liquidity_walls(multiplier=5)
    prices = [w["price"] for w in walls["ask_walls"]]
    assert 40099 in prices


def test_to_snapshot_dict():
    ob = make_book({40000: 10, 39999: 5}, {40001: 8, 40002: 3})
    snap = ob.to_snapshot_dict(depth=2)
    assert len(snap["bids_top5"]) == 2
    assert "imbalance" in snap


# ─── SpoofDetector тесты ────────────────────────────────────────────────────

def test_spoof_detected_fast_removal():
    detector = SpoofDetector()
    ob = make_book({40000: 1, 39999: 1}, {})  # avg_bid = 1
    # Большой ордер появляется (> 5x avg)
    detector.update("BTC/USDT", ob, [[39998, 10]], [])
    # Добавляем его в книгу вручную чтобы avg пересчитался
    ob.bids[39998] = 10

    # Сразу исчезает (qty=0) → спуф
    spoofs = detector.update("BTC/USDT", ob, [[39998, 0]], [])
    assert len(spoofs) == 1
    assert spoofs[0]["price"] == 39998
    assert spoofs[0]["side"] == "bid"


def test_no_spoof_if_slow_removal():
    """Ордер держался дольше TTL — не спуф."""
    detector = SpoofDetector()
    ob = make_book({40000: 1, 39999: 1}, {})
    detector.update("BTC/USDT", ob, [[39998, 10]], [])
    ob.bids[39998] = 10

    # Принудительно устаревляем запись
    watched = detector._watched["BTC/USDT"]["bid"]
    if 39998 in watched:
        watched[39998].seen_at -= (SPOOF_TTL_SEC + 1)

    spoofs = detector.update("BTC/USDT", ob, [[39998, 0]], [])
    assert len(spoofs) == 0


# ─── OBProcessor интеграционный тест ────────────────────────────────────────

@pytest.fixture
async def ob_setup():
    bus = EventBus()
    await bus.start()
    proc = OBProcessor(bus)
    await proc.start()
    yield bus, proc
    await proc.stop()
    await bus.stop()


async def test_ob_state_updated_event(ob_setup):
    bus, proc = ob_setup
    events = []

    async def handler(event):
        events.append(event.data)

    bus.subscribe("ob.state_updated", handler)

    snapshot = OrderBookSnapshot(
        symbol="BTC/USDT",
        timestamp=int(time.time() * 1000),
        bids=[OrderBookLevel(price=40000, quantity=10)],
        asks=[OrderBookLevel(price=40001, quantity=5)],
    )
    await bus.publish("orderbook.update", snapshot)
    await asyncio.sleep(0.1)

    assert len(events) == 1
    assert events[0]["symbol"] == "BTC/USDT"
    assert "imbalance" in events[0]


async def test_pressure_bull_event(ob_setup):
    bus, proc = ob_setup
    pressures = []

    async def handler(event):
        pressures.append(event.data)

    bus.subscribe("ob.pressure", handler)

    snapshot = OrderBookSnapshot(
        symbol="ETH/USDT",
        timestamp=int(time.time() * 1000),
        bids=[OrderBookLevel(price=2000, quantity=100)],
        asks=[OrderBookLevel(price=2001, quantity=5)],
    )
    await bus.publish("orderbook.update", snapshot)
    await asyncio.sleep(0.1)

    assert any(p["direction"] == "bull" for p in pressures)


async def test_calc_slippage(ob_setup):
    bus, proc = ob_setup

    snapshot = OrderBookSnapshot(
        symbol="SOL/USDT",
        timestamp=int(time.time() * 1000),
        bids=[OrderBookLevel(price=100, quantity=10)],
        asks=[OrderBookLevel(price=101, quantity=3), OrderBookLevel(price=102, quantity=5)],
    )
    await bus.publish("orderbook.update", snapshot)
    await asyncio.sleep(0.1)

    result = await proc.calc_slippage("SOL/USDT", "buy", qty=6)
    assert result is not None
    assert result["levels_consumed"] == 2
    assert result["slippage_pct"] > 0
