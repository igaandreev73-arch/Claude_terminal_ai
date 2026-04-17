from collections import defaultdict

from core.event_bus import Event, EventBus
from core.logger import get_logger
from data.validator import Candle

log = get_logger("TFAggregator")

# Количество 1m-свечей для каждого таймфрейма
TF_MINUTES: dict[str, int] = {
    "3m":  3,
    "5m":  5,
    "15m": 15,
    "30m": 30,
    "1h":  60,
    "2h":  120,
    "4h":  240,
    "6h":  360,
    "12h": 720,
    "1d":  1440,
}


def _aggregate(candles: list[Candle], tf: str) -> Candle:
    """Агрегирует список 1m-свечей в одну свечу таймфрейма tf."""
    return Candle(
        symbol=candles[0].symbol,
        timeframe=tf,
        open_time=candles[0].open_time,
        open=candles[0].open,
        high=max(c.high for c in candles),
        low=min(c.low for c in candles),
        close=candles[-1].close,
        volume=sum(c.volume for c in candles),
        is_closed=True,
        source="aggregated",
    )


class TFAggregator:
    """
    Подписывается на candle.1m.closed.
    Для каждого символа накапливает 1m-свечи.
    Когда набирается нужное количество — агрегирует и публикует candle.{tf}.closed.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        # {symbol: [Candle, ...]} — буфер 1m-свечей
        self._buffer: dict[str, list[Candle]] = defaultdict(list)

    async def start(self) -> None:
        self._bus.subscribe("candle.1m.closed", self._on_1m_closed)
        log.info("TF Aggregator запущен, подписан на candle.1m.closed")

    async def stop(self) -> None:
        log.info("TF Aggregator остановлен")

    async def _on_1m_closed(self, event: Event) -> None:
        candle: Candle = event.data
        symbol = candle.symbol
        buf = self._buffer[symbol]
        buf.append(candle)

        # Проверяем какие таймфреймы завершились
        for tf, minutes in TF_MINUTES.items():
            if len(buf) >= minutes:
                # Берём последние N свечей для агрегации
                window = buf[-minutes:]
                # Проверяем что окно выравнено по границе таймфрейма
                first_open_time_min = window[0].open_time // 60_000
                if first_open_time_min % minutes == 0:
                    aggregated = _aggregate(window, tf)
                    await self._bus.publish(f"candle.{tf}.closed", aggregated)
                    log.debug(f"Агрегирована свеча {symbol} {tf}: close={aggregated.close}")

        # Обрезаем буфер — оставляем не больше чем нужно для самого большого ТФ
        max_minutes = max(TF_MINUTES.values())
        if len(buf) > max_minutes:
            self._buffer[symbol] = buf[-max_minutes:]
