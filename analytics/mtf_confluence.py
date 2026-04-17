"""
MTF Confluence Engine — многотаймфреймный скоринг сигналов.

Собирает подтверждения от всех аналитических модулей по всем ТФ
и вычисляет итоговый score (0–100) для каждого символа и направления.

Публикует: mtf.score.updated
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from core.event_bus import Event, EventBus
from core.logger import get_logger

log = get_logger("MTFConfluence")

# ─── Веса таймфреймов (сумма ≈ 1.0) ─────────────────────────────────────────
TF_WEIGHTS: dict[str, float] = {
    "1m": 0.05, "3m": 0.07, "5m": 0.10,
    "15m": 0.12, "30m": 0.13, "1h": 0.15,
    "4h": 0.17, "1d": 0.12, "1W": 0.06, "1M": 0.03,
}

# ─── Пороги ──────────────────────────────────────────────────────────────────
SCORE_MIN_SIGNAL = 60.0      # минимум для генерации сигнала
SCORE_MIN_AUTO = 80.0        # минимум для авто-исполнения

# ─── Множители ───────────────────────────────────────────────────────────────
MULT_SMC_CONFIRM = 1.15      # +15% если SMC подтверждает
MULT_VOLUME_CONFIRM = 1.10   # +10% если Volume (CVD + OI) подтверждает
MULT_OB_CONFIRM = 1.10       # +10% если OB imbalance в нужную сторону
MULT_FEAR_GREED_AGAINST = 0.80   # -20% если Fear&Greed экстремален против
MULT_SPOOF = 0.70            # -30% если обнаружен spoof

# Окно жизни сигнала от каждого модуля (сколько новых событий держим)
SIGNAL_TTL = 10


@dataclass
class TFSignal:
    """Направленный сигнал от одного ТФ."""
    direction: Literal["bull", "bear"]
    strength: float = 1.0  # 0..1, насколько сильный сигнал


@dataclass
class SymbolState:
    """Состояние всех сигналов по одному символу."""
    # {timeframe: TFSignal}
    ta_signals: dict[str, TFSignal] = field(default_factory=dict)
    smc_confirmed: dict[str, bool] = field(default_factory=lambda: {"bull": False, "bear": False})
    volume_confirmed: dict[str, bool] = field(default_factory=lambda: {"bull": False, "bear": False})
    ob_imbalance: float = 0.0       # >0 = бычий давление, <0 = медвежий
    spoof_active: bool = False
    fear_greed: int | None = None   # 0–100


def _ta_direction(ta_result: dict) -> TFSignal | None:
    """
    Определяет направление сигнала из результатов TA.
    Использует RSI, MACD histogram, EMA cross.
    """
    rsi = ta_result.get("rsi_14")
    macd_hist = ta_result.get("macd_hist")
    ema_9 = ta_result.get("ema_9")
    ema_21 = ta_result.get("ema_21")
    close = ta_result.get("close")

    bull_score = 0
    bear_score = 0

    if rsi is not None:
        if rsi < 30:
            bull_score += 2  # перепродан → потенциальный разворот вверх
        elif rsi > 70:
            bear_score += 2
        elif 40 <= rsi <= 60:
            pass  # нейтрально

    if macd_hist is not None:
        if macd_hist > 0:
            bull_score += 1
        elif macd_hist < 0:
            bear_score += 1

    if ema_9 and ema_21 and close:
        if ema_9 > ema_21 and close > ema_9:
            bull_score += 1
        elif ema_9 < ema_21 and close < ema_9:
            bear_score += 1

    if bull_score == 0 and bear_score == 0:
        return None

    if bull_score > bear_score:
        strength = min(bull_score / 4.0, 1.0)
        return TFSignal(direction="bull", strength=strength)
    elif bear_score > bull_score:
        strength = min(bear_score / 4.0, 1.0)
        return TFSignal(direction="bear", strength=strength)
    return None


class MTFConfluenceEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        # {symbol: SymbolState}
        self._states: dict[str, SymbolState] = defaultdict(SymbolState)

    async def start(self) -> None:
        # TA результаты по всем ТФ
        for tf in TF_WEIGHTS:
            self._bus.subscribe(f"ta.*.{tf}.updated", self._on_ta_update)
        # Подписываемся через общий паттерн нельзя в нашей реализации,
        # поэтому подписываемся на конкретные события
        self._bus.subscribe("ta_any", self._on_ta_update)  # будет перезаписано ниже

        # SMC
        for evt in ("smc.bos.detected", "smc.choch.detected", "smc.fvg.detected"):
            self._bus.subscribe(evt, self._on_smc_event)

        # Volume CVD
        self._bus.subscribe("volume.cvd.updated", self._on_cvd_update)

        # OB imbalance
        self._bus.subscribe("ob.state_updated", self._on_ob_update)

        # Spoof
        self._bus.subscribe("ob.spoof_detected", self._on_spoof)

        log.info("MTF Confluence Engine запущен")

    async def stop(self) -> None:
        log.info("MTF Confluence Engine остановлен")

    def subscribe_ta_for_symbols(self, symbols: list[str]) -> None:
        """Вызывается после инициализации символов для подписки на ta.* события."""
        for symbol in symbols:
            for tf in TF_WEIGHTS:
                self._bus.subscribe(f"ta.{symbol}.{tf}.updated", self._on_ta_update)

    async def _on_ta_update(self, event: Event) -> None:
        ta = event.data
        symbol = ta.get("symbol")
        tf = ta.get("timeframe")
        if not symbol or not tf:
            return

        state = self._states[symbol]
        signal = _ta_direction(ta)
        if signal:
            state.ta_signals[tf] = signal
        elif tf in state.ta_signals:
            del state.ta_signals[tf]

        await self._recalculate(symbol)

    async def _on_smc_event(self, event: Event) -> None:
        data = event.data
        symbol = data.get("symbol")
        direction = data.get("direction")
        if not symbol or direction not in ("bull", "bear"):
            return
        state = self._states[symbol]
        state.smc_confirmed[direction] = True
        await self._recalculate(symbol)

    async def _on_cvd_update(self, event: Event) -> None:
        data = event.data
        symbol = data.get("symbol")
        cvd = data.get("cvd", 0.0)
        if not symbol:
            return
        state = self._states[symbol]
        # CVD > 0 → покупатели доминируют → бычье подтверждение
        state.volume_confirmed["bull"] = cvd > 0
        state.volume_confirmed["bear"] = cvd < 0
        await self._recalculate(symbol)

    async def _on_ob_update(self, event: Event) -> None:
        data = event.data
        symbol = data.get("symbol")
        imbalance = data.get("imbalance", 0.0)
        if not symbol:
            return
        self._states[symbol].ob_imbalance = imbalance
        await self._recalculate(symbol)

    async def _on_spoof(self, event: Event) -> None:
        symbol = event.data.get("symbol")
        if symbol:
            self._states[symbol].spoof_active = True
            log.warning(f"Spoof активен для {symbol} → score снижен на 30%")
            await self._recalculate(symbol)

    async def _recalculate(self, symbol: str) -> None:
        state = self._states[symbol]

        for direction in ("bull", "bear"):
            score = self._compute_score(state, direction)
            await self._bus.publish("mtf.score.updated", {
                "symbol": symbol,
                "direction": direction,
                "score": round(score, 2),
                "actionable": score >= SCORE_MIN_SIGNAL,
                "auto_eligible": score >= SCORE_MIN_AUTO,
                "ta_signals_count": sum(
                    1 for s in state.ta_signals.values() if s.direction == direction
                ),
            })

    def _compute_score(self, state: SymbolState, direction: str) -> float:
        # ── Базовый score: взвешенная сумма TA сигналов ──────────────────────
        base = 0.0
        total_weight = 0.0
        for tf, signal in state.ta_signals.items():
            w = TF_WEIGHTS.get(tf, 0.05)
            if signal.direction == direction:
                base += w * signal.strength * 100
            total_weight += w

        # Нормализуем к 0–100 относительно задействованных весов
        if total_weight > 0:
            base = base / total_weight
        else:
            return 0.0

        score = base

        # ── Множители ────────────────────────────────────────────────────────
        if state.smc_confirmed.get(direction):
            score *= MULT_SMC_CONFIRM

        if state.volume_confirmed.get(direction):
            score *= MULT_VOLUME_CONFIRM

        ob_confirms = (
            (direction == "bull" and state.ob_imbalance > 0.1) or
            (direction == "bear" and state.ob_imbalance < -0.1)
        )
        if ob_confirms:
            score *= MULT_OB_CONFIRM

        if state.fear_greed is not None:
            # Fear&Greed экстремален против сигнала
            extreme_against = (
                (direction == "bull" and state.fear_greed <= 20) or
                (direction == "bear" and state.fear_greed >= 80)
            )
            if extreme_against:
                score *= MULT_FEAR_GREED_AGAINST

        if state.spoof_active:
            score *= MULT_SPOOF

        return min(score, 100.0)

    def get_score(self, symbol: str, direction: str) -> float:
        """Синхронно возвращает текущий score."""
        state = self._states.get(symbol)
        if not state:
            return 0.0
        return self._compute_score(state, direction)
