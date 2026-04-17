from pydantic import BaseModel, field_validator, model_validator
from typing import Literal, Self


class Candle(BaseModel):
    symbol: str
    timeframe: str
    open_time: int       # Unix ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool = True
    source: Literal["exchange", "aggregated"] = "exchange"

    @field_validator("open", "high", "low", "close")
    @classmethod
    def price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Цена должна быть > 0, получено: {v}")
        return v

    @field_validator("volume")
    @classmethod
    def volume_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"Объём не может быть отрицательным: {v}")
        return v

    @model_validator(mode="after")
    def high_gte_low(self) -> Self:
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) не может быть меньше Low ({self.low})")
        return self


class Trade(BaseModel):
    symbol: str
    timestamp: int       # Unix ms
    price: float
    quantity: float
    side: Literal["buy", "sell"]
    trade_id: str | None = None

    @field_validator("price", "quantity")
    @classmethod
    def positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Значение должно быть > 0: {v}")
        return v


class OrderBookLevel(BaseModel):
    price: float
    quantity: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    timestamp: int
    bids: list[OrderBookLevel]   # от лучшего к худшему (высокая → низкая цена)
    asks: list[OrderBookLevel]   # от лучшего к худшему (низкая → высокая цена)

    @property
    def bid_volume(self) -> float:
        return sum(lvl.quantity for lvl in self.bids)

    @property
    def ask_volume(self) -> float:
        return sum(lvl.quantity for lvl in self.asks)

    @property
    def imbalance(self) -> float:
        total = self.bid_volume + self.ask_volume
        if total == 0:
            return 0.0
        return (self.bid_volume - self.ask_volume) / total
