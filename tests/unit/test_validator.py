import pytest
from pydantic import ValidationError
from data.validator import Candle, Trade, OrderBookSnapshot, OrderBookLevel


def make_candle(**kwargs) -> Candle:
    defaults = dict(
        symbol="BTC/USDT", timeframe="1m", open_time=1_700_000_000_000,
        open=40000.0, high=40500.0, low=39800.0, close=40200.0, volume=100.0,
    )
    return Candle(**(defaults | kwargs))


def test_valid_candle():
    c = make_candle()
    assert c.symbol == "BTC/USDT"
    assert c.source == "exchange"


def test_candle_negative_price_raises():
    with pytest.raises(ValidationError):
        make_candle(open=-1.0)


def test_candle_zero_price_raises():
    with pytest.raises(ValidationError):
        make_candle(close=0.0)


def test_candle_negative_volume_raises():
    with pytest.raises(ValidationError):
        make_candle(volume=-10.0)


def test_candle_high_less_than_low_raises():
    with pytest.raises(ValidationError):
        make_candle(high=39000.0, low=40000.0)


def test_valid_trade():
    t = Trade(symbol="ETH/USDT", timestamp=1_700_000_000_000, price=2000.0, quantity=1.5, side="buy")
    assert t.side == "buy"


def test_trade_invalid_side_raises():
    with pytest.raises(ValidationError):
        Trade(symbol="ETH/USDT", timestamp=1_700_000_000_000, price=2000.0, quantity=1.5, side="hold")


def test_orderbook_imbalance():
    bids = [OrderBookLevel(price=40000, quantity=10), OrderBookLevel(price=39999, quantity=5)]
    asks = [OrderBookLevel(price=40001, quantity=5)]
    ob = OrderBookSnapshot(symbol="BTC/USDT", timestamp=1_700_000_000_000, bids=bids, asks=asks)
    assert ob.bid_volume == 15.0
    assert ob.ask_volume == 5.0
    assert ob.imbalance == pytest.approx((15 - 5) / 20)
