"""Точка входа — два режима: collector (VPS) и terminal (Desktop).

collector:
  - Data Layer: BingX WS, REST, TF Aggregator, OB Processor, Watchdog, Basis, Data Verifier
  - Telemetry API (FastAPI :8800) — интерфейс для Desktop

terminal:
  - VPS Client — получает данные с VPS через WS + REST
  - Analytics: TA, SMC, Volume, Correlation, MTF
  - Signals: Signal Engine, Anomaly Detector
  - Execution: Risk Guard, BingX Private API, Execution Engine
  - Backtester, UI
"""
import asyncio
import signal

from dotenv import load_dotenv
load_dotenv()

from core.config import get_config
from core.event_bus import Event, EventBus
from core.health_monitor import HealthMonitor
from core.logger import get_logger, setup_logger
from storage.database import close_db, init_db
from storage.repositories.candles_repo import CandlesRepository
from storage.repositories.orderbook_repo import OrderBookRepository

log = get_logger("Main")


# ── COLLECTOR MODE ──────────────────────────────────────────────────────────

async def _run_collector() -> None:
    """Запуск в режиме COLLECTOR (VPS)."""
    from data.basis_calculator import BasisCalculator
    from data.bingx_futures_ws import BingXFuturesWebSocket
    from data.bingx_rest import BingXRestClient
    from data.bingx_ws import BingXWebSocket
    from data.data_verifier import DataVerifier
    from data.ob_processor import OBProcessor
    from data.rate_limit_guard import RateLimitGuard
    from data.tf_aggregator import TFAggregator
    from data.watchdog import Watchdog
    from data.backfill import run_backfill, repair_integrity, refresh_recent
    from telemetry.server import app as telemetry_app, set_event_bus, _broadcast_loop
    import uvicorn

    config = get_config()
    symbols = config.SYMBOLS
    log.info(f"═══ COLLECTOR MODE (VPS) ═══")
    log.info(f"Symbols: {symbols}")

    # Инициализация
    await init_db()
    event_bus = EventBus()
    health_monitor = HealthMonitor(event_bus)
    candles_repo = CandlesRepository()

    # Data Layer
    rate_guard = RateLimitGuard()
    rest_client = BingXRestClient(event_bus, rate_guard)
    ws_client = BingXWebSocket(event_bus, symbols)
    futures_ws = BingXFuturesWebSocket(event_bus, symbols)
    tf_aggregator = TFAggregator(event_bus)
    ob_processor = OBProcessor(event_bus)
    watchdog = Watchdog(event_bus, rest_client)
    basis_calculator = BasisCalculator(event_bus)
    data_verifier = DataVerifier(event_bus)
    ob_repo = OrderBookRepository()

    # Подписки
    async def _on_candle_closed(event: Event, repo: CandlesRepository) -> None:
        """Сохраняет закрытую свечу в БД."""
        try:
            await repo.upsert(event.data)
        except Exception as e:
            log.error(f"Ошибка записи свечи в БД: {e}")

    # Свечи spot в БД
    all_candle_events = ["candle.1m.tick", "candle.1m.closed"] + [
        f"candle.{tf}.closed" for tf in
        ["3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]
    ]
    for event_type in all_candle_events:
        event_bus.subscribe(event_type, lambda e, r=candles_repo: _on_candle_closed(e, r))

    # Futures свечи в БД
    futures_candle_events = ["futures.candle.1m.closed"] + [
        f"futures.candle.{tf}.closed" for tf in ["3m", "5m", "15m", "30m", "1h", "4h", "1d"]
    ]
    for event_type in futures_candle_events:
        event_bus.subscribe(event_type, lambda e, r=candles_repo: _on_candle_closed(e, r))

    # Снимки стакана в БД
    event_bus.subscribe("ob.snapshot", lambda e: ob_repo.save_from_event(e.data))

    # Ликвидации в БД
    async def _on_liquidation(event):
        import time as _t
        from storage.database import get_session_factory
        from storage.models import LiquidationModel
        from sqlalchemy.dialects.sqlite import insert as si
        try:
            d = event.data
            factory = get_session_factory()
            async with factory() as session:
                stmt = si(LiquidationModel).values(
                    symbol=d.get("symbol", ""),
                    timestamp=d.get("timestamp", int(_t.time() * 1000)),
                    side=d.get("side", "unknown"),
                    price=float(d.get("price", 0)),
                    quantity=float(d.get("quantity", 0)),
                    value_usd=d.get("value_usd"),
                    liq_type=d.get("liq_type", "forced"),
                    market_type="futures",
                ).on_conflict_do_nothing()
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            log.error(f"Ошибка записи ликвидации: {exc}")

    event_bus.subscribe("futures.liquidation", _on_liquidation)

    # Watchdog: регистрируем оба WS-соединения
    watchdog.register(
        "spot_ws", market_type="spot", is_critical=False,
        reconnect_fn=lambda: ws_client.start(),
    )
    watchdog.register(
        "futures_ws", market_type="futures", is_critical=True,
        reconnect_fn=lambda: futures_ws.start(),
    )

    # Telemetry API (Event Bus в WS Desktop)
    set_event_bus(event_bus)
    asyncio.create_task(_broadcast_loop())

    # Старт модулей
    await event_bus.start()
    await health_monitor.start()
    await rest_client.start()
    await tf_aggregator.start()
    await ob_processor.start()
    await ws_client.start()
    await futures_ws.start()
    await basis_calculator.start()
    asyncio.create_task(watchdog.start())

    # Проверка целостности, обновление, бэкфилл (в фоне)
    async def _startup_data():
        await repair_integrity(symbols, candles_repo)
        await refresh_recent(symbols, rest_client, candles_repo)
        await run_backfill(symbols, rest_client, candles_repo)

    asyncio.create_task(_startup_data())

    # Запуск FastAPI (uvicorn)
    log.info(f"Starting Telemetry API on {config.VPS_HOST}:{config.VPS_PORT}")
    telemetry_config = uvicorn.Config(
        telemetry_app,
        host=config.VPS_HOST,
        port=config.VPS_PORT,
        log_level=config.LOG_LEVEL.lower(),
    )
    telemetry_server = uvicorn.Server(telemetry_config)
    asyncio.create_task(telemetry_server.serve())

    log.info("Collector запущен. Нажмите Ctrl+C для остановки.")

    # Ожидание сигнала остановки
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
    await watchdog.stop()
    await futures_ws.stop()
    await basis_calculator.stop()
    await ws_client.stop()
    await ob_processor.stop()
    await rest_client.stop()
    await health_monitor.stop()
    await event_bus.stop()
    await close_db()
    log.info("═══ Collector остановлен ═══")


# ── TERMINAL MODE ───────────────────────────────────────────────────────────

async def _run_terminal() -> None:
    """Запуск в режиме TERMINAL (Desktop)."""
    from analytics.correlation import CorrelationEngine
    from analytics.mtf_confluence import MTFConfluenceEngine
    from analytics.smartmoney import SmartMoneyEngine
    from analytics.ta_engine import TAEngine
    from analytics.volume_engine import VolumeEngine
    from data.vps_client import VPSClient
    from execution.bingx_private import BingXPrivateClient
    from execution.execution_engine import ExecutionEngine
    from execution.risk_guard import RiskConfig, RiskGuard
    from signals.anomaly_detector import AnomalyDetector
    from signals.signal_engine import SignalEngine
    from ui.ws_server import WSServer

    config = get_config()
    symbols = config.SYMBOLS
    log.info(f"═══ TERMINAL MODE (Desktop) ═══")
    log.info(f"Symbols: {symbols}")
    log.info(f"VPS: {config.VPS_HOST}:{config.VPS_PORT}")

    # Инициализация
    await init_db()
    event_bus = EventBus()
    health_monitor = HealthMonitor(event_bus)
    candles_repo = CandlesRepository()

    # VPS Client (вместо прямых BingX-подключений)
    vps_client = VPSClient(event_bus)

    # Analytics Core
    ta_engine = TAEngine(event_bus)
    smc_engine = SmartMoneyEngine(event_bus)
    volume_engine = VolumeEngine(event_bus)
    mtf_engine = MTFConfluenceEngine(event_bus)
    correlation_engine = CorrelationEngine(event_bus, symbols)

    # Signals
    signal_engine = SignalEngine(event_bus)
    anomaly_detector = AnomalyDetector(event_bus)

    # Execution
    risk_guard = RiskGuard(RiskConfig())
    api_client = BingXPrivateClient(
        api_key=config.BINGX_API_KEY,
        api_secret=config.BINGX_API_SECRET,
        dry_run=not config.is_live,
    )
    execution_engine = ExecutionEngine(
        event_bus, risk_guard, api_client,
        initial_capital=config.INITIAL_CAPITAL,
    )

    # UI WebSocket (локальный, для React)
    ws_server = WSServer(
        event_bus, signal_engine, execution_engine,
        rest_client=None,
        candles_repo=candles_repo,
        watchdog=None,
        basis_calculator=None,
        data_verifier=None,
        ws_client=None,
        futures_ws=None,
        host=config.WS_HOST,
        port=config.WS_PORT,
    )

    # Подписки на свечи в БД (данные приходят через VPS Client)
    async def _on_candle_closed(event: Event, repo: CandlesRepository) -> None:
        try:
            await repo.upsert(event.data)
        except Exception as e:
            log.error(f"Ошибка записи свечи в БД: {e}")

    all_candle_events = ["candle.1m.tick", "candle.1m.closed"] + [
        f"candle.{tf}.closed" for tf in
        ["3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]
    ]
    for event_type in all_candle_events:
        event_bus.subscribe(event_type, lambda e, r=candles_repo: _on_candle_closed(e, r))

    futures_candle_events = ["futures.candle.1m.closed"] + [
        f"futures.candle.{tf}.closed" for tf in ["3m", "5m", "15m", "30m", "1h", "4h", "1d"]
    ]
    for event_type in futures_candle_events:
        event_bus.subscribe(event_type, lambda e, r=candles_repo: _on_candle_closed(e, r))

    # Ликвидации — только логирование (полная история на VPS)
    async def _on_liquidation(event):
        d = event.data
        value = d.get("value_usd")
        value_str = f" ${value:.0f}" if value else ""
        log.info(f"Ликвидация {d.get('symbol')} {d.get('side')}{value_str}")

    event_bus.subscribe("futures.liquidation", _on_liquidation)

    # Старт
    await event_bus.start()
    await health_monitor.start()
    await vps_client.start()
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

    log.info("Терминал запущен. Нажмите Ctrl+C для остановки.")

    # Ожидание сигнала остановки
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
    await ws_server.stop()
    await execution_engine.stop()
    await anomaly_detector.stop()
    await signal_engine.stop()
    await correlation_engine.stop()
    await mtf_engine.stop()
    await volume_engine.stop()
    await smc_engine.stop()
    await ta_engine.stop()
    await vps_client.stop()
    await health_monitor.stop()
    await event_bus.stop()
    await close_db()
    log.info("═══ Терминал остановлен ═══")


# ── Точка входа ─────────────────────────────────────────────────────────────

async def main() -> None:
    setup_logger()
    config = get_config()
    log.info(f"RUN_MODE={config.RUN_MODE}")

    if config.is_collector:
        await _run_collector()
    elif config.is_terminal:
        await _run_terminal()
    else:
        log.error(f"Неизвестный RUN_MODE: {config.RUN_MODE}")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
