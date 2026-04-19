import io
import os
import sys
from loguru import logger

_configured = False


def setup_logger() -> None:
    global _configured
    if _configured:
        return

    logger.remove()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Force UTF-8 on Windows consoles that default to cp1251/cp1252
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{extra[module]}</cyan> | {message}",
        colorize=True,
    )

    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        level="INFO",          # файл всегда INFO, консоль — по LOG_LEVEL
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {extra[module]} | {message}",
        rotation="10 MB",
        retention=7,           # храним последние 7 файлов (~70 МБ максимум)
        encoding="utf-8",
        compression="gz",      # сжимаем ротированные файлы
    )

    _configured = True


def get_logger(module_name: str):
    setup_logger()
    return logger.bind(module=module_name)
