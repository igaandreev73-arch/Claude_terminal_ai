from sqlalchemy import Boolean, Float, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class CandleModel(Base):
    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    open_time: Mapped[int] = mapped_column(Integer, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(Text, default="exchange")
    created_at: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "open_time", name="uq_candles"),
        Index("idx_candles_lookup", "symbol", "timeframe", "open_time"),
    )


class TradeRawModel(Base):
    __tablename__ = "trades_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    trade_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)


class OrderBookSnapshotModel(Base):
    __tablename__ = "orderbook_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    bids_top5: Mapped[str] = mapped_column(Text, nullable=False)   # JSON
    asks_top5: Mapped[str] = mapped_column(Text, nullable=False)   # JSON
    bid_volume: Mapped[float | None] = mapped_column(Float)
    ask_volume: Mapped[float | None] = mapped_column(Float)
    imbalance: Mapped[float | None] = mapped_column(Float)
    trigger: Mapped[str] = mapped_column(Text, default="periodic")


class MarketMetricsModel(Base):
    __tablename__ = "market_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    open_interest: Mapped[float | None] = mapped_column(Float)
    funding_rate: Mapped[float | None] = mapped_column(Float)
    long_short_ratio: Mapped[float | None] = mapped_column(Float)
    fear_greed_index: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("symbol", "timestamp", name="uq_metrics"),)


class SignalModel(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    indicators: Mapped[str | None] = mapped_column(Text)
    mtf_confirm: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[int] = mapped_column(Integer)


class TradeJournalModel(Base):
    __tablename__ = "trades_journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    sl_price: Mapped[float | None] = mapped_column(Float)
    tp_price: Mapped[float | None] = mapped_column(Float)
    pnl_usdt: Mapped[float | None] = mapped_column(Float)
    pnl_percent: Mapped[float | None] = mapped_column(Float)
    commission: Mapped[float | None] = mapped_column(Float)
    entry_time: Mapped[int] = mapped_column(Integer, nullable=False)
    exit_time: Mapped[int | None] = mapped_column(Integer)
    signal_id: Mapped[int | None] = mapped_column(Integer)
    execution_mode: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(Text)


class StrategyModel(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    fingerprint: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[int | None] = mapped_column(Integer)


class AnomalyModel(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    data_snapshot: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketSnapshotModel(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)


class SystemLogModel(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text)


class TaskModel(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)      # backfill, validation
    symbol: Mapped[str | None] = mapped_column(Text)
    period: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)    # running, paused, completed, error, cancelled
    percent: Mapped[int] = mapped_column(Integer, default=0)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    total_saved: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint_end_ms: Mapped[int | None] = mapped_column(Integer)  # for resume
    speed_cps: Mapped[float] = mapped_column(Float, default=0)      # candles/sec
    result: Mapped[str | None] = mapped_column(Text)   # JSON result on completion
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)


class BacktestResultModel(Base):
    __tablename__ = "backtest_results"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[int | None] = mapped_column(Integer)
    period_end: Mapped[int | None] = mapped_column(Integer)
    params: Mapped[str] = mapped_column(Text, nullable=False)        # JSON
    metrics: Mapped[str] = mapped_column(Text, nullable=False)       # JSON
    equity_curve: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    trades_count: Mapped[int] = mapped_column(Integer, default=0)
    is_optimization: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index("idx_backtest_strategy", "strategy_id", "symbol", "timeframe"),
    )
