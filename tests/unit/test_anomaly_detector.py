"""Unit tests for Anomaly Detector."""
import asyncio
import pytest

from core.event_bus import Event, EventBus
from signals.anomaly_detector import AnomalyDetector, FLASH_CRASH_PCT, PRICE_SPIKE_PCT


def candle_event(symbol, open_price, close, high=None, low=None):
    return Event("candle.1m.closed", {
        "symbol": symbol,
        "open": open_price,
        "close": close,
        "high": high or close * 1.001,
        "low": low or close * 0.999,
        "volume": 1000.0,
        "open_time": 0,
    })


@pytest.mark.asyncio
async def test_price_spike_detected():
    bus = EventBus()
    await bus.start()
    detector = AnomalyDetector(bus)
    await detector.start()

    received = []
    bus.subscribe("anomaly.price_spike", lambda e: received.append(e.data))

    # Price spikes up > PRICE_SPIKE_PCT%
    spike_pct = PRICE_SPIKE_PCT + 1.0
    close = 100.0 * (1 + spike_pct / 100)
    await detector._on_candle(candle_event("BTC/USDT", 100.0, close))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["symbol"] == "BTC/USDT"
    assert received[0]["change_pct"] > PRICE_SPIKE_PCT
    await bus.stop()


@pytest.mark.asyncio
async def test_no_spike_on_small_move():
    bus = EventBus()
    detector = AnomalyDetector(bus)
    await detector.start()

    received = []
    bus.subscribe("anomaly.price_spike", lambda e: received.append(e.data))

    await detector._on_candle(candle_event("BTC/USDT", 100.0, 101.0))  # 1% — no spike
    assert received == []


@pytest.mark.asyncio
async def test_flash_crash_detected():
    bus = EventBus()
    await bus.start()
    detector = AnomalyDetector(bus)
    await detector.start()

    received = []
    bus.subscribe("anomaly.flash_crash", lambda e: received.append(e.data))

    # 3 candles of consecutive drops > FLASH_CRASH_PCT% total
    prices = [100.0, 99.0, 98.0, 100.0 * (1 - (FLASH_CRASH_PCT + 1) / 100)]
    prev = prices[0]
    for p in prices[1:]:
        await detector._on_candle(candle_event("BTC/USDT", prev, p))
        prev = p

    await asyncio.sleep(0.05)
    assert len(received) == 1
    assert received[0]["drop_pct"] >= FLASH_CRASH_PCT
    await bus.stop()


@pytest.mark.asyncio
async def test_flash_crash_cooldown_prevents_spam():
    bus = EventBus()
    await bus.start()
    detector = AnomalyDetector(bus)
    await detector.start()

    received = []
    bus.subscribe("anomaly.flash_crash", lambda e: received.append(e.data))

    # Trigger the same flash crash twice — cooldown should suppress second
    drop_close = 100.0 * (1 - (FLASH_CRASH_PCT + 1) / 100)
    for _ in range(2):
        detector._closes["BTC/USDT"].clear()
        detector._closes["BTC/USDT"].extend([100.0, 99.0, drop_close])
        await detector._on_candle(candle_event("BTC/USDT", 99.0, drop_close))

    await asyncio.sleep(0.05)
    assert len(received) == 1  # cooldown suppressed second
    await bus.stop()


@pytest.mark.asyncio
async def test_ob_manip_detected():
    bus = EventBus()
    await bus.start()
    detector = AnomalyDetector(bus)
    await detector.start()

    received = []
    bus.subscribe("anomaly.ob_manip", lambda e: received.append(e.data))

    # Spoof + high imbalance
    await detector._on_ob_update(Event("ob.state_updated", {"symbol": "BTC/USDT", "imbalance": 0.5}))
    await detector._on_spoof(Event("ob.spoof_detected", {"symbol": "BTC/USDT"}))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["symbol"] == "BTC/USDT"
    await bus.stop()


@pytest.mark.asyncio
async def test_ob_manip_not_detected_without_spoof():
    bus = EventBus()
    detector = AnomalyDetector(bus)
    await detector.start()

    received = []
    bus.subscribe("anomaly.ob_manip", lambda e: received.append(e.data))

    # High imbalance but no spoof
    await detector._on_ob_update(Event("ob.state_updated", {"symbol": "BTC/USDT", "imbalance": 0.5}))
    assert received == []


@pytest.mark.asyncio
async def test_slippage_anomaly_reported():
    bus = EventBus()
    await bus.start()
    detector = AnomalyDetector(bus)

    received = []
    bus.subscribe("anomaly.slippage", lambda e: received.append(e.data))

    await detector.report_slippage("BTC/USDT", expected_pct=0.01, actual_pct=0.05)
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["actual_pct"] == 0.05
    await bus.stop()


@pytest.mark.asyncio
async def test_slippage_not_reported_below_multiplier():
    bus = EventBus()
    detector = AnomalyDetector(bus)

    received = []
    bus.subscribe("anomaly.slippage", lambda e: received.append(e.data))

    await detector.report_slippage("BTC/USDT", expected_pct=0.01, actual_pct=0.015)  # 1.5× < 3×
    assert received == []
