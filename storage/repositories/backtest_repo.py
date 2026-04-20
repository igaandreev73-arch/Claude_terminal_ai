from __future__ import annotations

import json
import time
import uuid

from sqlalchemy import desc, select
from sqlalchemy.dialects.sqlite import insert

from core.logger import get_logger
from storage.database import get_session_factory
from storage.models import BacktestResultModel

log = get_logger("BacktestRepo")

_TRADE_FIELDS = ("params", "metrics", "equity_curve", "trades_count",
                 "trades_detail", "is_optimization", "created_at")


class BacktestRepository:

    async def save(self, data: dict) -> str:
        rid = data.get("id") or str(uuid.uuid4())
        factory = get_session_factory()
        row = {
            "id": rid,
            "strategy_id": data["strategy_id"],
            "symbol": data["symbol"],
            "timeframe": data["timeframe"],
            "period_start": data.get("period_start"),
            "period_end": data.get("period_end"),
            "params": json.dumps(data.get("params") or {}),
            "metrics": json.dumps(data.get("metrics") or {}),
            "equity_curve": json.dumps(data.get("equity_curve") or []),
            "trades_count": data.get("trades_count", 0),
            "trades_detail": json.dumps(data.get("trades_detail") or []),
            "is_optimization": data.get("is_optimization", False),
            "created_at": data.get("created_at", int(time.time())),
        }
        async with factory() as session:
            stmt = insert(BacktestResultModel).values(**row).on_conflict_do_update(
                index_elements=["id"],
                set_={col: getattr(insert(BacktestResultModel).values(**row).excluded, col)
                      for col in _TRADE_FIELDS},
            )
            await session.execute(stmt)
            await session.commit()
        return rid

    async def get_latest(self, strategy_id: str, symbol: str, timeframe: str) -> dict | None:
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(BacktestResultModel)
                .where(
                    BacktestResultModel.strategy_id == strategy_id,
                    BacktestResultModel.symbol == symbol,
                    BacktestResultModel.timeframe == timeframe,
                )
                .order_by(desc(BacktestResultModel.created_at))
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _row_to_dict(row) if row else None

    async def list_for_strategy(self, strategy_id: str) -> list[dict]:
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(BacktestResultModel)
                .where(BacktestResultModel.strategy_id == strategy_id)
                .order_by(desc(BacktestResultModel.created_at))
                .limit(100)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: BacktestResultModel) -> dict:
    return {
        "id": row.id,
        "strategy_id": row.strategy_id,
        "symbol": row.symbol,
        "timeframe": row.timeframe,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "params": json.loads(row.params),
        "metrics": json.loads(row.metrics),
        "equity_curve": json.loads(row.equity_curve),
        "trades_count": row.trades_count,
        "trades_detail": json.loads(row.trades_detail or "[]"),
        "is_optimization": row.is_optimization,
        "created_at": row.created_at,
    }
