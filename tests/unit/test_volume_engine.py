import asyncio
import pytest
from analytics.volume_engine import VolumeEngine, CVDTracker, compute_volume_profile, candle_delta_estimate
from core.event_bus import EventBus
from data.validator import Candle, Trade


def make_candle(i: int, close: float = 100.0, volume: float = 10.0) -> Candle:
    return Candle(
        symbol="BTC/USDT", timeframe="1m",
        open_time=i * 60_000, open=close - 1, high=close + 2, low=close - 2,
        close=close, volume=volume,
    )


def make_trade(side: str, qty: float = 1.0) -> Trade:
    return Trade(symbol="BTC/USDT", timestamp=1_700_000_000_000, price=40000.0, quantity=qty, side=side)


# ─── CVD Tracker ─────────────────────────────────────────────────────────────

def test_cvd_buy_increases():
    cvd = CVDTracker()
    cvd.update(make_trade("buy", 5.0))
    assert cvd.get("BTC/USDT") == pytest.approx(5.0)


def test_cvd_sell_decreases():
    cvd = CVDTracker()
    cvd.update(make_trade("buy", 10.0))
    cvd.update(make_trade("sell", 3.0))
    assert cvd.get("BTC/USDT") == pytest.approx(7.0)


def test_cvd_reset():
    cvd = CVDTracker()
    cvd.update(make_trade("buy", 10.0))
    cvd.reset("BTC/USDT")
    assert cvd.get("BTC/USDT") == 0.0


# ─── Candle Delta ─────────────────────────────────────────────────────────────

def test_delta_bullish_candle():
    candle = Candle(symbol="X", timeframe="1m", open_time=0,
                    open=99.0, high=104.0, low=98.0, close=103.0, volume=100.0)
    delta = candle_delta_estimate(candle)
    assert delta > 0  # бычья → положительная дельта


def test_delta_bearish_candle():
    candle = Candle(symbol="X", timeframe="1m", open_time=0,
                    open=103.0, high=104.0, low=98.0, close=99.0, volume=100.0)
    delta = candle_delta_estimate(candle)
    assert delta < 0  # медвежья → отрицательная дельта


# ─── Volume Profile ────────────────────────────────────────────────────────────

def test_volume_profile_has_poc():
    candles = [make_candle(i, close=100.0 + i % 5, volume=10.0) for i in range(50)]
    profile = compute_volume_profile(candles)
    assert "poc" in profile
    assert "vah" in profile
    assert "val" in profile
    assert profile["vah"] >= profile["poc"] >= profile["val"]


def test_volume_profile_empty_returns_empty():
    assert compute_volume_profile([]) == {}


def test_volume_profile_val_lte_vah():
    candles = [make_candle(i, close=40000 + i * 10, volume=5.0) for i in range(100)]
    profile = compute_volume_profile(candles)
    assert profile["val"] <= profile["vah"]


# ─── Volume Engine интеграция ─────────────────────────────────────────────────

@pytest.fixture
async def vol_setup():
    bus = EventBus()
    await bus.start()
    engine = VolumeEngine(bus)
    await engine.start()
    yield bus, engine
    await engine.stop()
    await bus.stop()


async def test_cvd_event_on_trade(vol_setup):
    bus, engine = vol_setup
    events = []

    async def handler(event):
        events.append(event.data)

    bus.subscribe("volume.cvd.updated", handler)
    await bus.publish("trade.raw", make_trade("buy", 2.0))
    await asyncio.sleep(0.1)

    assert len(events) == 1
    assert events[0]["cvd"] == pytest.approx(2.0)


async def test_delta_event_on_candle(vol_setup):
    bus, engine = vol_setup
    events = []

    async def handler(event):
        events.append(event.data)

    bus.subscribe("volume.delta.candle", handler)
    await bus.publish("candle.1m.closed", make_candle(0))
    await asyncio.sleep(0.1)

    assert len(events) == 1
    assert "delta" in events[0]


async def test_profile_event_after_20_candles(vol_setup):
    bus, engine = vol_setup
    profiles = []

    async def handler(event):
        profiles.append(event.data)

    bus.subscribe("volume.profile.updated", handler)

    for i in range(25):
        await bus.publish("candle.1m.closed", make_candle(i, close=100 + i))
    await asyncio.sleep(0.2)

    assert len(profiles) > 0
    assert "poc" in profiles[-1]
