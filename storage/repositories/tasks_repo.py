import time
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from storage.database import get_session_factory
from storage.models import TaskModel
from core.logger import get_logger

log = get_logger("TasksRepo")


class TasksRepository:

    async def upsert(self, task: dict) -> None:
        """Вставляет или обновляет задачу по task_id."""
        factory = get_session_factory()
        now = int(time.time())
        row = {**task, "updated_at": now}
        if "created_at" not in row:
            row["created_at"] = now

        async with factory() as session:
            base_stmt = insert(TaskModel).values(**row)
            update_cols = {
                col: getattr(base_stmt.excluded, col)
                for col in (
                    "status", "percent", "fetched", "total_pages",
                    "total_saved", "checkpoint_end_ms", "speed_cps",
                    "result", "error", "updated_at",
                )
            }
            stmt = base_stmt.on_conflict_do_update(
                index_elements=["task_id"],
                set_=update_cols,
            )
            await session.execute(stmt)
            await session.commit()

    async def get(self, task_id: str) -> dict | None:
        """Возвращает задачу по task_id или None."""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(TaskModel).where(TaskModel.task_id == task_id)
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_dict(row)

    async def get_paused(self) -> list[dict]:
        """Возвращает все задачи со статусом 'paused'."""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(TaskModel)
                .where(TaskModel.status == "paused")
                .order_by(TaskModel.updated_at.desc())
            )
            rows = result.scalars().all()
        return [_row_to_dict(r) for r in rows]

    async def get_recent(self, limit: int = 20) -> list[dict]:
        """Возвращает последние N завершённых/ошибочных задач."""
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(TaskModel)
                .where(TaskModel.status.in_(["completed", "error", "cancelled"]))
                .order_by(TaskModel.updated_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
        return [_row_to_dict(r) for r in rows]

    async def mark_status(self, task_id: str, status: str, **kwargs) -> None:
        """Обновляет статус и дополнительные поля задачи."""
        task = await self.get(task_id)
        if task is None:
            return
        task.update({"status": status, **kwargs})
        await self.upsert(task)


def _row_to_dict(row: TaskModel) -> dict:
    return {
        "task_id":          row.task_id,
        "type":             row.type,
        "symbol":           row.symbol,
        "period":           row.period,
        "status":           row.status,
        "percent":          row.percent,
        "fetched":          row.fetched,
        "total_pages":      row.total_pages,
        "total_saved":      row.total_saved,
        "checkpoint_end_ms": row.checkpoint_end_ms,
        "speed_cps":        row.speed_cps,
        "result":           row.result,
        "error":            row.error,
        "created_at":       row.created_at,
        "updated_at":       row.updated_at,
    }
