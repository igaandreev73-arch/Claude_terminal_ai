import os
import pytest
from data.validator import Candle
from storage.database import init_db, close_db


# Используем тестовую in-memory БД
os.environ.setdefault("DB_PATH", ":memory:")


@pytest.fixture(autouse=True)
async def setup_db():
    # Сброс синглтона перед каждым тестом
    import storage.database as db_module
    db_module._engine = None
    db_module._session_factory = None
    os.environ["DB_PATH"] = ":memory:"
    await init_db()
    yield
    await close_db()


def make_candle(open_time: int = 1_700_000_000_000, close: float = 40000.0) -> Candle:
    return Candle(
        symbol="BTC/USDT",
        timeframe="1m",
        open_time=open_time,
        open=39900.0,
        high=40500.0,
        low=39800.0,
        close=close,
        volume=100.0,
    )


async def test_upsert_and_get_latest():
    from storage.repositories.candles_repo import CandlesRepository
    repo = CandlesRepository()
    candle = make_candle()
    await repo.upsert(candle)
    result = await repo.get_latest("BTC/USDT", "1m", limit=10)
    assert len(result) == 1
    assert result[0].close == 40000.0


async def test_upsert_updates_existing():
    from storage.repositories.candles_repo import CandlesRepository
    repo = CandlesRepository()
    await repo.upsert(make_candle(close=40000.0))
    await repo.upsert(make_candle(close=41000.0))  # тот же open_time
    result = await repo.get_latest("BTC/USDT", "1m")
    assert len(result) == 1
    assert result[0].close == 41000.0


async def test_upsert_many():
    from storage.repositories.candles_repo import CandlesRepository
    repo = CandlesRepository()
    candles = [make_candle(open_time=1_700_000_000_000 + i * 60_000) for i in range(5)]
    count = await repo.upsert_many(candles)
    assert count == 5
    result = await repo.get_latest("BTC/USDT", "1m", limit=10)
    assert len(result) == 5


async def test_count():
    from storage.repositories.candles_repo import CandlesRepository
    repo = CandlesRepository()
    await repo.upsert_many([make_candle(open_time=1_700_000_000_000 + i * 60_000) for i in range(3)])
    assert await repo.count("BTC/USDT", "1m") == 3


async def test_get_range():
    from storage.repositories.candles_repo import CandlesRepository
    repo = CandlesRepository()
    base = 1_700_000_000_000
    await repo.upsert_many([make_candle(open_time=base + i * 60_000) for i in range(10)])
    result = await repo.get_range("BTC/USDT", "1m", base, base + 4 * 60_000)
    assert len(result) == 5  # 0..4 включительно


async def test_delete_before():
    from storage.repositories.candles_repo import CandlesRepository
    repo = CandlesRepository()
    base = 1_700_000_000_000
    await repo.upsert_many([make_candle(open_time=base + i * 60_000) for i in range(10)])
    deleted = await repo.delete_before("BTC/USDT", "1m", base + 5 * 60_000)
    assert deleted == 5
    assert await repo.count("BTC/USDT", "1m") == 5
