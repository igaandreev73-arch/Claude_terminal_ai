import asyncio
import pytest
from core.event_bus import EventBus
from analytics.ta_engine import TAEngine, _rsi, _macd, _bollinger, _atr, _stochastic, _candle_patterns
from data.validator import Candle
import pandas as pd


def make_candle(i: int, close: float = 100.0, symbol: str = "BTC/USDT", tf: str = "1m") -> Candle:
    return Candle(
        symbol=symbol, timeframe=tf,
        open_time=i * 60_000, open=close - 1, high=close + 2, low=close - 2,
        close=close, volume=10.0,
    )


def make_series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


# ─── Математика индикаторов ──────────────────────────────────────────────────

def test_rsi_range():
    closes = [100 + i * 0.5 for i in range(30)]
    s = make_series(closes)
    result = _rsi(s)
    rsi_val = result["rsi"].dropna().iloc[-1]
    assert 0 <= rsi_val <= 100


def test_rsi_overbought():
    closes = [100 + i * 2 for i in range(30)]  # чистый рост → RSI > 70
    result = _rsi(make_series(closes))
    assert result["rsi"].dropna().iloc[-1] > 70


def test_macd_histogram_sign():
    # Рост → ema_fast обгоняет ema_slow → histogram > 0
    closes = [100 + i for i in range(40)]
    result = _macd(make_series(closes))
    hist = result["macd_hist"].dropna().iloc[-1]
    assert hist > 0


def test_bollinger_width_positive():
    closes = [100 + (i % 5) for i in range(30)]
    result = _bollinger(make_series(closes))
    width = result["bb_width"].dropna().iloc[-1]
    assert width > 0


def test_atr_positive():
    hi = make_series([105.0] * 20)
    lo = make_series([95.0] * 20)
    cl = make_series([100.0] * 20)
    result = _atr(hi, lo, cl)
    atr_val = result["atr"].dropna().iloc[-1]
    assert atr_val > 0


def test_stochastic_range():
    closes = [100 + (i % 10) for i in range(20)]
    hi = [c + 3 for c in closes]
    lo = [c - 3 for c in closes]
    result = _stochastic(make_series(hi), make_series(lo), make_series(closes))
    k_val = result["stoch_k"].dropna().iloc[-1]
    assert 0 <= k_val <= 100


def test_candle_pattern_doji():
    # open ≈ close → doji
    patterns = _candle_patterns(100.0, 105.0, 95.0, 100.2)
    assert patterns["doji"] is True


def test_candle_pattern_hammer():
    # маленькое тело вверху, длинная нижняя тень
    patterns = _candle_patterns(100.0, 101.0, 90.0, 100.5)
    assert patterns["hammer"] is True


# ─── TA Engine интеграция ─────────────────────────────────────────────────────

@pytest.fixture
async def ta_setup():
    bus = EventBus()
    await bus.start()
    engine = TAEngine(bus)
    await engine.start()
    yield bus, engine
    await engine.stop()
    await bus.stop()


async def test_ta_event_published(ta_setup):
    bus, engine = ta_setup
    results = []

    async def handler(event):
        results.append(event.data)

    bus.subscribe("ta.BTC/USDT.1m.updated", handler)

    # Публикуем 30 свечей чтобы хватило для RSI
    for i in range(30):
        await bus.publish("candle.1m.closed", make_candle(i, close=100.0 + i))

    await asyncio.sleep(0.1)
    assert len(results) > 0
    last = results[-1]
    assert last["symbol"] == "BTC/USDT"
    assert "close" in last


async def test_ta_rsi_present_after_15_candles(ta_setup):
    bus, engine = ta_setup
    results = []

    async def handler(event):
        results.append(event.data)

    bus.subscribe("ta.BTC/USDT.1m.updated", handler)

    # Чередуем рост и падение чтобы RSI не вырождался в 100/0
    for i in range(20):
        close = 100.0 + (5 if i % 2 == 0 else -3)
        await bus.publish("candle.1m.closed", make_candle(i, close=close))
    await asyncio.sleep(0.1)

    last = results[-1]
    assert "rsi_14" in last
    assert last["rsi_14"] is not None


async def test_ta_patterns_in_result(ta_setup):
    bus, engine = ta_setup
    results = []

    async def handler(event):
        results.append(event.data)

    bus.subscribe("ta.BTC/USDT.1m.updated", handler)

    for i in range(5):
        await bus.publish("candle.1m.closed", make_candle(i))
    await asyncio.sleep(0.1)

    last = results[-1]
    assert "doji" in last
    assert "hammer" in last


async def test_get_latest(ta_setup):
    _, engine = ta_setup
    bus, _ = ta_setup

    for i in range(20):
        await bus.publish("candle.1m.closed", make_candle(i))
    await asyncio.sleep(0.1)

    result = engine.get_latest("BTC/USDT", "1m")
    assert result is not None
    assert result["symbol"] == "BTC/USDT"
