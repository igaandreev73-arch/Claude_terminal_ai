import json
import time
from sqlalchemy.dialects.sqlite import insert

from storage.database import get_session_factory
from storage.models import OrderBookSnapshotModel
from core.logger import get_logger

log = get_logger("OrderBookRepo")


class OrderBookRepository:

    async def save_snapshot(self, snapshot: dict) -> None:
        """
        Сохраняет снимок стакана.
        snapshot: dict с ключами symbol, timestamp, bids_top5, asks_top5,
                  bid_volume, ask_volume, imbalance, trigger.
        """
        factory = get_session_factory()
        async with factory() as session:
            stmt = insert(OrderBookSnapshotModel).values(
                symbol=snapshot["symbol"],
                timestamp=snapshot.get("timestamp", int(time.time() * 1000)),
                bids_top5=json.dumps(snapshot.get("bids_top5", [])),
                asks_top5=json.dumps(snapshot.get("asks_top5", [])),
                bid_volume=snapshot.get("bid_volume"),
                ask_volume=snapshot.get("ask_volume"),
                imbalance=snapshot.get("imbalance"),
                trigger=snapshot.get("trigger", "periodic"),
            )
            await session.execute(stmt)
            await session.commit()

    async def save_from_event(self, event_data: dict) -> None:
        """Обёртка для прямого использования с Event Bus."""
        try:
            await self.save_snapshot(event_data)
        except Exception as e:
            log.error(f"Ошибка сохранения снимка стакана: {e}")
