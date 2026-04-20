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
    market_type: Mapped[str] = mapped_column(Text, default="spot")        # 'spot' | 'futures'
    data_trust_score: Mapped[int] = mapped_column(Integer, default=100)   # 0–100
    created_at: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "open_time", "market_type", name="uq_candles"),
        Index("idx_candles_lookup", "symbol", "timeframe", "open_time", "market_type"),
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
    market_type: Mapped[str] = mapped_column(Text, default="spot")


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
    market_type: Mapped[str] = mapped_column(Text, default="spot")


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


class FuturesMetricsModel(Base):
    """Метрики специфичные для фьючерсного рынка."""
    __tablename__ = "futures_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    open_interest: Mapped[float | None] = mapped_column(Float)
    funding_rate: Mapped[float | None] = mapped_column(Float)
    long_short_ratio: Mapped[float | None] = mapped_column(Float)
    mark_price: Mapped[float | None] = mapped_column(Float)
    index_price: Mapped[float | None] = mapped_column(Float)
    basis: Mapped[float | None] = mapped_column(Float)         # futures_price - spot_price
    basis_pct: Mapped[float | None] = mapped_column(Float)     # basis / spot_price * 100

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uq_futures_metrics"),
        Index("idx_futures_metrics", "symbol", "timestamp"),
    )


class LiquidationModel(Base):
    """Ликвидации — только WebSocket, невосстанавливаемые."""
    __tablename__ = "liquidations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)    # 'long' | 'short'
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    value_usd: Mapped[float | None] = mapped_column(Float)
    liq_type: Mapped[str] = mapped_column(Text, default="forced")  # 'forced' | 'auto'

    __table_args__ = (
        Index("idx_liquidations", "symbol", "timestamp"),
    )


class DataVerificationLogModel(Base):
    """Лог результатов верификации данных."""
    __tablename__ = "data_verification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    market_type: Mapped[str] = mapped_column(Text, default="spot")
    period_start: Mapped[int] = mapped_column(Integer, nullable=False)
    period_end: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)        # 1-4
    status: Mapped[str] = mapped_column(Text, nullable=False)          # verified/mismatch_found/needs_review/repaired
    match_pct: Mapped[float | None] = mapped_column(Float)             # % совпадения с биржей
    total_checked: Mapped[int] = mapped_column(Integer, default=0)
    total_missing: Mapped[int] = mapped_column(Integer, default=0)
    total_mismatch: Mapped[int] = mapped_column(Integer, default=0)
    auto_repaired: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[str | None] = mapped_column(Text)                  # JSON
    verified_at: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("idx_verification_log", "symbol", "timeframe", "verified_at"),
    )


class DataGapModel(Base):
    """Известные пропуски в данных."""
    __tablename__ = "data_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)       # 'candles' | 'liquidations' | 'cvd' | 'orderbook'
    market_type: Mapped[str] = mapped_column(Text, default="spot")
    gap_start: Mapped[int] = mapped_column(Integer, nullable=False)    # ms timestamp
    gap_end: Mapped[int] = mapped_column(Integer, nullable=False)      # ms timestamp
    cause: Mapped[str | None] = mapped_column(Text)                    # 'ws_disconnect' | 'api_error' | ...
    recoverable: Mapped[bool] = mapped_column(Boolean, default=True)
    recovery_status: Mapped[str] = mapped_column(Text, default="pending")  # pending/in_progress/recovered/unrecoverable
    detected_at: Mapped[int] = mapped_column(Integer, nullable=False)
    recovered_at: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("idx_data_gaps", "symbol", "data_type", "gap_start"),
    )


class StorageStatsModel(Base):
    """Ежедневная статистика объёма базы по температурам (горячая/тёплая/холодная)."""
    __tablename__ = "storage_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recorded_at: Mapped[int] = mapped_column(Integer, nullable=False)   # unix timestamp (день)
    hot_mb: Mapped[float] = mapped_column(Float, default=0)             # < 90 дней
    warm_mb: Mapped[float] = mapped_column(Float, default=0)            # 90 дней – 12 мес
    cold_mb: Mapped[float] = mapped_column(Float, default=0)            # > 12 мес
    total_mb: Mapped[float] = mapped_column(Float, default=0)
    hot_rows: Mapped[int] = mapped_column(Integer, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    growth_mb_7d: Mapped[float] = mapped_column(Float, default=0)       # прирост за 7 дней
    forecast_full_days: Mapped[int | None] = mapped_column(Integer)     # прогноз заполнения диска


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
    market_type: Mapped[str] = mapped_column(Text, default="spot")
    basis: Mapped[float | None] = mapped_column(Float)


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
    type: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str | None] = mapped_column(Text)
    period: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    percent: Mapped[int] = mapped_column(Integer, default=0)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    total_saved: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint_end_ms: Mapped[int | None] = mapped_column(Integer)
    speed_cps: Mapped[float] = mapped_column(Float, default=0)
    result: Mapped[str | None] = mapped_column(Text)
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
    params: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[str] = mapped_column(Text, nullable=False)
    equity_curve: Mapped[str] = mapped_column(Text, nullable=False)
    trades_count: Mapped[int] = mapped_column(Integer, default=0)
    trades_detail: Mapped[str] = mapped_column(Text, default="[]")
    is_optimization: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index("idx_backtest_strategy", "strategy_id", "symbol", "timeframe"),
    )
