import time
from sqlalchemy import select, delete
from sqlalchemy.dialects.sqlite import insert

from storage.database import get_session_factory
from storage.models import CandleModel
from data.validator import Candle
from core.logger import get_logger

log = get_logger("CandlesRepo")


class CandlesRepository:

    async def upsert(self, candle: Candle) -> None:
        """Вставляет свечу или обновляет если уже существует (по symbol+timeframe+open_time)."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                insert(CandleModel)
                .values(
                    symbol=candle.symbol,
                    timeframe=candle.timeframe,
                    open_time=candle.open_time,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    is_closed=candle.is_closed,
                    source=candle.source,
                    created_at=int(time.time()),
                )
                .on_conflict_do_update(
                    index_elements=["symbol", "timeframe", "open_time"],
                    set_=dict(
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        is_closed=candle.is_closed,
                    ),
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def upsert_many(self, candles: list[Candle]) -> int:
        """Пакетная вставка. Возвращает количество обработанных записей."""
        if not candles:
            return 0
        BATCH_SIZE = 500
        now = int(time.time())
        factory = get_session_factory()
        async with factory() as session:
            for i in range(0, len(candles), BATCH_SIZE):
                batch = candles[i : i + BATCH_SIZE]
                rows = [
                    dict(
                        symbol=c.symbol,
                        timeframe=c.timeframe,
                        open_time=c.open_time,
                        open=c.open,
                        high=c.high,
                        low=c.low,
                        close=c.close,
                        volume=c.volume,
                        is_closed=c.is_closed,
                        source=c.source,
                        created_at=now,
                    )
                    for c in batch
                ]
                stmt = insert(CandleModel).values(rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "timeframe", "open_time"],
                    set_={
                        col: getattr(stmt.excluded, col)
                        for col in ("high", "low", "close", "volume", "is_closed")
                    },
                )
                await session.execute(stmt)
            await session.commit()
        return len(candles)

    async def get_latest(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        """Возвращает последние N закрытых свечей, отсортированных по времени (старые → новые)."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(CandleModel)
                .where(
                    CandleModel.symbol == symbol,
                    CandleModel.timeframe == timeframe,
                    CandleModel.is_closed == True,
                )
                .order_by(CandleModel.open_time.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        candles = [
            Candle(
                symbol=row.symbol,
                timeframe=row.timeframe,
                open_time=row.open_time,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                is_closed=row.is_closed,
                source=row.source,
            )
            for row in reversed(rows)  # возвращаем хронологически
        ]
        return candles

    async def get_range(
        self, symbol: str, timeframe: str, start_time: int, end_time: int
    ) -> list[Candle]:
        """Возвращает свечи в диапазоне [start_time, end_time] (Unix ms)."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(CandleModel)
                .where(
                    CandleModel.symbol == symbol,
                    CandleModel.timeframe == timeframe,
                    CandleModel.open_time >= start_time,
                    CandleModel.open_time <= end_time,
                    CandleModel.is_closed == True,
                )
                .order_by(CandleModel.open_time)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            Candle(
                symbol=row.symbol,
                timeframe=row.timeframe,
                open_time=row.open_time,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                is_closed=row.is_closed,
                source=row.source,
            )
            for row in rows
        ]

    async def count(self, symbol: str, timeframe: str) -> int:
        from sqlalchemy import func
        factory = get_session_factory()
        async with factory() as session:
            stmt = select(func.count()).select_from(CandleModel).where(
                CandleModel.symbol == symbol,
                CandleModel.timeframe == timeframe,
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def delete_before(self, symbol: str, timeframe: str, before_time: int) -> int:
        """Удаляет старые свечи до before_time (Unix ms). Возвращает количество удалённых."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = delete(CandleModel).where(
                CandleModel.symbol == symbol,
                CandleModel.timeframe == timeframe,
                CandleModel.open_time < before_time,
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def delete_timeframe(self, symbol: str, timeframe: str) -> int:
        """Удаляет все свечи указанного таймфрейма для символа."""
        factory = get_session_factory()
        async with factory() as session:
            stmt = delete(CandleModel).where(
                CandleModel.symbol == symbol,
                CandleModel.timeframe == timeframe,
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
