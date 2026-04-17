import asyncio
import pytest
from analytics.smartmoney import detect_fvg, detect_bos, detect_choch, detect_order_block, detect_premium_discount, SmartMoneyEngine
from core.event_bus import EventBus
from data.validator import Candle


def make_candle(i: int, o: float, h: float, l: float, c: float, symbol: str = "BTC/USDT", tf: str = "1h") -> Candle:
    return Candle(symbol=symbol, timeframe=tf, open_time=i * 3600_000,
                  open=o, high=h, low=l, close=c, volume=10.0)


# ─── FVG ─────────────────────────────────────────────────────────────────────

def test_bullish_fvg():
    candles = [
        make_candle(0, 100, 105, 98, 103),   # c1: high=105
        make_candle(1, 103, 108, 102, 107),  # c2: большая бычья
        make_candle(2, 107, 112, 106, 111),  # c3: low=106 > c1.high=105 → FVG
    ]
    result = detect_fvg(candles)
    assert len(result) == 1
    assert result[0].direction == "bull"
    assert result[0].bottom == 105.0
    assert result[0].top == 106.0


def test_bearish_fvg():
    candles = [
        make_candle(0, 110, 112, 106, 108),  # c1: low=106
        make_candle(1, 108, 109, 100, 102),  # c2: большая медвежья
        make_candle(2, 102, 103, 95, 97),    # c3: high=103 < c1.low=106 → FVG
    ]
    result = detect_fvg(candles)
    assert len(result) == 1
    assert result[0].direction == "bear"


def test_no_fvg_when_no_gap():
    candles = [
        make_candle(0, 100, 105, 98, 103),
        make_candle(1, 103, 108, 102, 107),
        make_candle(2, 107, 112, 103, 111),  # low=103 ≤ c1.high=105 → нет гэпа
    ]
    result = detect_fvg(candles)
    assert len(result) == 0


# ─── BOS ─────────────────────────────────────────────────────────────────────

def test_bullish_bos():
    # 6 свечей: первые 5 качаются вокруг 100, последняя пробивает максимум
    candles = [make_candle(i, 99, 102 + i * 0.1, 98, 100) for i in range(5)]
    candles.append(make_candle(5, 100, 115, 99, 114))  # close=114 > swing high
    bos = detect_bos(candles, lookback=5)
    assert bos is not None
    assert bos["direction"] == "bull"


def test_bearish_bos():
    candles = [make_candle(i, 101, 103, 98 - i * 0.1, 100) for i in range(5)]
    candles.append(make_candle(5, 100, 101, 85, 86))  # close=86 < swing low
    bos = detect_bos(candles, lookback=5)
    assert bos is not None
    assert bos["direction"] == "bear"


def test_no_bos_without_breakout():
    candles = [make_candle(i, 99, 105, 95, 100) for i in range(6)]
    bos = detect_bos(candles, lookback=5)
    assert bos is None


# ─── Order Block ─────────────────────────────────────────────────────────────

def test_bullish_order_block():
    # Медвежья свеча на позиции 3, за ней 3 бычьих → бычий OB в окне lookback=5
    # window = последние 5 свечей из 8: candles[3..7]
    candles = [
        make_candle(0, 120, 122, 117, 118),  # padding
        make_candle(1, 118, 120, 116, 119),  # padding
        make_candle(2, 119, 121, 115, 120),  # padding
        make_candle(3, 120, 122, 109, 111),  # МЕДВЕЖЬЯ (o=120 > c=111)
        make_candle(4, 111, 116, 110, 115),  # бычья
        make_candle(5, 115, 120, 114, 119),  # бычья
        make_candle(6, 119, 124, 118, 123),  # бычья
        make_candle(7, 123, 127, 122, 126),  # padding
    ]
    obs = detect_order_block(candles, lookback=5)
    bull_obs = [o for o in obs if o.direction == "bull"]
    assert len(bull_obs) >= 1


# ─── Premium/Discount ─────────────────────────────────────────────────────────

def test_premium_zone():
    candles = [make_candle(i, 100, 100 + i, 99, 100 + i * 0.9) for i in range(20)]
    result = detect_premium_discount(candles, lookback=20)
    assert result is not None
    assert result["zone"] == "premium"  # последняя свеча в верхней части диапазона


def test_discount_zone():
    # первые 19 высокие, последняя низкая → discount
    candles = [make_candle(i, 200, 210, 195, 200) for i in range(19)]
    candles.append(make_candle(19, 100, 105, 95, 97))  # сильно ниже
    result = detect_premium_discount(candles, lookback=20)
    assert result is not None
    assert result["zone"] == "discount"


# ─── SmartMoney Engine интеграция ─────────────────────────────────────────────

@pytest.fixture
async def smc_setup():
    bus = EventBus()
    await bus.start()
    engine = SmartMoneyEngine(bus)
    await engine.start()
    yield bus, engine
    await engine.stop()
    await bus.stop()


async def test_smc_publishes_zone_event(smc_setup):
    bus, _ = smc_setup
    zones = []

    async def handler(event):
        zones.append(event.data)

    bus.subscribe("smc.zone.updated", handler)

    # Публикуем 20 свечей
    for i in range(20):
        c = make_candle(i, 100 + i, 105 + i, 98 + i, 102 + i)
        await bus.publish("candle.1h.closed", c)

    await asyncio.sleep(0.1)
    assert len(zones) > 0
    assert "zone" in zones[-1]
