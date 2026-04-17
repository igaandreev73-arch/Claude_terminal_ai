"""
Risk Guard — управление риском и расчёт размера позиции.

Проверяет каждый сигнал перед исполнением:
  - Не превышен дневной лимит убытков
  - Не превышено максимальное количество позиций
  - Минимальный score для режима авто
  - Достаточно капитала для входа

Рассчитывает размер позиции по модели фиксированного риска:
  size_usd = capital × risk_pct / sl_pct
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from core.logger import get_logger

log = get_logger("RiskGuard")


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 1.0      # % капитала рискуем за сделку
    max_daily_loss_pct: float = 5.0      # дневной стоп-лосс в % от начального капитала
    max_open_positions: int = 3          # максимум одновременных позиций
    max_leverage: int = 10               # максимально допустимое плечо
    min_score_auto: float = 80.0         # минимальный score для авто-исполнения
    min_score_semi: float = 60.0         # минимальный score для semi-auto


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    position_size_usd: float = 0.0
    leverage: int = 1


class RiskGuard:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()
        self._open_positions: int = 0
        self._daily_pnl: float = 0.0
        self._initial_capital: float = 0.0
        self._day: date = datetime.now(timezone.utc).date()

    def set_capital(self, capital: float) -> None:
        self._initial_capital = capital

    def check(
        self,
        symbol: str,
        score: float,
        auto_mode: bool,
        capital: float,
        sl_pct: float,
        leverage: int = 1,
    ) -> RiskDecision:
        """Проверяет можно ли открыть позицию и возвращает размер."""
        self._refresh_day()

        # Минимальный score
        min_score = self._config.min_score_auto if auto_mode else self._config.min_score_semi
        if score < min_score:
            return RiskDecision(
                allowed=False,
                reason=f"Score {score:.1f} ниже порога {min_score:.1f}",
            )

        # Дневной лимит убытков
        if self._initial_capital > 0:
            daily_loss_pct = -self._daily_pnl / self._initial_capital * 100
            if daily_loss_pct >= self._config.max_daily_loss_pct:
                return RiskDecision(
                    allowed=False,
                    reason=f"Дневной лимит убытков {self._config.max_daily_loss_pct}% достигнут",
                )

        # Максимум открытых позиций
        if self._open_positions >= self._config.max_open_positions:
            return RiskDecision(
                allowed=False,
                reason=f"Максимум позиций {self._config.max_open_positions} открыто",
            )

        # Плечо
        if leverage > self._config.max_leverage:
            return RiskDecision(
                allowed=False,
                reason=f"Плечо {leverage}x превышает лимит {self._config.max_leverage}x",
            )

        # Размер позиции по формуле фиксированного риска
        size_usd = self._calc_size(capital, sl_pct, leverage)
        if size_usd <= 0:
            return RiskDecision(allowed=False, reason="Нулевой размер позиции")

        return RiskDecision(
            allowed=True,
            reason="OK",
            position_size_usd=round(size_usd, 2),
            leverage=leverage,
        )

    def on_position_opened(self) -> None:
        self._open_positions += 1

    def on_position_closed(self, pnl: float) -> None:
        self._open_positions = max(0, self._open_positions - 1)
        self._daily_pnl += pnl

    def get_daily_pnl(self) -> float:
        self._refresh_day()
        return self._daily_pnl

    def get_open_positions(self) -> int:
        return self._open_positions

    def _calc_size(self, capital: float, sl_pct: float, leverage: int) -> float:
        """
        Размер позиции чтобы при срабатывании SL потерять не более risk_per_trade_pct % капитала.
        size = (capital × risk_pct) / sl_pct × leverage
        """
        if sl_pct <= 0:
            return 0.0
        risk_amount = capital * self._config.risk_per_trade_pct / 100
        return risk_amount / (sl_pct / leverage)

    def _refresh_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._day:
            self._day = today
            self._daily_pnl = 0.0
            log.info("RiskGuard: дневной PnL сброшен")
