"""Централизованная конфигурация приложения.

Читает переменные окружения из .env и предоставляет typed-доступ ко всем настройкам.
Поддерживает два режима: collector (VPS) и terminal (Desktop).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

RunMode = Literal["collector", "terminal"]


@dataclass
class AppConfig:
    # ── Режим запуска ──────────────────────────────────────────────────────
    RUN_MODE: RunMode = "terminal"

    # ── Торговые пары ──────────────────────────────────────────────────────
    SYMBOLS: list[str] = field(default_factory=lambda: [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    ])

    # ── VPS (только для terminal) ──────────────────────────────────────────
    VPS_HOST: str = "132.243.235.173"
    VPS_PORT: int = 8800
    VPS_API_KEY: str = ""

    # ── BingX Private API (только для terminal) ────────────────────────────
    BINGX_API_KEY: str = ""
    BINGX_API_SECRET: str = ""

    # ── БД ─────────────────────────────────────────────────────────────────
    DB_PATH: str = "data/terminal.db"

    # ── Логирование ────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── Торговые параметры ─────────────────────────────────────────────────
    TRADING_MODE: str = "paper"  # live | paper
    EXECUTION_MODE: str = "alert_only"  # auto | semi_auto | alert_only
    INITIAL_CAPITAL: float = 10000.0
    MAX_RISK_PER_TRADE: float = 0.02
    MAX_OPEN_POSITIONS: int = 5
    MAX_DAILY_DRAWDOWN: float = 0.05
    MAX_TOTAL_DRAWDOWN: float = 0.15
    DEFAULT_LEVERAGE: int = 5

    # ── WS сервер (локальный, для UI) ──────────────────────────────────────
    WS_HOST: str = "localhost"
    WS_PORT: int = 8765

    # ── Telegram ───────────────────────────────────────────────────────────
    TELEGRAM_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # ── Внешние API ────────────────────────────────────────────────────────
    NEWS_API_KEY: str = ""

    @property
    def is_collector(self) -> bool:
        return self.RUN_MODE == "collector"

    @property
    def is_terminal(self) -> bool:
        return self.RUN_MODE == "terminal"

    @property
    def is_live(self) -> bool:
        return self.TRADING_MODE == "live"

    @property
    def vps_url(self) -> str:
        return f"http://{self.VPS_HOST}:{self.VPS_PORT}"

    @property
    def vps_ws_url(self) -> str:
        return f"ws://{self.VPS_HOST}:{self.VPS_PORT}/ws"


def _parse_symbols(raw: str) -> list[str]:
    """Парсит строку SYMBOLS из .env в список."""
    return [s.strip() for s in raw.split(",") if s.strip()]


def load_config() -> AppConfig:
    """Загружает конфигурацию из переменных окружения."""
    raw_symbols = os.getenv("SYMBOLS", "")
    symbols = _parse_symbols(raw_symbols) if raw_symbols else [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    ]

    return AppConfig(
        RUN_MODE=os.getenv("RUN_MODE", "terminal"),  # type: ignore[arg-type]
        SYMBOLS=symbols,
        VPS_HOST=os.getenv("VPS_HOST", "132.243.235.173"),
        VPS_PORT=int(os.getenv("VPS_PORT", "8800")),
        VPS_API_KEY=os.getenv("VPS_API_KEY", ""),
        BINGX_API_KEY=os.getenv("BINGX_API_KEY", ""),
        BINGX_API_SECRET=os.getenv("BINGX_API_SECRET", ""),
        DB_PATH=os.getenv("DB_PATH", "data/terminal.db"),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        TRADING_MODE=os.getenv("TRADING_MODE", "paper"),
        EXECUTION_MODE=os.getenv("EXECUTION_MODE", "alert_only"),
        INITIAL_CAPITAL=float(os.getenv("INITIAL_CAPITAL", "10000")),
        MAX_RISK_PER_TRADE=float(os.getenv("MAX_RISK_PER_TRADE", "0.02")),
        MAX_OPEN_POSITIONS=int(os.getenv("MAX_OPEN_POSITIONS", "5")),
        MAX_DAILY_DRAWDOWN=float(os.getenv("MAX_DAILY_DRAWDOWN", "0.05")),
        MAX_TOTAL_DRAWDOWN=float(os.getenv("MAX_TOTAL_DRAWDOWN", "0.15")),
        DEFAULT_LEVERAGE=int(os.getenv("DEFAULT_LEVERAGE", "5")),
        WS_HOST=os.getenv("WS_HOST", "localhost"),
        WS_PORT=int(os.getenv("WS_PORT", "8765")),
        TELEGRAM_TOKEN=os.getenv("TELEGRAM_TOKEN", ""),
        TELEGRAM_CHAT_ID=os.getenv("TELEGRAM_CHAT_ID", ""),
        NEWS_API_KEY=os.getenv("NEWS_API_KEY", ""),
    )


# Глобальный синглтон конфигурации (загружается один раз при импорте)
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Возвращает глобальную конфигурацию (синглтон)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
