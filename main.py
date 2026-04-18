import asyncio
import signal

from dotenv import load_dotenv
load_dotenv()

from core.event_bus import Event, EventBus
from core.health_monitor import HealthMonitor
from core.logger import get_logger, setup_logger
import os

from analytics.correlation import CorrelationEngine
from analytics.mtf_confluence import MTFConfluenceEngine
from analytics.smartmoney import SmartMoneyEngine
from analytics.ta_engine import TAEngine
from analytics.volume_engine import VolumeEngine
from data.bingx_rest import BingXRestClient
from data.bingx_ws import BingXWebSocket
from data.ob_processor import OBProcessor
from data.rate_limit_guard import RateLimitGuard
from data.tf_aggregator import TFAggregator
from execution.bingx_private import BingXPrivateClient
from execution.execution_engine import ExecutionEngine, ExecutionMode
from execution.risk_guard import RiskConfig, RiskGuard
from signals.anomaly_detector import AnomalyDetector
from signals.signal_engine import SignalEngine
from storage.database import close_db, init_db
from ui.ws_server import WSServer
from storage.repositories.candles_repo import CandlesRepository
from storage.repositories.orderbook_repo import OrderBookRepository
from data.backfill import run_backfill

log = get_logger("Main")

# Торговые пары — настраиваются через .env (SYMBOLS=BTC/USDT,ETH/USDT,...)
DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]


def _get_symbols() -> list[str]:
    raw = os.getenv("SYMBOLS", "")
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    return DEFAULT_SYMBOLS


async def _on_candle_closed(event: Event, repo: CandlesRepository) -> None:
    """Сохраняет закрытую свечу (любой таймфрейм) в БД."""
    try:
        await repo.upsert(event.data)
    except Exception as e:
        log.error(f"Ошибка записи свечи в БД: {e}")


async def main() -> None:
    setup_logger()
    log.info("═══ Запуск криптовалютного терминала ═══")

    # --- Инициализация БД ---
    await init_db()

    symbols = _get_symbols()
    log.info(f"Торговые пары: {symbols}")

    # --- Ядро системы ---
    event_bus = EventBus()
    health_monitor = HealthMonitor(event_bus)
    candles_repo = CandlesRepository()

    # --- Data layer ---
    rate_guard = RateLimitGuard()
    rest_client = BingXRestClient(event_bus, rate_guard)
    ws_client = BingXWebSocket(event_bus, symbols)
    tf_aggregator = TFAggregator(event_bus)
    ob_processor = OBProcessor(event_bus)
    ob_repo = OrderBookRepository()
    ta_engine = TAEngine(event_bus)
    smc_engine = SmartMoneyEngine(event_bus)
    volume_engine = VolumeEngine(event_bus)
    mtf_engine = MTFConfluenceEngine(event_bus)
    correlation_engine = CorrelationEngine(event_bus, symbols)
    signal_engine = SignalEngine(event_bus)
    anomaly_detector = AnomalyDetector(event_bus)
    risk_guard = RiskGuard(RiskConfig())
    api_client = BingXPrivateClient(
        api_key=os.getenv("BINGX_API_KEY", ""),
        api_secret=os.getenv("BINGX_API_SECRET", ""),
        dry_run=os.getenv("TRADING_MODE", "paper") != "live",
    )
    execution_engine = ExecutionEngine(
        event_bus, risk_guard, api_client,
        initial_capital=float(os.getenv("INITIAL_CAPITAL", "10000")),
    )
    ws_server = WSServer(
        event_bus, signal_engine, execution_engine,
        rest_client=rest_client,
        candles_repo=candles_repo,
        host=os.getenv("WS_HOST", "localhost"),
        port=int(os.getenv("WS_PORT", "8765")),
    )

    # Снимки стакана → БД
    event_bus.subscribe("ob.snapshot", lambda e: ob_repo.save_from_event(e.data))

    # --- Подписка: тики и закрытые свечи → БД (upsert, is_closed=True перезапишет тик) ---
    all_candle_events = ["candle.1m.tick", "candle.1m.closed"] + [f"candle.{tf}.closed" for tf in
                         ["3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]]
    for event_type in all_candle_events:
        event_bus.subscribe(event_type, lambda e, r=candles_repo: _on_candle_closed(e, r))

    # --- Старт ---
    await event_bus.start()
    await health_monitor.start()
    await rest_client.start()
    await tf_aggregator.start()
    await ob_processor.start()
    await ta_engine.start()
    await smc_engine.start()
    await volume_engine.start()
    await mtf_engine.start()
    mtf_engine.subscribe_ta_for_symbols(symbols)
    await correlation_engine.start()
    await signal_engine.start()
    await anomaly_detector.start()
    await execution_engine.start()
    await ws_server.start()
    await ws_client.start()

    # Загрузка исторических свечей в фоне (не блокирует старт)
    asyncio.create_task(run_backfill(symbols, rest_client, candles_repo))

    log.info("Система запущена. Нажмите Ctrl+C для остановки.")

    stop_event = asyncio.Event()

    def _on_signal(*_):
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            signal.signal(sig, _on_signal)

    await stop_event.wait()

    log.info("Получен сигнал остановки...")
    await ws_client.stop()
    await ws_server.stop()
    await execution_engine.stop()
    await anomaly_detector.stop()
    await signal_engine.stop()
    await correlation_engine.stop()
    await mtf_engine.stop()
    await volume_engine.stop()
    await smc_engine.stop()
    await ta_engine.stop()
    await ob_processor.stop()
    await rest_client.stop()
    await health_monitor.stop()
    await event_bus.stop()
    await close_db()
    log.info("═══ Терминал остановлен ═══")


if __name__ == "__main__":
    asyncio.run(main())
