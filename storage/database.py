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
                "timeout": 30,           # ждём до 30с при блокировке
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
    """Создаёт все таблицы если не существуют. Включает WAL-режим."""
    from storage import models  # noqa: F401 — нужен чтобы зарегистрировать модели в Base.metadata
    from sqlalchemy import text
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # WAL позволяет параллельные читатели при одном писателе
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=30000"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
    log.info("Таблицы БД созданы/проверены")


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        log.info("Соединение с БД закрыто")
