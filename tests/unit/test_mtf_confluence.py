"""Unit tests for MTF Confluence Engine."""
import pytest

from analytics.mtf_confluence import (
    MTFConfluenceEngine,
    SymbolState,
    TFSignal,
    _ta_direction,
)
from core.event_bus import Event, EventBus


# ── helpers ──────────────────────────────────────────────────────────────────

def make_bus():
    return EventBus()


def make_ta_event(symbol, tf, rsi=50, macd_hist=0.0, ema_9=100.0, ema_21=99.0, close=100.5):
    return Event(
        type=f"ta.{symbol}.{tf}.updated",
        data={
            "symbol": symbol,
            "timeframe": tf,
            "rsi_14": rsi,
            "macd_hist": macd_hist,
            "ema_9": ema_9,
            "ema_21": ema_21,
            "close": close,
        },
    )


# ── _ta_direction ─────────────────────────────────────────────────────────────

def test_ta_direction_bull_rsi_oversold():
    result = _ta_direction({"rsi_14": 25, "macd_hist": 0.1, "ema_9": 100, "ema_21": 99, "close": 101})
    assert result is not None
    assert result.direction == "bull"


def test_ta_direction_bear_rsi_overbought():
    result = _ta_direction({"rsi_14": 75, "macd_hist": -0.1, "ema_9": 99, "ema_21": 100, "close": 98})
    assert result is not None
    assert result.direction == "bear"


def test_ta_direction_neutral_returns_none():
    result = _ta_direction({"rsi_14": 50})
    assert result is None


def test_ta_direction_strength_capped_at_1():
    result = _ta_direction({"rsi_14": 25, "macd_hist": 0.5, "ema_9": 100, "ema_21": 99, "close": 101})
    assert result is not None
    assert result.strength <= 1.0


def test_ta_direction_missing_fields():
    result = _ta_direction({})
    assert result is None


# ── MTFConfluenceEngine score ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_zero_with_no_signals():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)
    score = engine.get_score("BTC/USDT", "bull")
    assert score == 0.0


@pytest.mark.asyncio
async def test_score_increases_with_bull_ta_signal():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)

    # Simulate a bullish TA signal on 1h
    event = make_ta_event("BTC/USDT", "1h", rsi=25, macd_hist=0.1, ema_9=100, ema_21=99, close=101)
    await engine._on_ta_update(event)

    score = engine.get_score("BTC/USDT", "bull")
    assert score > 0.0


@pytest.mark.asyncio
async def test_score_bear_not_inflated_by_bull_signal():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)

    event = make_ta_event("BTC/USDT", "1h", rsi=25, macd_hist=0.1, ema_9=100, ema_21=99, close=101)
    await engine._on_ta_update(event)

    bear_score = engine.get_score("BTC/USDT", "bear")
    bull_score = engine.get_score("BTC/USDT", "bull")
    assert bull_score > bear_score


@pytest.mark.asyncio
async def test_smc_confirm_multiplies_score():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)

    # Weak signal: only MACD positive → base ~25, below cap
    event = make_ta_event("BTC/USDT", "1h", rsi=50, macd_hist=0.1, ema_9=None, ema_21=None, close=None)
    await engine._on_ta_update(event)
    score_before = engine.get_score("BTC/USDT", "bull")
    assert 0 < score_before < 100

    smc_event = Event("smc.bos.detected", {"symbol": "BTC/USDT", "direction": "bull"})
    await engine._on_smc_event(smc_event)
    score_after = engine.get_score("BTC/USDT", "bull")

    assert score_after > score_before


@pytest.mark.asyncio
async def test_spoof_reduces_score():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)

    event = make_ta_event("BTC/USDT", "1h", rsi=25, macd_hist=0.1, ema_9=100, ema_21=99, close=101)
    await engine._on_ta_update(event)
    score_before = engine.get_score("BTC/USDT", "bull")

    spoof_event = Event("ob.spoof_detected", {"symbol": "BTC/USDT"})
    await engine._on_spoof(spoof_event)
    score_after = engine.get_score("BTC/USDT", "bull")

    assert score_after < score_before


@pytest.mark.asyncio
async def test_volume_cvd_bull_confirms():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)

    event = make_ta_event("BTC/USDT", "1h", rsi=50, macd_hist=0.1, ema_9=None, ema_21=None, close=None)
    await engine._on_ta_update(event)
    score_before = engine.get_score("BTC/USDT", "bull")

    cvd_event = Event("volume.cvd.updated", {"symbol": "BTC/USDT", "cvd": 500.0})
    await engine._on_cvd_update(cvd_event)
    score_after = engine.get_score("BTC/USDT", "bull")

    assert score_after > score_before


@pytest.mark.asyncio
async def test_ob_imbalance_bull_confirms():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)

    event = make_ta_event("BTC/USDT", "1h", rsi=50, macd_hist=0.1, ema_9=None, ema_21=None, close=None)
    await engine._on_ta_update(event)
    score_before = engine.get_score("BTC/USDT", "bull")

    ob_event = Event("ob.state_updated", {"symbol": "BTC/USDT", "imbalance": 0.3})
    await engine._on_ob_update(ob_event)
    score_after = engine.get_score("BTC/USDT", "bull")

    assert score_after > score_before


@pytest.mark.asyncio
async def test_score_capped_at_100():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)

    # Pile on every bullish signal across all timeframes
    for tf in ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]:
        e = make_ta_event("BTC/USDT", tf, rsi=25, macd_hist=0.5, ema_9=100, ema_21=99, close=101)
        await engine._on_ta_update(e)

    await engine._on_smc_event(Event("smc.bos.detected", {"symbol": "BTC/USDT", "direction": "bull"}))
    await engine._on_cvd_update(Event("volume.cvd.updated", {"symbol": "BTC/USDT", "cvd": 1000.0}))
    await engine._on_ob_update(Event("ob.state_updated", {"symbol": "BTC/USDT", "imbalance": 0.5}))

    score = engine.get_score("BTC/USDT", "bull")
    assert score <= 100.0


@pytest.mark.asyncio
async def test_ta_signal_removed_when_neutral():
    bus = make_bus()
    engine = MTFConfluenceEngine(bus)

    bull_event = make_ta_event("BTC/USDT", "1h", rsi=25, macd_hist=0.1, ema_9=100, ema_21=99, close=101)
    await engine._on_ta_update(bull_event)
    assert engine.get_score("BTC/USDT", "bull") > 0.0

    # Fully neutral: rsi neutral, macd=0, no EMA data → _ta_direction returns None
    neutral_event = Event(
        type="ta.BTC/USDT.1h.updated",
        data={"symbol": "BTC/USDT", "timeframe": "1h", "rsi_14": 50, "macd_hist": 0.0},
    )
    await engine._on_ta_update(neutral_event)
    assert engine.get_score("BTC/USDT", "bull") == 0.0


@pytest.mark.asyncio
async def test_mtf_published_events():
    bus = make_bus()
    await bus.start()
    engine = MTFConfluenceEngine(bus)

    received = []
    bus.subscribe("mtf.score.updated", lambda e: received.append(e.data))

    event = make_ta_event("BTC/USDT", "1h", rsi=25, macd_hist=0.1, ema_9=100, ema_21=99, close=101)
    await engine._on_ta_update(event)

    import asyncio
    await asyncio.sleep(0.05)

    assert any(r["symbol"] == "BTC/USDT" for r in received)
    await bus.stop()
