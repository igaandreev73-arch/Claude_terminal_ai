"""
Execution Engine — три режима исполнения торговых сигналов.

Режимы (переключаются без перезапуска):
  AUTO       — score ≥ 80 → исполняется автоматически
  SEMI_AUTO  — сигнал → ожидание подтверждения N секунд → исполнение или истечение
  ALERT_ONLY — только уведомление, без исполнения

Реагирует на аномалии:
  anomaly.flash_crash → блокирует новые входы
  anomaly.ob_manip    → задержка входа (MANIP_DELAY_SEC)
  anomaly.slippage    → обновляет slippage модель

Публикует:
  execution.signal_received   — сигнал получен
  execution.order_placed      — ордер отправлен на биржу
  execution.position_opened   — позиция открыта
  execution.position_closed   — позиция закрыта
  execution.blocked           — вход заблокирован (risk / anomaly)
  execution.pending           — ждём подтверждения (semi_auto)
  execution.confirmed         — подтверждено пользователем
  execution.rejected          — отклонено пользователем / таймаут
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from core.event_bus import Event, EventBus
from core.logger import get_logger
from execution.bingx_private import BingXPrivateClient
from execution.risk_guard import RiskGuard
from signals.signal_engine import TradingSignal

log = get_logger("ExecutionEngine")

SEMI_AUTO_TIMEOUT_SEC = 30      # таймаут подтверждения в semi-auto
MANIP_DELAY_SEC = 10            # задержка входа при ob_manip
DEFAULT_SL_PCT = 0.02           # 2% SL если не указан
DEFAULT_TP_PCT = 0.04           # 4% TP если не указан
DEFAULT_LEVERAGE = 3            # плечо по умолчанию


class ExecutionMode(Enum):
    AUTO = "auto"
    SEMI_AUTO = "semi_auto"
    ALERT_ONLY = "alert_only"


@dataclass
class ActivePosition:
    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    size_usd: float
    sl_pct: float
    tp_pct: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PendingConfirmation:
    signal: TradingSignal
    size_usd: float
    deadline: float           # time.monotonic() deadline


class ExecutionEngine:
    def __init__(
        self,
        event_bus: EventBus,
        risk_guard: RiskGuard,
        api_client: BingXPrivateClient,
        initial_capital: float = 10_000.0,
        mode: ExecutionMode = ExecutionMode.SEMI_AUTO,
    ) -> None:
        self._bus = event_bus
        self._risk = risk_guard
        self._api = api_client
        self._capital = initial_capital
        self._mode = mode

        self._risk.set_capital(initial_capital)

        # {symbol: ActivePosition}
        self._positions: dict[str, ActivePosition] = {}
        # {signal_id: PendingConfirmation} — only in semi_auto
        self._pending: dict[str, PendingConfirmation] = {}

        self._flash_crash_active: bool = False
        self._manip_symbols: set[str] = set()

    @property
    def mode(self) -> ExecutionMode:
        return self._mode

    def set_mode(self, mode: ExecutionMode) -> None:
        log.info(f"Режим исполнения изменён: {self._mode.value} → {mode.value}")
        self._mode = mode

    def get_positions(self) -> list[dict]:
        return [
            {
                "symbol": p.symbol,
                "direction": p.direction,
                "entry_price": p.entry_price,
                "size_usd": p.size_usd,
                "opened_at": p.opened_at.isoformat(),
            }
            for p in self._positions.values()
        ]

    async def start(self) -> None:
        self._bus.subscribe("signal.generated", self._on_signal)
        self._bus.subscribe("anomaly.flash_crash", self._on_flash_crash)
        self._bus.subscribe("anomaly.ob_manip", self._on_ob_manip)
        self._bus.subscribe("position.closed_externally", self._on_external_close)
        log.info(f"Execution Engine запущен, режим: {self._mode.value}, капитал: {self._capital:.2f}")

    async def stop(self) -> None:
        log.info(f"Execution Engine остановлен. Открытых позиций: {len(self._positions)}")

    # ── Signal handling ───────────────────────────────────────────────────────

    async def _on_signal(self, event: Event) -> None:
        data = event.data
        symbol = data.get("symbol", "")
        direction = data.get("direction", "")
        score = data.get("score", 0.0)
        signal_id = data.get("id", "")
        auto_eligible = data.get("auto_eligible", False)

        await self._bus.publish("execution.signal_received", {
            "id": signal_id, "symbol": symbol, "direction": direction,
            "score": score, "mode": self._mode.value,
        })

        # Блокировки
        if self._flash_crash_active:
            await self._blocked(signal_id, symbol, "Flash crash активен — входы заблокированы")
            return

        if symbol in self._positions:
            await self._blocked(signal_id, symbol, "Позиция уже открыта")
            return

        # Risk check
        decision = self._risk.check(
            symbol=symbol,
            score=score,
            auto_mode=(self._mode == ExecutionMode.AUTO),
            capital=self._capital,
            sl_pct=DEFAULT_SL_PCT,
            leverage=DEFAULT_LEVERAGE,
        )
        if not decision.allowed:
            await self._blocked(signal_id, symbol, decision.reason)
            return

        if self._mode == ExecutionMode.ALERT_ONLY:
            log.info(f"[Alert] Сигнал: {symbol} {direction.upper()} score={score:.1f}")
            return

        if self._mode == ExecutionMode.AUTO and auto_eligible:
            await self._execute(signal_id, symbol, direction, decision.position_size_usd)

        elif self._mode == ExecutionMode.SEMI_AUTO:
            import time
            pending = PendingConfirmation(
                signal=TradingSignal(
                    id=signal_id, symbol=symbol, direction=direction,
                    score=score, source="", created_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc),
                    auto_eligible=auto_eligible,
                ),
                size_usd=decision.position_size_usd,
                deadline=time.monotonic() + SEMI_AUTO_TIMEOUT_SEC,
            )
            self._pending[signal_id] = pending
            log.info(
                f"[Semi-auto] Ожидание подтверждения: {symbol} {direction.upper()} "
                f"score={score:.1f} размер={decision.position_size_usd:.2f} USD"
            )
            await self._bus.publish("execution.pending", {
                "id": signal_id, "symbol": symbol, "direction": direction,
                "score": score, "size_usd": decision.position_size_usd,
                "timeout_sec": SEMI_AUTO_TIMEOUT_SEC,
            })

    async def confirm(self, signal_id: str) -> None:
        """Подтверждение входа пользователем (semi-auto)."""
        import time
        pending = self._pending.pop(signal_id, None)
        if not pending:
            log.warning(f"Подтверждение для несуществующего сигнала: {signal_id}")
            return
        if time.monotonic() > pending.deadline:
            log.info(f"Сигнал {signal_id} истёк до подтверждения")
            await self._bus.publish("execution.rejected", {
                "id": signal_id, "reason": "timeout",
            })
            return
        await self._bus.publish("execution.confirmed", {"id": signal_id})
        await self._execute(
            signal_id,
            pending.signal.symbol,
            pending.signal.direction,
            pending.size_usd,
        )

    async def reject(self, signal_id: str) -> None:
        """Отклонение сигнала пользователем."""
        self._pending.pop(signal_id, None)
        await self._bus.publish("execution.rejected", {"id": signal_id, "reason": "user"})
        log.info(f"Сигнал {signal_id} отклонён пользователем")

    async def close_position(self, symbol: str, reason: str = "manual") -> None:
        """Закрывает открытую позицию."""
        pos = self._positions.pop(symbol, None)
        if not pos:
            log.warning(f"Попытка закрыть несуществующую позицию: {symbol}")
            return
        direction = "SHORT" if pos.direction == "bear" else "LONG"
        await self._api.close_position(symbol, direction, pos.size_usd)
        self._risk.on_position_closed(pnl=0.0)  # реальный PnL придёт от биржи
        log.info(f"Позиция закрыта: {symbol} ({reason})")
        await self._bus.publish("execution.position_closed", {
            "symbol": symbol, "reason": reason,
            "entry_price": pos.entry_price, "size_usd": pos.size_usd,
        })

    # ── Anomaly handlers ──────────────────────────────────────────────────────

    async def _on_flash_crash(self, event: Event) -> None:
        self._flash_crash_active = True
        log.warning(f"Flash crash! Все новые входы заблокированы. {event.data}")
        # Сбросить через 5 минут
        asyncio.get_event_loop().call_later(300, self._clear_flash_crash)

    async def _on_ob_manip(self, event: Event) -> None:
        symbol = event.data.get("symbol", "")
        if symbol:
            self._manip_symbols.add(symbol)
            log.warning(f"OB манипуляция на {symbol}, вход задержан на {MANIP_DELAY_SEC}s")
            asyncio.get_event_loop().call_later(
                MANIP_DELAY_SEC, lambda: self._manip_symbols.discard(symbol)
            )

    def _clear_flash_crash(self) -> None:
        self._flash_crash_active = False
        log.info("Flash crash флаг снят — входы разблокированы")

    async def _on_external_close(self, event: Event) -> None:
        symbol = event.data.get("symbol", "")
        pnl = event.data.get("pnl", 0.0)
        if symbol in self._positions:
            self._positions.pop(symbol)
            self._risk.on_position_closed(pnl)

    # ── Execution ─────────────────────────────────────────────────────────────

    async def _execute(
        self, signal_id: str, symbol: str, direction: str, size_usd: float
    ) -> None:
        if symbol in self._manip_symbols:
            await self._blocked(signal_id, symbol, "OB манипуляция — вход задержан")
            return

        side = "BUY" if direction == "bull" else "SELL"
        pos_side = "LONG" if direction == "bull" else "SHORT"

        result = await self._api.place_order(
            symbol=symbol,
            side=side,
            position_side=pos_side,
            order_type="MARKET",
            quantity=size_usd,
        )

        entry_price = result.get("data", {}).get("price", 0.0) if isinstance(result.get("data"), dict) else 0.0

        pos = ActivePosition(
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            size_usd=size_usd,
            sl_pct=DEFAULT_SL_PCT,
            tp_pct=DEFAULT_TP_PCT,
        )
        self._positions[symbol] = pos
        self._risk.on_position_opened()

        log.info(
            f"Позиция открыта: {symbol} {direction.upper()} "
            f"size={size_usd:.2f} USD"
        )
        await self._bus.publish("execution.position_opened", {
            "signal_id": signal_id,
            "symbol": symbol,
            "direction": direction,
            "size_usd": size_usd,
            "entry_price": entry_price,
            "mode": self._mode.value,
        })

    async def _blocked(self, signal_id: str, symbol: str, reason: str) -> None:
        log.info(f"Вход заблокирован [{symbol}]: {reason}")
        await self._bus.publish("execution.blocked", {
            "id": signal_id, "symbol": symbol, "reason": reason,
        })
