"""
Инициализация базы данных.
Запуск: python scripts/init_db.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from storage.database import init_db, close_db
from core.logger import get_logger

log = get_logger("init_db")


async def main() -> None:
    log.info("Инициализация базы данных...")
    await init_db()
    log.info("База данных готова")
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
