"""
Signal Engine — генерация и управление торговыми сигналами.

Источники сигналов:
  - mtf.score.updated   (MTF Confluence score ≥ порога)
  - correlation.divergence (дивергенция от BTC/ETH)

Управление:
  - Сигналы живут TTL секунд, после чего публикуется signal.expired
  - Очередь сигналов доступна через get_queue()
  - Дублирующие сигналы (тот же symbol+direction за TTL) игнорируются

Публикует:
  signal.generated   — новый сигнал
  signal.expired     — сигнал истёк без исполнения
  signal.executed    — сигнал помечен исполненным (внешний вызов)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.event_bus import Event, EventBus
from core.logger import get_logger

log = get_logger("SignalEngine")

SCORE_MIN_SIGNAL = 60.0          # минимум для генерации сигнала
SCORE_MIN_AUTO = 80.0            # минимум для авто-исполнения
SIGNAL_TTL_SEC = 300             # 5 минут жизни сигнала
DIVERGENCE_MIN_CORR = 0.7        # корреляция для сигнала дивергенции


@dataclass
class TradingSignal:
    id: str
    symbol: str
    direction: str               # "bull" | "bear"
    score: float
    source: str                  # "mtf_confluence" | "divergence"
    created_at: datetime
    expires_at: datetime
    auto_eligible: bool
    details: dict = field(default_factory=dict)
    executed: bool = False

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class SignalEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        # {signal_id: TradingSignal}
        self._queue: dict[str, TradingSignal] = {}
        # {symbol+direction: signal_id} — last active signal per pair+direction
        self._active: dict[str, str] = {}

    async def start(self) -> None:
        self._bus.subscribe("mtf.score.updated", self._on_mtf_score)
        self._bus.subscribe("correlation.divergence", self._on_divergence)
        log.info("Signal Engine запущен")

    async def stop(self) -> None:
        log.info(f"Signal Engine остановлен. Активных сигналов: {len(self._queue)}")

    async def tick(self) -> None:
        """Вызывается периодически для проверки истёкших сигналов."""
        expired = [sid for sid, s in self._queue.items() if s.is_expired() and not s.executed]
        for sid in expired:
            signal = self._queue.pop(sid)
            key = f"{signal.symbol}:{signal.direction}"
            self._active.pop(key, None)
            log.debug(f"Сигнал истёк: {signal.symbol} {signal.direction} score={signal.score:.1f}")
            await self._bus.publish("signal.expired", {
                "id": sid,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "score": signal.score,
            })

    def get_queue(self) -> list[TradingSignal]:
        """Возвращает список активных (не истёкших, не исполненных) сигналов."""
        return [
            s for s in self._queue.values()
            if not s.is_expired() and not s.executed
        ]

    async def mark_executed(self, signal_id: str) -> None:
        """Помечает сигнал исполненным."""
        signal = self._queue.get(signal_id)
        if signal:
            signal.executed = True
            key = f"{signal.symbol}:{signal.direction}"
            self._active.pop(key, None)
            await self._bus.publish("signal.executed", {
                "id": signal_id,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "score": signal.score,
            })

    async def _on_mtf_score(self, event: Event) -> None:
        data = event.data
        symbol = data.get("symbol")
        direction = data.get("direction")
        score = data.get("score", 0.0)
        auto_eligible = data.get("auto_eligible", False)

        if not symbol or not direction or score < SCORE_MIN_SIGNAL:
            return

        key = f"{symbol}:{direction}"
        # Не создаём дублирующий сигнал если уже есть активный
        existing_id = self._active.get(key)
        if existing_id and existing_id in self._queue:
            existing = self._queue[existing_id]
            if not existing.is_expired() and not existing.executed:
                return

        await self._create_signal(
            symbol=symbol,
            direction=direction,
            score=score,
            source="mtf_confluence",
            auto_eligible=auto_eligible,
            details={"ta_signals_count": data.get("ta_signals_count", 0)},
        )

    async def _on_divergence(self, event: Event) -> None:
        data = event.data
        symbol = data.get("symbol")
        direction = data.get("direction")
        corr = data.get("correlation", 0.0)

        if not symbol or not direction or corr < DIVERGENCE_MIN_CORR:
            return

        # Дивергенция — среднеприоритетный сигнал, score = 65
        score = 65.0
        await self._create_signal(
            symbol=symbol,
            direction=direction,
            score=score,
            source="divergence",
            auto_eligible=False,
            details={
                "reference": data.get("reference"),
                "correlation": corr,
                "sym_move_pct": data.get("sym_move_pct"),
                "ref_move_pct": data.get("ref_move_pct"),
            },
        )

    async def _create_signal(
        self,
        symbol: str,
        direction: str,
        score: float,
        source: str,
        auto_eligible: bool,
        details: dict,
    ) -> None:
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        signal = TradingSignal(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            direction=direction,
            score=score,
            source=source,
            created_at=now,
            expires_at=now + timedelta(seconds=SIGNAL_TTL_SEC),
            auto_eligible=auto_eligible,
            details=details,
        )
        self._queue[signal.id] = signal
        self._active[f"{symbol}:{direction}"] = signal.id

        log.info(
            f"Сигнал: {symbol} {direction.upper()} score={score:.1f} "
            f"[{source}] auto={auto_eligible}"
        )
        await self._bus.publish("signal.generated", {
            "id": signal.id,
            "symbol": symbol,
            "direction": direction,
            "score": score,
            "source": source,
            "auto_eligible": auto_eligible,
            "details": details,
        })
