"""
WebSocket Server — мост между Python бэкендом и React фронтендом.

Протокол (JSON):
  Server → Client:
    {"type": "event",  "event_type": str, "data": any, "ts": iso}
    {"type": "state",  "positions": [...], "signals": [...], "health": {...}}
    {"type": "pong"}

  Client → Server:
    {"type": "ping"}
    {"type": "command", "command": str, "payload": {}}

Команды от клиента:
  confirm_signal  — подтвердить сигнал (semi-auto)
  reject_signal   — отклонить сигнал
  close_position  — закрыть позицию
  set_mode        — изменить режим исполнения
  get_state       — запросить текущее состояние системы
  start_backfill  — запустить ручной бэкфилл
  stop_task       — мягко остановить задачу (пауза с checkpoint)
  resume_task     — возобновить приостановленную задачу
  get_tasks       — получить список активных + завершённых задач
  run_validation  — запустить проверку данных

Публикует: нет (только проксирует события шины)
"""
from __future__ import annotations

import asyncio
import json
import time
import weakref
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web_ws import WebSocketResponse

from core.event_bus import Event, EventBus
from core.logger import get_logger
from storage.repositories.tasks_repo import TasksRepository

if TYPE_CHECKING:
    from execution.execution_engine import ExecutionEngine
    from signals.signal_engine import SignalEngine
    from data.bingx_rest import BingXRestClient
    from storage.repositories.candles_repo import CandlesRepository

log = get_logger("WSServer")

# События которые транслируются во фронтенд
BROADCAST_EVENTS = {
    "candle.1m.closed",
    "ta.*",
    "smc.bos.detected", "smc.choch.detected", "smc.fvg.detected",
    "volume.cvd.updated",
    "ob.state_updated", "ob.spoof_detected",
    "mtf.score.updated",
    "correlation.updated", "correlation.divergence",
    "signal.generated", "signal.expired", "signal.executed",
    "anomaly.flash_crash", "anomaly.price_spike", "anomaly.ob_manip", "anomaly.slippage",
    "execution.signal_received", "execution.position_opened", "execution.position_closed",
    "execution.pending", "execution.confirmed", "execution.rejected", "execution.blocked",
    "demo.trade.opened", "demo.trade.closed", "demo.stats.updated",
    "backfill.progress", "backfill.complete", "backfill.error",
    "validation.result",
    "backtest.started", "backtest.progress", "backtest.completed", "backtest.error",
    "optimizer.started", "optimizer.completed", "optimizer.error",
    "watchdog.degraded", "watchdog.lost", "watchdog.dead", "watchdog.recovered", "watchdog.reconnecting",
    "futures.candle.1m.closed", "futures.orderbook.update", "futures.liquidation", "futures.basis.updated",
    "HEALTH_UPDATE",
}


class WSServer:
    def __init__(
        self,
        event_bus: EventBus,
        signal_engine: "SignalEngine",
        execution_engine: "ExecutionEngine",
        rest_client: "BingXRestClient | None" = None,
        candles_repo: "CandlesRepository | None" = None,
        watchdog=None,
        basis_calculator=None,
        data_verifier=None,
        host: str = "localhost",
        port: int = 8765,
    ) -> None:
        self._bus = event_bus
        self._signal_engine = signal_engine
        self._execution_engine = execution_engine
        self._rest_client = rest_client
        self._candles_repo = candles_repo
        self._watchdog = watchdog
        self._basis_calculator = basis_calculator
        self._data_verifier = data_verifier
        self._host = host
        self._port = port
        self._clients: weakref.WeakSet[WebSocketResponse] = weakref.WeakSet()
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        # task_id → {symbol, period, percent, fetched, total, status, stop_flag, start_time, candles_fetched}
        self._active_backfills: dict[str, dict] = {}
        self._tasks_repo = TasksRepository()

    async def start(self) -> None:
        # Подписываемся на все события шины
        for event_type in BROADCAST_EVENTS:
            self._bus.subscribe(event_type, self._on_event)

        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/health", self._health_handler)
        self._app.router.add_get("/api/candles", self._candles_http_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        log.info(f"WebSocket сервер запущен: ws://{self._host}:{self._port}/ws")

    async def stop(self) -> None:
        for ws in list(self._clients):
            await ws.close()
        if self._runner:
            await self._runner.cleanup()
        log.info("WebSocket сервер остановлен")

    # ── HTTP handlers ─────────────────────────────────────────────────────────

    async def _health_handler(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "clients": len(list(self._clients))})

    async def _candles_http_handler(self, request: web.Request) -> web.Response:
        symbol = request.rel_url.query.get("symbol", "BTC/USDT")
        tf     = request.rel_url.query.get("tf", "1m")
        limit  = int(request.rel_url.query.get("limit", "500"))
        from storage.repositories.candles_repo import CandlesRepository
        repo = CandlesRepository()
        try:
            candles = await repo.get_latest(symbol, tf, limit)
            data = [
                {"time": c.open_time // 1000, "open": c.open,
                 "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                for c in candles
            ]
        except Exception as e:
            log.error(f"REST /api/candles ошибка: {e}")
            data = []
        headers = {"Access-Control-Allow-Origin": "*"}
        return web.json_response({"candles": data, "symbol": symbol, "tf": tf}, headers=headers)

    async def _ws_handler(self, request: web.Request) -> WebSocketResponse:
        ws = WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._clients.add(ws)
        log.info(f"WS клиент подключился. Всего: {len(list(self._clients))}")

        try:
            await self._send_state(ws)

            async for msg in ws:
                from aiohttp import WSMsgType
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_command(ws, data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            self._clients.discard(ws)
            log.info(f"WS клиент отключился. Осталось: {len(list(self._clients))}")

        return ws

    # ── Command handling ──────────────────────────────────────────────────────

    async def _handle_command(self, ws: WebSocketResponse, msg: dict) -> None:
        msg_type = msg.get("type")
        command = msg.get("command", "")
        payload = msg.get("payload", {})

        if msg_type == "ping":
            await self._send(ws, {"type": "pong"})
            return

        if msg_type != "command":
            return

        if command == "confirm_signal":
            await self._execution_engine.confirm(payload.get("signal_id", ""))

        elif command == "reject_signal":
            await self._execution_engine.reject(payload.get("signal_id", ""))

        elif command == "close_position":
            await self._execution_engine.close_position(
                payload.get("symbol", ""), reason="user_ui"
            )

        elif command == "set_mode":
            from execution.execution_engine import ExecutionMode
            try:
                mode = ExecutionMode(payload.get("mode", "alert_only"))
                self._execution_engine.set_mode(mode)
                await self._send(ws, {"type": "mode_changed", "mode": mode.value})
            except ValueError:
                pass

        elif command == "get_state":
            await self._send_state(ws)

        elif command == "start_backfill":
            await self._handle_start_backfill(ws, payload)

        elif command == "stop_task":
            await self._handle_stop_task(ws, payload)

        elif command == "resume_task":
            await self._handle_resume_task(ws, payload)

        elif command == "get_tasks":
            await self._handle_get_tasks(ws)

        elif command == "run_validation":
            await self._handle_run_validation(ws, payload)

        elif command == "get_db_stats":
            await self._send_db_stats(ws)

        elif command == "get_candles":
            symbol = payload.get("symbol", "BTC/USDT")
            tf     = payload.get("tf", "1m")
            limit  = int(payload.get("limit", 500))
            await self._send_candles(ws, symbol, tf, limit)

        elif command == "run_backtest":
            await self._handle_run_backtest(ws, payload)

        elif command == "run_optimizer":
            await self._handle_run_optimizer(ws, payload)

        elif command == "get_backtest_results":
            await self._handle_get_backtest_results(ws, payload)

        elif command == "get_pulse_state":
            await self._handle_get_pulse_state(ws)

    async def _handle_start_backfill(self, ws: WebSocketResponse, payload: dict) -> None:
        from data.backfill import run_manual_backfill
        symbol  = payload.get("symbol", "BTC/USDT")
        period  = payload.get("period", "1w")
        task_id = payload.get("task_id", f"{symbol}-{period}")

        if task_id in self._active_backfills:
            await self._send(ws, {"type": "backfill_rejected", "task_id": task_id, "reason": "already_running"})
            return
        if not self._rest_client or not self._candles_repo:
            await self._send(ws, {"type": "backfill_rejected", "task_id": task_id, "reason": "not_configured"})
            return

        stop_flag: list[bool] = [False]
        now_ts = int(time.time())

        self._active_backfills[task_id] = {
            "task_id": task_id, "symbol": symbol, "period": period,
            "percent": 0, "fetched": 0, "total": 0, "status": "running",
            "stop_flag": stop_flag,
            "start_time": time.time(),
            "candles_fetched": 0,
            "speed_cps": 0.0,
            "eta_seconds": None,
        }

        # Сохраняем задачу в БД
        await self._tasks_repo.upsert({
            "task_id": task_id, "type": "backfill",
            "symbol": symbol, "period": period,
            "status": "running", "percent": 0,
            "fetched": 0, "total_pages": 0, "total_saved": 0,
            "created_at": now_ts,
        })

        # Обновляем кэш прогресса при каждом backfill.progress событии
        async def _on_progress(event):
            d = event.data
            if d.get("task_id") == task_id:
                info = self._active_backfills.get(task_id)
                if info:
                    info.update({k: d[k] for k in ("percent", "fetched", "total", "status") if k in d})
                    # Вычисляем скорость
                    elapsed = time.time() - info["start_time"]
                    total_fetched = d.get("total_saved", 0) or d.get("fetched", 0) * 1440
                    if elapsed > 0 and total_fetched > 0:
                        speed = total_fetched / elapsed
                        info["speed_cps"] = round(speed, 1)
                        pct = d.get("percent", 0)
                        if pct > 0 and pct < 100:
                            remaining_pct = 95 - pct if pct < 95 else 0
                            eta = (remaining_pct / pct) * elapsed if pct > 0 else None
                            info["eta_seconds"] = round(eta) if eta else None

        self._bus.subscribe("backfill.progress", _on_progress)

        async def _run():
            try:
                await run_manual_backfill(
                    symbol, period,
                    self._rest_client, self._candles_repo, self._bus, task_id,
                    stop_flag=stop_flag,
                )
            except asyncio.CancelledError:
                pass
            finally:
                self._active_backfills.pop(task_id, None)

        asyncio.create_task(_run())
        log.info(f"Запущен ручной бэкфилл: {symbol} {period} [{task_id}]")

    async def _handle_stop_task(self, ws: WebSocketResponse, payload: dict) -> None:
        task_id = payload.get("task_id", "")
        info = self._active_backfills.get(task_id)
        if not info:
            await self._send(ws, {"type": "error", "message": f"Задача {task_id} не найдена"})
            return

        # Устанавливаем флаг остановки
        stop_flag = info.get("stop_flag")
        if stop_flag is not None:
            stop_flag[0] = True

        log.info(f"Запрос на остановку задачи {task_id}")

    async def _handle_resume_task(self, ws: WebSocketResponse, payload: dict) -> None:
        from data.backfill import run_manual_backfill
        task_id = payload.get("task_id", "")

        # Загружаем из БД
        task = await self._tasks_repo.get(task_id)
        if not task or task["status"] != "paused":
            await self._send(ws, {"type": "error", "message": f"Задача {task_id} не найдена или не приостановлена"})
            return

        if not self._rest_client or not self._candles_repo:
            await self._send(ws, {"type": "error", "message": "REST клиент не настроен"})
            return

        symbol   = task["symbol"]
        period   = task["period"]
        resume_end_ms = task.get("checkpoint_end_ms")

        # Создаём новый task_id для возобновлённой задачи (или используем тот же)
        new_task_id = task_id
        stop_flag: list[bool] = [False]

        self._active_backfills[new_task_id] = {
            "task_id": new_task_id, "symbol": symbol, "period": period,
            "percent": task.get("percent", 0),
            "fetched": task.get("fetched", 0),
            "total": task.get("total_pages", 0),
            "status": "running",
            "stop_flag": stop_flag,
            "start_time": time.time(),
            "candles_fetched": 0,
            "speed_cps": 0.0,
            "eta_seconds": None,
        }

        await self._tasks_repo.mark_status(new_task_id, "running")

        async def _run():
            try:
                await run_manual_backfill(
                    symbol, period,
                    self._rest_client, self._candles_repo, self._bus, new_task_id,
                    stop_flag=stop_flag,
                    resume_end_ms=resume_end_ms,
                )
            except asyncio.CancelledError:
                pass
            finally:
                self._active_backfills.pop(new_task_id, None)

        asyncio.create_task(_run())
        log.info(f"Возобновлён бэкфилл: {symbol} {period} [{new_task_id}] от end_ms={resume_end_ms}")

    async def _handle_get_tasks(self, ws: WebSocketResponse) -> None:
        running = list(self._active_backfills.values())
        # Убираем непереносимые объекты (stop_flag) перед отправкой
        running_clean = [
            {k: v for k, v in t.items() if k != "stop_flag"}
            for t in running
        ]
        recent = await self._tasks_repo.get_recent(limit=20)
        paused = await self._tasks_repo.get_paused()
        await self._send(ws, {
            "type": "tasks_list",
            "running": running_clean,
            "paused": paused,
            "recent": recent,
        })

    # ── Backtest / Optimizer ──────────────────────────────────────────────────

    def _strategy_registry(self) -> dict:
        from strategies.simple_ma_strategy import SimpleMAStrategy
        from strategies.mtf_confluence_strategy import MTFConfluenceStrategy
        return {
            "ma-crossover":    SimpleMAStrategy,
            "mtf-confluence":  MTFConfluenceStrategy,
        }

    async def _handle_run_backtest(self, ws: WebSocketResponse, payload: dict) -> None:
        strategy_id = payload.get("strategy_id", "")
        symbol      = payload.get("symbol", "BTC/USDT")
        timeframe   = payload.get("timeframe", "1h")
        params      = payload.get("params", {})

        registry = self._strategy_registry()
        if strategy_id not in registry:
            await self._broadcast_event("backtest.error", {
                "strategy_id": strategy_id,
                "error": f"Стратегия '{strategy_id}' не поддерживает бэктест",
            })
            return
        if not self._candles_repo:
            await self._broadcast_event("backtest.error", {
                "strategy_id": strategy_id, "error": "Репозиторий свечей недоступен",
            })
            return

        run_id = f"bt-{strategy_id}-{symbol.replace('/', '')}-{int(time.time())}"
        await self._broadcast_event("backtest.started", {
            "run_id": run_id, "strategy_id": strategy_id,
            "symbol": symbol, "timeframe": timeframe,
        })
        asyncio.create_task(
            self._run_backtest_task(run_id, strategy_id, symbol, timeframe, params, registry)
        )

    async def _run_backtest_task(
        self, run_id: str, strategy_id: str, symbol: str, timeframe: str,
        params: dict, registry: dict,
    ) -> None:
        try:
            candles = await self._candles_repo.get_latest(symbol, timeframe, limit=500_000)
            if not candles:
                await self._broadcast_event("backtest.error", {
                    "run_id": run_id, "strategy_id": strategy_id,
                    "error": f"Нет данных для {symbol}/{timeframe}",
                })
                return

            candles_data = [
                {"open_time": c.open_time, "open": c.open, "high": c.high,
                 "low": c.low, "close": c.close, "volume": c.volume}
                for c in candles
            ]

            from backtester.engine import BacktestConfig, BacktestEngine
            strategy = registry[strategy_id](params=params or {})
            engine = BacktestEngine()
            loop = asyncio.get_event_loop()

            def _progress_cb(current: int, total: int) -> None:
                pct = min(90, int(current / total * 90)) if total else 0
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_event("backtest.progress", {
                        "strategy_id": strategy_id, "run_id": run_id,
                        "percent": pct, "current": current, "total": total,
                    }),
                    loop,
                )

            result = await loop.run_in_executor(
                None,
                lambda: engine.run(
                    strategy, candles_data, BacktestConfig(), symbol, timeframe,
                    on_progress=_progress_cb,
                ),
            )

            eq = result.equity_curve
            if len(eq) > 500:
                step = len(eq) / 500
                eq = [eq[int(i * step)] for i in range(500)] + [eq[-1]]

            # Сериализуем сделки (максимум 2000)
            trades_detail = [
                {
                    "entry_time": t.entry_time,
                    "exit_time":  t.exit_time,
                    "direction":  t.direction,
                    "entry_price": t.entry_price,
                    "exit_price":  t.exit_price,
                    "size_usd":   t.size_usd,
                    "pnl":        round(t.pnl, 4),
                    "pnl_pct":    round(t.pnl_pct, 4),
                    "closed_by":  t.closed_by,
                }
                for t in result.trades[:2000]
            ]

            result_data = {
                "id": run_id,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "period_start": candles[0].open_time,
                "period_end": candles[-1].open_time,
                "params": params,
                "metrics": result.metrics,
                "equity_curve": eq,
                "trades_count": len(result.trades),
                "trades_detail": trades_detail,
                "is_optimization": False,
                "created_at": int(time.time()),
            }

            from storage.repositories.backtest_repo import BacktestRepository
            await BacktestRepository().save(result_data)
            await self._broadcast_event("backtest.completed", result_data)
            log.info(f"Бэктест {strategy_id} {symbol}/{timeframe}: {len(result.trades)} сделок")

        except Exception as e:
            log.error(f"Ошибка бэктеста {strategy_id}: {e}")
            await self._broadcast_event("backtest.error", {
                "run_id": run_id, "strategy_id": strategy_id, "error": str(e),
            })

    async def _handle_run_optimizer(self, ws: WebSocketResponse, payload: dict) -> None:
        strategy_id   = payload.get("strategy_id", "")
        symbol        = payload.get("symbol", "BTC/USDT")
        timeframe     = payload.get("timeframe", "1h")
        param_grid    = payload.get("param_grid", {})
        target_metric = payload.get("target_metric", "sharpe_ratio")
        walk_forward  = bool(payload.get("walk_forward", True))

        registry = self._strategy_registry()
        if strategy_id not in registry:
            await self._broadcast_event("optimizer.error", {
                "strategy_id": strategy_id, "error": "Стратегия не поддерживает оптимизацию",
            })
            return
        if not self._candles_repo:
            await self._broadcast_event("optimizer.error", {
                "strategy_id": strategy_id, "error": "Репозиторий свечей недоступен",
            })
            return

        run_id = f"opt-{strategy_id}-{symbol.replace('/', '')}-{int(time.time())}"
        await self._broadcast_event("optimizer.started", {
            "run_id": run_id, "strategy_id": strategy_id,
            "symbol": symbol, "timeframe": timeframe,
        })
        asyncio.create_task(
            self._run_optimizer_task(
                run_id, strategy_id, symbol, timeframe,
                param_grid, target_metric, walk_forward, registry,
            )
        )

    async def _run_optimizer_task(
        self, run_id: str, strategy_id: str, symbol: str, timeframe: str,
        param_grid: dict, target_metric: str, walk_forward: bool, registry: dict,
    ) -> None:
        try:
            candles = await self._candles_repo.get_latest(symbol, timeframe, limit=500_000)
            if not candles:
                await self._broadcast_event("optimizer.error", {
                    "run_id": run_id, "strategy_id": strategy_id,
                    "error": f"Нет данных для {symbol}/{timeframe}",
                })
                return

            candles_data = [
                {"open_time": c.open_time, "open": c.open, "high": c.high,
                 "low": c.low, "close": c.close, "volume": c.volume}
                for c in candles
            ]

            from backtester.engine import BacktestConfig
            from backtester.optimizer import GridSearchOptimizer, OptimizeConfig
            strategy_cls = registry[strategy_id]
            opt_config = OptimizeConfig(
                param_grid=param_grid,
                backtest_config=BacktestConfig(),
                target_metric=target_metric,
                walk_forward=walk_forward,
            )
            optimizer = GridSearchOptimizer()
            loop = asyncio.get_event_loop()
            opt_result = await loop.run_in_executor(
                None,
                lambda: optimizer.run(strategy_cls, candles_data, opt_config, symbol, timeframe),
            )

            top_results = [
                {"params": p, "metrics": r.metrics, "trades_count": len(r.trades)}
                for p, r in opt_result.all_results[:20]
            ]

            eq = opt_result.best_result.equity_curve
            if len(eq) > 300:
                step = len(eq) / 300
                eq = [eq[int(i * step)] for i in range(300)] + [eq[-1]]

            result_data = {
                "run_id": run_id,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "target_metric": target_metric,
                "best_params": opt_result.best_params,
                "best_metric": opt_result.best_metric,
                "best_equity_curve": eq,
                "all_results": top_results,
                "fingerprint": opt_result.fingerprint.data,
                "created_at": int(time.time()),
            }

            from storage.repositories.backtest_repo import BacktestRepository
            await BacktestRepository().save({
                "id": run_id,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "period_start": candles[0].open_time,
                "period_end": candles[-1].open_time,
                "params": opt_result.best_params,
                "metrics": opt_result.best_result.metrics,
                "equity_curve": eq,
                "trades_count": len(opt_result.best_result.trades),
                "is_optimization": True,
                "created_at": int(time.time()),
            })
            await self._broadcast_event("optimizer.completed", result_data)
            log.info(f"Оптимизация {strategy_id} {symbol}: лучшие {opt_result.best_params}")

        except Exception as e:
            log.error(f"Ошибка оптимизации {strategy_id}: {e}")
            await self._broadcast_event("optimizer.error", {
                "run_id": run_id, "strategy_id": strategy_id, "error": str(e),
            })

    async def _handle_get_backtest_results(self, ws: WebSocketResponse, payload: dict) -> None:
        strategy_id = payload.get("strategy_id", "")
        from storage.repositories.backtest_repo import BacktestRepository
        results = await BacktestRepository().list_for_strategy(strategy_id)
        await self._send(ws, {
            "type": "backtest_results",
            "strategy_id": strategy_id,
            "results": results,
        })

    async def _handle_get_pulse_state(self, ws: WebSocketResponse) -> None:
        import os
        import time as _time

        # ── Connections ───────────────────────────────────────────────────────
        now_ts = _time.time()

        # Синтетические соединения которые Watchdog не отслеживает
        ws_ui_stage = "normal" if list(self._clients) else "lost"
        rest_stage  = "normal" if self._rest_client else "stopped"
        db_stage    = "normal"  # если мы отвечаем — БД доступна
        try:
            from storage.database import get_session_factory
            get_session_factory()
        except Exception:
            db_stage = "lost"

        connections = [
            {"name": "ws_ui",        "label": "WebSocket UI",       "stage": ws_ui_stage, "last_ok_at": now_ts, "is_critical": False, "market_type": "internal"},
            {"name": "spot_rest",    "label": "REST API Спот",       "stage": rest_stage,  "last_ok_at": now_ts if rest_stage == "normal" else None, "is_critical": False, "market_type": "spot"},
            {"name": "futures_rest", "label": "REST API Фьючерсы",   "stage": "stopped",   "last_ok_at": None,    "is_critical": False, "market_type": "futures"},
            {"name": "local_db",     "label": "Локальная БД",        "stage": db_stage,    "last_ok_at": now_ts,  "is_critical": True,  "market_type": "internal"},
            {"name": "fear_greed",   "label": "Fear & Greed API",    "stage": "stopped",   "last_ok_at": None,    "is_critical": False, "market_type": "external"},
            {"name": "news_feed",    "label": "Новостной фид",       "stage": "stopped",   "last_ok_at": None,    "is_critical": False, "market_type": "external"},
        ]

        # Добавляем WS-соединения из Watchdog (spot_ws, futures_ws)
        if self._watchdog:
            watchdog_conns = []
            for s in self._watchdog.get_all_statuses():
                labels = {"spot_ws": "WS Спот BingX", "futures_ws": "WS Фьючерсы BingX"}
                watchdog_conns.append({
                    "name":        s["name"],
                    "label":       labels.get(s["name"], s["name"].replace("_", " ").title()),
                    "stage":       s["stage"],
                    "last_ok_at":  s.get("last_message_at"),
                    "is_critical": s.get("is_critical", False),
                    "market_type": s.get("market_type", "spot"),
                    "silence_sec": s.get("silence_sec"),
                })
            # Вставляем WS-соединения после ws_ui (позиция 1)
            connections = connections[:1] + watchdog_conns + connections[1:]

        # ── Modules (fixed list, status ok unless watchdog says otherwise) ────
        modules = [
            {"name": "event_bus",      "label": "Event Bus",        "status": "ok", "last_action_at": int(_time.time()), "events_per_min": 0, "latency_ms": None},
            {"name": "spot_ws",        "label": "Spot WebSocket",   "status": "ok", "last_action_at": int(_time.time()), "events_per_min": 0, "latency_ms": None},
            {"name": "futures_ws",     "label": "Futures WebSocket","status": "ok", "last_action_at": int(_time.time()), "events_per_min": 0, "latency_ms": None},
            {"name": "ta_engine",      "label": "TA Engine",        "status": "ok", "last_action_at": int(_time.time()), "events_per_min": 0, "latency_ms": None},
            {"name": "signal_engine",  "label": "Signal Engine",    "status": "ok", "last_action_at": int(_time.time()), "events_per_min": 0, "latency_ms": None},
            {"name": "basis_calc",     "label": "Basis Calculator", "status": "ok", "last_action_at": int(_time.time()), "events_per_min": 0, "latency_ms": None},
        ]
        # Downgrade module status based on watchdog stage
        if self._watchdog:
            stage_map = {s["name"]: s["stage"] for s in self._watchdog.get_all_statuses()}
            for m in modules:
                stage = stage_map.get(m["name"])
                if stage == "degraded":
                    m["status"] = "degraded"
                elif stage in ("lost", "dead"):
                    m["status"] = "frozen"

        # ── Basis ─────────────────────────────────────────────────────────────
        basis = []
        if self._basis_calculator:
            for sym, b in self._basis_calculator.last_basis.items():
                basis.append({
                    "symbol":     sym,
                    "spot":       b.get("spot", 0),
                    "futures":    b.get("futures", 0),
                    "basis":      b.get("basis", 0),
                    "basis_pct":  b.get("basis_pct", 0),
                    "updated_at": b.get("timestamp", 0),
                })

        # ── Data trust rows ───────────────────────────────────────────────────
        data_rows = []
        if self._data_verifier:
            for key, score in self._data_verifier.get_trust_scores().items():
                parts = key.split(":")
                if len(parts) == 3:
                    data_rows.append({
                        "symbol":              parts[0],
                        "timeframe":           parts[1],
                        "market_type":         parts[2],
                        "last_candle_at":      None,
                        "gaps_24h":            0,
                        "verification_status": "ok" if score >= 80 else ("degraded" if score >= 50 else "failed"),
                        "trust_score":         score,
                        "size_mb":             0,
                    })

        # ── DB size ───────────────────────────────────────────────────────────
        db_path = os.path.join("data", "terminal.db")
        try:
            db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        except Exception:
            db_size_mb = 0.0

        # ── Rate limit ────────────────────────────────────────────────────────
        rate_limit = {"used": 0, "limit": 2400, "pct": 0.0, "priority": "NORMAL"}
        if self._rest_client and hasattr(self._rest_client, "_rate_guard"):
            rg = self._rest_client._rate_guard
            used  = getattr(rg, "used",  0)
            limit = getattr(rg, "limit", 2400) or 2400
            pct   = round(used / limit * 100, 1)
            rate_limit = {
                "used": used, "limit": limit, "pct": pct,
                "priority": "CRITICAL" if pct > 90 else ("HIGH" if pct > 70 else "NORMAL"),
            }

        await self._send(ws, {
            "type":               "pulse_state",
            "connections":        connections,
            "modules":            modules,
            "rate_limit":         rate_limit,
            "data_rows":          data_rows,
            "basis":              basis,
            "db_size_mb":         db_size_mb,
            "db_growth_mb_7d":    0,
            "db_forecast_days":   None,
            "last_aggregation_at": None,
            "updated_at":         int(_time.time()),
        })

    async def _broadcast_event(self, event_type: str, data: dict) -> None:
        await self._broadcast({
            "type": "event",
            "event_type": event_type,
            "data": _serialise(data),
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    async def _handle_run_validation(self, ws: WebSocketResponse, payload: dict) -> None:
        """Запускает проверку данных и публикует результат."""
        symbol = payload.get("symbol", "BTC/USDT")
        mode   = payload.get("mode", "quick")  # 'quick' (3 окна) или 'full' (10 окон)
        windows = 3 if mode == "quick" else 10
        task_id = f"validation-{symbol}-{int(time.time())}"

        asyncio.create_task(self._run_validation_task(task_id, symbol, windows))

    async def _run_validation_task(self, task_id: str, symbol: str, windows: int) -> None:
        """Выполняет валидацию в фоне и публикует результат."""
        import aiohttp as _aiohttp
        from sqlalchemy import func, select
        from storage.database import get_session_factory
        from storage.models import CandleModel

        BASE_URL  = "https://open-api.bingx.com"
        TF        = "1m"
        WINDOW    = 50
        VOL_TOL   = 0.001
        PRICE_TOL = 0.001

        def fmt_sym(s: str) -> str:
            return s.replace("/", "-")

        factory = get_session_factory()

        # Узнаём диапазон данных в БД
        try:
            async with factory() as session:
                row = await session.execute(
                    select(
                        func.min(CandleModel.open_time),
                        func.max(CandleModel.open_time),
                    ).where(
                        CandleModel.symbol == symbol,
                        CandleModel.timeframe == TF,
                    )
                )
                min_ts, max_ts = row.one()
        except Exception as e:
            await self._bus.publish("validation.result", {
                "task_id": task_id, "symbol": symbol,
                "status": "error", "error": str(e),
            })
            return

        if not min_ts or not max_ts:
            await self._bus.publish("validation.result", {
                "task_id": task_id, "symbol": symbol,
                "status": "error", "error": "Нет данных в БД",
            })
            return

        import random
        span = max_ts - min_ts
        window_ms = WINDOW * 60 * 1000

        total_checked  = 0
        total_missing  = 0
        total_mismatch = 0
        window_results = []

        try:
            connector = _aiohttp.TCPConnector(resolver=_aiohttp.ThreadedResolver())
            async with _aiohttp.ClientSession(
                connector=connector,
                timeout=_aiohttp.ClientTimeout(total=15),
            ) as http:
                for w in range(windows):
                    if span <= window_ms:
                        start = min_ts
                    else:
                        start = random.randint(min_ts, max_ts - window_ms)
                    end = start + window_ms

                    # Fetch from API
                    params = {
                        "symbol": fmt_sym(symbol),
                        "interval": TF,
                        "startTime": start,
                        "endTime": end,
                        "limit": WINDOW + 5,
                    }
                    try:
                        async with http.get(
                            f"{BASE_URL}/openApi/swap/v3/quote/klines",
                            params=params,
                        ) as resp:
                            data = await resp.json()
                        api_data: dict[int, dict] = {}
                        for r in data.get("data", []):
                            t = int(r["time"])
                            api_data[t] = {
                                "open":   float(r["open"]),
                                "high":   float(r["high"]),
                                "low":    float(r["low"]),
                                "close":  float(r["close"]),
                                "volume": float(r["volume"]),
                            }
                    except Exception:
                        api_data = {}

                    # Fetch from DB
                    async with factory() as session:
                        rows = await session.execute(
                            select(CandleModel).where(
                                CandleModel.symbol == symbol,
                                CandleModel.timeframe == TF,
                                CandleModel.open_time >= start,
                                CandleModel.open_time <= end,
                            ).order_by(CandleModel.open_time)
                        )
                        db_rows = rows.scalars().all()
                    db_data: dict[int, dict] = {
                        c.open_time: {
                            "open": c.open, "high": c.high,
                            "low": c.low, "close": c.close, "volume": c.volume,
                        }
                        for c in db_rows
                    }

                    api_times = set(api_data)
                    db_times  = set(db_data)
                    missing   = len(api_times - db_times)
                    common    = api_times & db_times
                    mismatches = 0
                    for ts in common:
                        for field in ("open", "high", "low", "close"):
                            diff = abs(api_data[ts][field] - db_data[ts][field])
                            rel  = diff / api_data[ts][field] if api_data[ts][field] else 0
                            if rel > PRICE_TOL:
                                mismatches += 1
                                break
                        else:
                            vdiff = abs(api_data[ts]["volume"] - db_data[ts]["volume"]) / (api_data[ts]["volume"] or 1)
                            if vdiff > VOL_TOL:
                                mismatches += 1

                    total_checked  += len(api_times)
                    total_missing  += missing
                    total_mismatch += mismatches
                    window_results.append({
                        "window": w + 1,
                        "start_ms": start,
                        "end_ms": end,
                        "api_count": len(api_times),
                        "db_count": len(db_times),
                        "missing": missing,
                        "mismatch": mismatches,
                        "ok": missing == 0 and mismatches == 0,
                    })
                    await asyncio.sleep(0.5)

        except Exception as e:
            await self._bus.publish("validation.result", {
                "task_id": task_id, "symbol": symbol,
                "status": "error", "error": str(e),
            })
            return

        overall_ok = total_missing == 0 and total_mismatch == 0
        await self._bus.publish("validation.result", {
            "task_id": task_id,
            "symbol": symbol,
            "timeframe": TF,
            "windows_checked": windows,
            "total_checked": total_checked,
            "total_missing": total_missing,
            "total_mismatch": total_mismatch,
            "ok": overall_ok,
            "windows": window_results,
            "status": "completed",
            "ts": int(time.time()),
        })

    async def _send_candles(self, ws: WebSocketResponse, symbol: str, tf: str, limit: int) -> None:
        from storage.repositories.candles_repo import CandlesRepository
        repo = CandlesRepository()
        try:
            candles = await repo.get_latest(symbol, tf, limit)
            await self._send(ws, {
                "type":    "candles_data",
                "symbol":  symbol,
                "tf":      tf,
                "candles": [
                    {"time": c.open_time // 1000, "open": c.open,
                     "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                    for c in candles
                ],
            })
        except Exception as e:
            log.error(f"Ошибка получения свечей {symbol} {tf}: {e}")

    async def _send_db_stats(self, ws: WebSocketResponse) -> None:
        """Собирает статистику по таблицам БД и отправляет клиенту."""
        from datetime import datetime, timezone
        from sqlalchemy import Integer, case, func, select
        from storage.database import get_session_factory
        from storage.models import CandleModel, OrderBookSnapshotModel

        factory = get_session_factory()

        def ts_to_iso(ts: int | None) -> str | None:
            if ts is None:
                return None
            # open_time хранится в миллисекундах
            try:
                return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            except Exception:
                return None

        candles_stats: list[dict] = []
        ob_stats: list[dict] = []

        try:
            async with factory() as session:
                # Свечи — группировка по symbol + timeframe
                rows = await session.execute(
                    select(
                        CandleModel.symbol,
                        CandleModel.timeframe,
                        func.count().label("count"),
                        func.min(CandleModel.open_time).label("min_ts"),
                        func.max(CandleModel.open_time).label("max_ts"),
                        func.sum(
                            case((CandleModel.open <= 0, 1), else_=0)
                        ).label("invalid"),
                    ).group_by(CandleModel.symbol, CandleModel.timeframe)
                    .order_by(CandleModel.symbol, CandleModel.timeframe)
                )
                for r in rows:
                    candles_stats.append({
                        "symbol":    r.symbol,
                        "timeframe": r.timeframe,
                        "count":     r.count,
                        "from":      ts_to_iso(r.min_ts),
                        "to":        ts_to_iso(r.max_ts),
                        "invalid":   r.invalid or 0,
                        "ok":        r.count - (r.invalid or 0),
                    })

                # Стакан — группировка по symbol
                ob_rows = await session.execute(
                    select(
                        OrderBookSnapshotModel.symbol,
                        func.count().label("count"),
                        func.min(OrderBookSnapshotModel.timestamp).label("min_ts"),
                        func.max(OrderBookSnapshotModel.timestamp).label("max_ts"),
                        func.avg(OrderBookSnapshotModel.imbalance).label("avg_imbalance"),
                    ).group_by(OrderBookSnapshotModel.symbol)
                    .order_by(OrderBookSnapshotModel.symbol)
                )
                for r in ob_rows:
                    ob_stats.append({
                        "symbol":        r.symbol,
                        "count":         r.count,
                        "from":          ts_to_iso(r.min_ts),
                        "to":            ts_to_iso(r.max_ts),
                        "avg_imbalance": round(r.avg_imbalance or 0, 4),
                    })

        except Exception as e:
            log.error(f"Ошибка получения статистики БД: {e}")

        await self._send(ws, {
            "type":    "db_stats",
            "candles": candles_stats,
            "orderbook": ob_stats,
        })

    # ── Event forwarding ──────────────────────────────────────────────────────

    async def _on_event(self, event: Event) -> None:
        if not self._clients:
            return

        # Обновляем БД при завершении/паузе/ошибке бэкфилла
        et = event.type
        d  = event.data if isinstance(event.data, dict) else {}
        tid = d.get("task_id", "")

        if et == "backfill.progress" and tid:
            status = d.get("status", "running")
            if status == "paused":
                await self._tasks_repo.mark_status(
                    tid, "paused",
                    percent=d.get("percent", 0),
                    fetched=d.get("fetched", 0),
                    total_pages=d.get("total", 0),
                    total_saved=d.get("total_saved", 0),
                    checkpoint_end_ms=d.get("checkpoint_end_ms"),
                )
                self._active_backfills.pop(tid, None)
            else:
                await self._tasks_repo.mark_status(
                    tid, "running",
                    percent=d.get("percent", 0),
                    fetched=d.get("fetched", 0),
                    total_pages=d.get("total", 0),
                    total_saved=d.get("total_saved", 0),
                    checkpoint_end_ms=d.get("checkpoint_end_ms"),
                    speed_cps=self._active_backfills.get(tid, {}).get("speed_cps", 0),
                )
        elif et == "backfill.complete" and tid:
            await self._tasks_repo.mark_status(
                tid, "completed",
                percent=100,
                total_saved=d.get("total_saved", d.get("total_fetched", 0)),
            )
            self._active_backfills.pop(tid, None)
        elif et == "backfill.error" and tid:
            await self._tasks_repo.mark_status(
                tid, "error",
                error=d.get("error", ""),
            )
            self._active_backfills.pop(tid, None)

        # Добавляем speed_cps и eta_seconds в прогресс-событие из кэша
        if et == "backfill.progress" and tid and tid in self._active_backfills:
            info = self._active_backfills[tid]
            augmented_data = {
                **d,
                "speed_cps":   info.get("speed_cps", 0),
                "eta_seconds": info.get("eta_seconds"),
            }
            message = {
                "type": "event",
                "event_type": event.type,
                "data": _serialise(augmented_data),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            await self._broadcast(message)
            return

        message = {
            "type": "event",
            "event_type": event.type,
            "data": _serialise(event.data),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        await self._broadcast(message)

    async def _broadcast(self, message: dict) -> None:
        payload = json.dumps(message, default=str)
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def _send(self, ws: WebSocketResponse, message: dict) -> None:
        try:
            await ws.send_str(json.dumps(message, default=str))
        except Exception:
            pass

    async def _send_state(self, ws: WebSocketResponse) -> None:
        """Отправляет текущее состояние системы при подключении клиента."""
        signals = [
            {
                "id": s.id,
                "symbol": s.symbol,
                "direction": s.direction,
                "score": s.score,
                "source": s.source,
                "auto_eligible": s.auto_eligible,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in self._signal_engine.get_queue()
        ]
        positions = self._execution_engine.get_positions()
        mode = self._execution_engine.mode.value

        # Активные задачи (без stop_flag)
        active_backfills_clean = [
            {k: v for k, v in t.items() if k != "stop_flag"}
            for t in self._active_backfills.values()
        ]

        # Приостановленные задачи из БД
        paused_tasks = await self._tasks_repo.get_paused()

        await self._send(ws, {
            "type": "state",
            "positions": positions,
            "signals": signals,
            "mode": mode,
            "active_backfills": active_backfills_clean,
            "paused_tasks": paused_tasks,
        })


def _serialise(data):
    """Делает данные JSON-сериализуемыми (рекурсивно)."""
    if hasattr(data, "isoformat"):
        return data.isoformat()
    if isinstance(data, dict):
        return {k: _serialise(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_serialise(v) for v in data]
    if hasattr(data, "__dict__"):
        return {k: _serialise(v) for k, v in data.__dict__.items()
                if not k.startswith("_")}
    return data
