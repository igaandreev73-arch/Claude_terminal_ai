"""
Correlation Engine — анализ корреляций.

- Pearson корреляция каждой пары с BTC и ETH (скользящее окно)
- Матрица корреляций между парами портфеля
- Режим рынка: пара идёт сама или следует за BTC/ETH
- Дивергенция: пара должна была пойти с BTC, но не пошла → торговая возможность

Публикует:
  correlation.updated      — корреляция пары с BTC/ETH
  correlation.divergence   — обнаружена дивергенция
  correlation.matrix       — матрица корреляций (периодически)
"""
from __future__ import annotations

import math
from collections import defaultdict, deque

from core.event_bus import Event, EventBus
from core.logger import get_logger
from data.validator import Candle

log = get_logger("Correlation")

REFERENCE_SYMBOLS = ("BTC/USDT", "ETH/USDT")
WINDOW_SIZE = 50          # свечей для скользящей корреляции
MIN_WINDOW = 20           # минимум для расчёта
DIVERGENCE_THRESHOLD = 0.7   # корреляция выше этого = сильная связь
DIVERGENCE_DELTA = 0.03      # разница в % движении для сигнала дивергенции
MATRIX_INTERVAL = 20         # публиковать матрицу каждые N обновлений


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Коэффициент корреляции Пирсона для двух списков одинаковой длины."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 6)


def pct_changes(prices: list[float]) -> list[float]:
    """Процентные изменения цены."""
    if len(prices) < 2:
        return []
    return [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]


class CorrelationEngine:
    def __init__(self, event_bus: EventBus, symbols: list[str]) -> None:
        self._bus = event_bus
        self._symbols = symbols
        # {symbol: deque[close_price]}
        self._closes: dict[str, deque] = defaultdict(lambda: deque(maxlen=WINDOW_SIZE + 1))
        self._update_count = 0

    async def start(self) -> None:
        self._bus.subscribe("candle.1m.closed", self._on_candle)
        log.info(f"Correlation Engine запущен для {len(self._symbols)} символов")

    async def stop(self) -> None:
        log.info("Correlation Engine остановлен")

    async def _on_candle(self, event: Event) -> None:
        candle: Candle = event.data
        self._closes[candle.symbol].append(candle.close)

        # Считаем только если символ отслеживаемый
        if candle.symbol not in self._symbols:
            return

        self._update_count += 1

        await self._calc_pair_correlation(candle.symbol)

        if self._update_count % MATRIX_INTERVAL == 0:
            await self._publish_matrix()

    async def _calc_pair_correlation(self, symbol: str) -> None:
        closes_sym = list(self._closes[symbol])
        if len(closes_sym) < MIN_WINDOW:
            return

        changes_sym = pct_changes(closes_sym)

        for ref in REFERENCE_SYMBOLS:
            if ref == symbol:
                continue

            closes_ref = list(self._closes[ref])
            if len(closes_ref) < MIN_WINDOW:
                continue

            changes_ref = pct_changes(closes_ref)
            n = min(len(changes_sym), len(changes_ref))
            if n < MIN_WINDOW - 1:
                continue

            corr = pearson(changes_sym[-n:], changes_ref[-n:])
            if corr is None:
                continue

            # Режим рынка
            regime = _market_regime(corr)

            result = {
                "symbol": symbol,
                "reference": ref,
                "correlation": corr,
                "window": n,
                "regime": regime,
            }

            await self._bus.publish("correlation.updated", result)

            # Проверка дивергенции
            div = _check_divergence(changes_sym, changes_ref, corr)
            if div:
                log.info(f"Дивергенция: {symbol} vs {ref} — {div['description']}")
                await self._bus.publish("correlation.divergence", {
                    "symbol": symbol,
                    "reference": ref,
                    "correlation": corr,
                    **div,
                })

    async def _publish_matrix(self) -> None:
        """Строит и публикует матрицу корреляций между всеми отслеживаемыми символами."""
        matrix: dict[str, dict[str, float | None]] = {}

        for sym_a in self._symbols:
            matrix[sym_a] = {}
            closes_a = list(self._closes[sym_a])
            changes_a = pct_changes(closes_a) if len(closes_a) >= 2 else []

            for sym_b in self._symbols:
                if sym_a == sym_b:
                    matrix[sym_a][sym_b] = 1.0
                    continue
                closes_b = list(self._closes[sym_b])
                changes_b = pct_changes(closes_b) if len(closes_b) >= 2 else []
                n = min(len(changes_a), len(changes_b))
                if n < MIN_WINDOW - 1:
                    matrix[sym_a][sym_b] = None
                    continue
                matrix[sym_a][sym_b] = pearson(changes_a[-n:], changes_b[-n:])

        await self._bus.publish("correlation.matrix", {"matrix": matrix})

    def get_correlation(self, symbol: str, reference: str) -> float | None:
        """Синхронный расчёт последней корреляции."""
        closes_sym = list(self._closes[symbol])
        closes_ref = list(self._closes[reference])
        if len(closes_sym) < MIN_WINDOW or len(closes_ref) < MIN_WINDOW:
            return None
        n = min(len(closes_sym), len(closes_ref))
        ch_sym = pct_changes(closes_sym[-n:])
        ch_ref = pct_changes(closes_ref[-n:])
        m = min(len(ch_sym), len(ch_ref))
        return pearson(ch_sym[-m:], ch_ref[-m:])


def _market_regime(corr: float) -> str:
    """Определяет режим движения пары относительно референса."""
    if corr >= DIVERGENCE_THRESHOLD:
        return "following"       # следует за референсом
    elif corr <= -DIVERGENCE_THRESHOLD:
        return "inverse"         # движется обратно
    else:
        return "independent"     # движется самостоятельно


def _check_divergence(
    changes_sym: list[float],
    changes_ref: list[float],
    corr: float,
) -> dict | None:
    """
    Дивергенция: корреляция высокая (пара обычно следует за BTC),
    но за последние N свечей они пошли в разные стороны.
    """
    if corr < DIVERGENCE_THRESHOLD or len(changes_sym) < 3 or len(changes_ref) < 3:
        return None

    recent_sym = sum(changes_sym[-3:])
    recent_ref = sum(changes_ref[-3:])

    # Разные знаки движения и достаточная величина
    if (recent_sym * recent_ref < 0 and
            abs(recent_sym) > DIVERGENCE_DELTA and
            abs(recent_ref) > DIVERGENCE_DELTA):

        direction = "bull" if recent_sym > 0 else "bear"
        return {
            "direction": direction,
            "sym_move_pct": round(recent_sym * 100, 3),
            "ref_move_pct": round(recent_ref * 100, 3),
            "description": (
                f"BTC {'вырос' if recent_ref > 0 else 'упал'} "
                f"на {abs(recent_ref)*100:.2f}%, но пара "
                f"{'выросла' if recent_sym > 0 else 'упала'} "
                f"на {abs(recent_sym)*100:.2f}%"
            ),
        }
    return None
