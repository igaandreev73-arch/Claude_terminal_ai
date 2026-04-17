import asyncio
import pytest
from core.event_bus import EventBus
from data.tf_aggregator import TFAggregator
from data.validator import Candle


def make_1m_candle(open_time_min: int, close: float = 100.0) -> Candle:
    """open_time_min — минута с эпохи Unix (для удобства)."""
    return Candle(
        symbol="BTC/USDT",
        timeframe="1m",
        open_time=open_time_min * 60_000,
        open=100.0,
        high=105.0,
        low=95.0,
        close=close,
        volume=10.0,
        is_closed=True,
        source="exchange",
    )


@pytest.fixture
async def setup():
    bus = EventBus()
    await bus.start()
    agg = TFAggregator(bus)
    await agg.start()
    yield bus, agg
    await agg.stop()
    await bus.stop()


async def test_3m_candle_aggregated(setup):
    bus, agg = setup
    received: list[Candle] = []

    async def on_3m(event):
        received.append(event.data)

    bus.subscribe("candle.3m.closed", on_3m)

    # 3 свечи с 1m aligned start (минута кратная 3)
    # open_time_min=0,1,2 → aligned at 0 (0 % 3 == 0)
    for minute in range(3):
        await bus.publish("candle.1m.closed", make_1m_candle(minute))

    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].timeframe == "3m"
    assert received[0].open_time == 0  # 0 * 60_000
    assert received[0].source == "aggregated"


async def test_aggregated_high_low(setup):
    bus, agg = setup
    received: list[Candle] = []

    async def on_3m(event):
        received.append(event.data)

    bus.subscribe("candle.3m.closed", on_3m)

    candles = [
        Candle(symbol="BTC/USDT", timeframe="1m", open_time=i * 60_000,
               open=100.0, high=100 + i * 10, low=90.0, close=101.0,
               volume=5.0, is_closed=True, source="exchange")
        for i in range(3)
    ]
    for c in candles:
        await bus.publish("candle.1m.closed", c)

    await asyncio.sleep(0.1)

    assert len(received) == 1
    agg_candle = received[0]
    assert agg_candle.high == 120.0   # max(100, 110, 120)
    assert agg_candle.low == 90.0
    assert agg_candle.volume == pytest.approx(15.0)


async def test_no_aggregation_before_enough_candles(setup):
    bus, agg = setup
    received: list = []

    async def on_5m(event):
        received.append(event.data)

    bus.subscribe("candle.5m.closed", on_5m)

    # Публикуем только 4 свечи — 5m не должна сформироваться
    for minute in range(4):
        await bus.publish("candle.1m.closed", make_1m_candle(minute))

    await asyncio.sleep(0.1)
    assert len(received) == 0
