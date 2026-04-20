import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.logger import get_logger

log = get_logger("Database")


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        db_path = os.getenv("DB_PATH", "data/terminal.db")
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        url = f"sqlite+aiosqlite:///{db_path}"
        _engine = create_async_engine(
            url,
            echo=False,
            connect_args={
                "timeout": 30,
                "check_same_thread": False,
            },
        )
        log.info(f"БД подключена: {db_path}")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    """Создаёт все таблицы если не существуют. Включает WAL-режим. Выполняет миграции."""
    from storage import models  # noqa: F401
    from sqlalchemy import text
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=30000"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        await _run_migrations(conn)
    log.info("Таблицы БД созданы/проверены")


async def _run_migrations(conn) -> None:
    """Применяет инкрементальные миграции схемы."""
    from sqlalchemy import text

    migrations = [
        # backtest_results
        ("ALTER TABLE backtest_results ADD COLUMN trades_detail TEXT NOT NULL DEFAULT '[]'",
         "backtest_results.trades_detail"),
        # candles: market_type + data_trust_score
        ("ALTER TABLE candles ADD COLUMN market_type TEXT NOT NULL DEFAULT 'spot'",
         "candles.market_type"),
        ("ALTER TABLE candles ADD COLUMN data_trust_score INTEGER DEFAULT 100",
         "candles.data_trust_score"),
        # trades_raw: market_type
        ("ALTER TABLE trades_raw ADD COLUMN market_type TEXT NOT NULL DEFAULT 'spot'",
         "trades_raw.market_type"),
        # orderbook_snapshots: market_type
        ("ALTER TABLE orderbook_snapshots ADD COLUMN market_type TEXT NOT NULL DEFAULT 'spot'",
         "orderbook_snapshots.market_type"),
        # market_snapshots: market_type + basis
        ("ALTER TABLE market_snapshots ADD COLUMN market_type TEXT NOT NULL DEFAULT 'spot'",
         "market_snapshots.market_type"),
        ("ALTER TABLE market_snapshots ADD COLUMN basis REAL",
         "market_snapshots.basis"),
    ]

    for sql, name in migrations:
        try:
            await conn.execute(text(sql))
            log.info(f"Миграция применена: {name}")
        except Exception:
            pass  # Колонка/таблица уже существует

    # Миграция уникального индекса candles: добавляем market_type в constraint.
    # SQLite не поддерживает DROP CONSTRAINT — делаем через пересоздание таблицы.
    await _migrate_candles_unique_constraint(conn)


async def _migrate_candles_unique_constraint(conn) -> None:
    """
    Обновляет уникальный индекс candles с (symbol, timeframe, open_time)
    на (symbol, timeframe, open_time, market_type).
    Безопасно: работает только если старый индекс ещё существует.
    """
    from sqlalchemy import text

    # Проверяем текущие индексы таблицы candles
    result = await conn.execute(text("PRAGMA index_list(candles)"))
    indexes = {row[1] for row in result.fetchall()}  # имена индексов

    # Если уже есть новый индекс с market_type — миграция не нужна
    if "uq_candles" in indexes:
        result2 = await conn.execute(text("PRAGMA index_info(uq_candles)"))
        cols = {row[2] for row in result2.fetchall()}
        if "market_type" in cols:
            return  # уже актуально

    log.info("Миграция: пересоздаём уникальный индекс candles с market_type...")
    try:
        await conn.execute(text("DROP INDEX IF EXISTS uq_candles"))
        await conn.execute(text("DROP INDEX IF EXISTS idx_candles_lookup"))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_candles "
            "ON candles(symbol, timeframe, open_time, market_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_candles_lookup "
            "ON candles(symbol, timeframe, open_time, market_type)"
        ))
        log.info("Миграция uq_candles завершена")
    except Exception as e:
        log.warning(f"Миграция uq_candles: {e}")


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        log.info("Соединение с БД закрыто")
