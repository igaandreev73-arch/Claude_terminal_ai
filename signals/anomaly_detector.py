"""
Anomaly Detector — обнаружение рыночных аномалий в реальном времени.

Детектирует:
  - Flash crash: цена упала > FLASH_CRASH_PCT за FLASH_CRASH_CANDLES свечей
  - Price spike: цена выросла > PRICE_SPIKE_PCT за одну свечу
  - OB manipulation: spoofing + высокий дисбаланс стакана одновременно
  - Slippage anomaly: фактический slippage превысил ожидаемый

Публикует:
  anomaly.flash_crash    — резкое падение цены
  anomaly.price_spike    — резкий рост цены
  anomaly.ob_manip       — манипуляция стаканом
  anomaly.slippage       — аномальный slippage
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

from core.event_bus import Event, EventBus
from core.logger import get_logger

log = get_logger("AnomalyDetector")

FLASH_CRASH_PCT = 3.0        # % падения за окно
FLASH_CRASH_CANDLES = 3      # окно свечей
PRICE_SPIKE_PCT = 3.0        # % роста за одну свечу
OB_MANIP_IMBALANCE = 0.4     # порог дисбаланса стакана для манипуляции
SLIPPAGE_ANOMALY_MULT = 3.0  # фактический slippage > ожидаемый × этот коэффициент
COOLDOWN_SEC = 60            # не повторять один тип аномалии чаще раза в минуту


class AnomalyDetector:
    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        # {symbol: deque[close]}
        self._closes: dict[str, deque] = defaultdict(lambda: deque(maxlen=FLASH_CRASH_CANDLES + 1))
        # {symbol: bool} — есть ли активный спуф
        self._spoof_active: dict[str, bool] = defaultdict(bool)
        # {symbol: float} — последний imbalance
        self._ob_imbalance: dict[str, float] = defaultdict(float)
        # {(symbol, anomaly_type): datetime} — cooldown tracking
        self._last_anomaly: dict[tuple, datetime] = {}

    async def start(self) -> None:
        self._bus.subscribe("candle.1m.closed", self._on_candle)
        self._bus.subscribe("ob.spoof_detected", self._on_spoof)
        self._bus.subscribe("ob.state_updated", self._on_ob_update)
        log.info("Anomaly Detector запущен")

    async def stop(self) -> None:
        log.info("Anomaly Detector остановлен")

    async def _on_candle(self, event: Event) -> None:
        candle = event.data
        if hasattr(candle, "symbol"):
            symbol = candle.symbol
            close = candle.close
            prev_close = candle.open
        else:
            symbol = candle.get("symbol", "")
            close = candle.get("close", 0.0)
            prev_close = candle.get("open", close)

        if not symbol or not close:
            return

        self._closes[symbol].append(close)

        # Price spike (single candle)
        if prev_close > 0:
            change_pct = (close - prev_close) / prev_close * 100
            if change_pct >= PRICE_SPIKE_PCT:
                await self._emit(symbol, "anomaly.price_spike", {
                    "symbol": symbol,
                    "change_pct": round(change_pct, 2),
                    "price": close,
                    "description": f"Рост на {change_pct:.1f}% за одну свечу",
                })

        # Flash crash (multi-candle)
        closes = list(self._closes[symbol])
        if len(closes) >= FLASH_CRASH_CANDLES:
            oldest = closes[-FLASH_CRASH_CANDLES]
            newest = closes[-1]
            if oldest > 0:
                drop_pct = (oldest - newest) / oldest * 100
                if drop_pct >= FLASH_CRASH_PCT:
                    await self._emit(symbol, "anomaly.flash_crash", {
                        "symbol": symbol,
                        "drop_pct": round(drop_pct, 2),
                        "from_price": oldest,
                        "to_price": newest,
                        "candles": FLASH_CRASH_CANDLES,
                        "description": f"Flash crash: -{drop_pct:.1f}% за {FLASH_CRASH_CANDLES} свечей",
                    })

    async def _on_spoof(self, event: Event) -> None:
        symbol = event.data.get("symbol", "")
        if not symbol:
            return
        self._spoof_active[symbol] = True
        await self._check_ob_manip(symbol)

    async def _on_ob_update(self, event: Event) -> None:
        data = event.data
        symbol = data.get("symbol", "")
        imbalance = data.get("imbalance", 0.0)
        if not symbol:
            return
        self._ob_imbalance[symbol] = imbalance
        # Reset spoof flag after OB normalises
        if abs(imbalance) < 0.1:
            self._spoof_active[symbol] = False

    async def _check_ob_manip(self, symbol: str) -> None:
        imbalance = self._ob_imbalance.get(symbol, 0.0)
        if self._spoof_active[symbol] and abs(imbalance) >= OB_MANIP_IMBALANCE:
            await self._emit(symbol, "anomaly.ob_manip", {
                "symbol": symbol,
                "imbalance": round(imbalance, 3),
                "description": f"OB манипуляция: spoof + imbalance={imbalance:.2f}",
            })

    async def report_slippage(self, symbol: str, expected_pct: float, actual_pct: float) -> None:
        """Вызывается Execution Engine после исполнения ордера."""
        if expected_pct > 0 and actual_pct > expected_pct * SLIPPAGE_ANOMALY_MULT:
            await self._emit(symbol, "anomaly.slippage", {
                "symbol": symbol,
                "expected_pct": round(expected_pct, 4),
                "actual_pct": round(actual_pct, 4),
                "multiplier": round(actual_pct / expected_pct, 2),
                "description": f"Slippage {actual_pct:.3f}% вместо {expected_pct:.3f}%",
            })

    async def _emit(self, symbol: str, event_type: str, data: dict) -> None:
        """Публикует аномалию с cooldown-защитой от спама."""
        key = (symbol, event_type)
        now = datetime.now(timezone.utc)
        last = self._last_anomaly.get(key)
        if last and (now - last).total_seconds() < COOLDOWN_SEC:
            return
        self._last_anomaly[key] = now
        log.warning(f"Аномалия [{event_type}]: {data.get('description', '')}")
        await self._bus.publish(event_type, data)
