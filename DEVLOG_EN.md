# Development Log — EN
## Crypto Trading Terminal

> **Rule:** New entry after each work session or completed milestone.  
> Keep it short: what was done, what decisions were made, what was postponed and why.  
> Russian version is maintained in parallel in `DEVLOG_RU.md`.

---

## Entry format

```
### [YYYY-MM-DD] Phase name

**Done:**
- item

**Decisions:**
- decision and rationale

**Postponed:**
- what and why

Tests:
  Unit:        ✅ / ❌ / — / ⏳
  Integration: ✅ / ❌ / — / ⏳
  Smoke:       ✅ / ❌ / — / ⏳
  Coverage:    XX%

Commit: `hash` or `—`
Next step: ...
```

**Test status legend:**
`✅` written and passing · `❌` has failures · `—` not applicable · `⏳` planned

---

## Entries

### [2026-04-20] Step 1 — Data Foundation: futures WS, Watchdog, verifier, Pulse tab

**Done:**

**DB Schema (`storage/models.py`, `storage/database.py`):**
- `CandleModel`: added `market_type TEXT DEFAULT 'spot'` and `data_trust_score INTEGER DEFAULT 100`
- Unique index `uq_candles` extended to `(symbol, timeframe, open_time, market_type)` — spot and futures stored separately in same table
- `market_type` added to `TradeRawModel`, `OrderBookSnapshotModel`, `MarketSnapshotModel`; `basis` to `MarketSnapshotModel`
- 5 new tables: `FuturesMetricsModel` (OI/Funding/basis), `LiquidationModel` (non-recoverable), `DataVerificationLogModel`, `DataGapModel`, `StorageStatsModel`
- Migrations via `ALTER TABLE ... ADD COLUMN` with `try/except` — backward-compatible; index recreated using `PRAGMA index_info`

**Futures WebSocket (`data/bingx_futures_ws.py`):**
- Independent class `BingXFuturesWebSocket`: subscribes to `@kline_1min`, `@depth20`, `@trade`, `@forceOrder` (liquidations)
- Publishes `futures.candle.1m.closed`, `futures.orderbook.update`, `futures.trade.raw`, `futures.liquidation`
- Own reconnect loop, gzip decompression, updates Watchdog on every message
- Liquidations written to `LiquidationModel` — non-recoverable, WebSocket only

**Basis Calculator (`data/basis_calculator.py`):**
- Listens to `candle.1m.closed` (spot) and `futures.candle.1m.closed` (futures)
- When both prices available: publishes `futures.basis.updated` and writes to `FuturesMetricsModel`
- Public `last_basis: dict[str, dict]` cache — read by `get_pulse_state`

**Watchdog (`data/watchdog.py`):**
- 4 escalation stages: `NORMAL → DEGRADED → LOST → DEAD`
- 3 diagnostic levels: silence counter (5s/30s thresholds), price drift vs REST (0.5% tolerance), reconnect exhaustion
- Exponential backoff: `BACKOFF_BASE × 2^n`, max 10 attempts
- On critical connection degradation (futures WS): immediately writes `DataGapModel(recoverable=False)` to DB
- Publishes `watchdog.degraded/lost/dead/recovered/reconnecting`

**Data Verifier (`data/data_verifier.py`):**
- 4 verification levels: completeness (gap detection), OHLCV accuracy (REST cross-check, 0.01% tolerance), aggregation correctness (1h exchange vs local), continuity (3×ATR spike check)
- Updates `CandleModel.data_trust_score` via batch UPDATE in DB
- Public `get_trust_scores() -> dict[str, int]` — read by Pulse tab

**Pulse Tab UI (`ui/react-app/src/components/PulseView.tsx`):**
- 6 blocks: Connections (status dots + rate-limit bar), Modules (table), Task Queue, Critical Events, Data Status (DB size + basis + trust scores), Event Stream
- New store types in `useStore.ts`: `ConnectionStatus`, `ModuleStatus`, `RateLimitStatus`, `DataTrustRow`, `BasisRow`, `PulseState`, `CriticalEvent`
- «Pulse» tab added to `TopBar.tsx` navigation

**WebSocket server (`ui/ws_server.py`):**
- New command `get_pulse_state`: aggregates data from Watchdog, BasisCalculator, DataVerifier, calculates DB size
- `watchdog.*` and `futures.*` events added to `BROADCAST_EVENTS`
- Optional constructor params `watchdog`, `basis_calculator`, `data_verifier`

**main.py:**
- Wired: `BingXFuturesWebSocket`, `BasisCalculator`, `Watchdog`, `DataVerifier`
- Watchdog registers both WS connections (spot_ws non-critical, futures_ws critical)
- Futures candles subscribed to DB persistence

**Bug fixes:**
- `useWebSocket.ts`: `backtestResults` key fixed to `r.id` (in two places) — history no longer overwritten on repeated runs of same pair/timeframe
- `useWebSocket.ts`: `watchdog.*` events → `pushCriticalEvent`; `pulse_state` message → `setPulseState`
- Optimizer: `optimizer.error` now forcibly resets `localRunning` via `false → true → false` state toggle — fixes "Sending..." button stuck forever

**Decisions:**
- Futures WS as separate class (not subclass of BingXWebSocket): different data formats, different endpoints, independent reconnect loop
- Liquidations WebSocket-only: BingX REST history unavailable → stored without aggregation, gaps recorded in `data_gaps` with `recoverable=False`
- `market_type` in unique index: spot and futures of same symbol coexist in one table, separated at index level — query without `market_type` returns both markets intentionally
- Pulse state is pull-based (client requests on button click), not push: data is stable, no point streaming it every second

**Postponed:**
- Futures REST poller (OI, Funding Rate, Long/Short Ratio) — in Step 1 checklist, implemented separately
- Three-temperature storage (hot/warm/cold) and cold data aggregation — Step 1 §6
- Smart verification scheduling — `DataVerifier` implements 4 levels, scheduling added later

Tests:
  Unit:        —
  Integration: —
  Smoke:       ⏳
  Coverage:    n/a

Commit: `—`
Next step: Futures REST poller (OI/Funding/L-S Ratio) → complete Step 1 checklist

---

### [2026-04-19] Data integrity: backfill, TF aggregation, WAL, auto-repair, logs, cross-validation

**Done:**

**Critical BingX API parsing bug fixed (`data/bingx_rest.py`):**
- BingX v3 `/openApi/swap/v3/quote/klines` returns candles as JSON objects `{"time": ms, "open": "...", ...}`, not arrays `[time, open, ...]`
- Code used `row[0]`, `row[1]` — every candle raised `KeyError` and was silently skipped
- Result: only 521 live 1m candles in DB (from WebSocket stream), zero historical data saved
- Fixed to use `row["time"]`, `row["open"]`, `row["high"]`, `row["low"]`, `row["close"]`, `row["volume"]`

**Backfill strategy: 1m only → aggregate (`data/backfill.py`):**
- Discovered DB anomaly: more 5m candles than 1m (each TF was fetched independently with different time windows)
- Decision: only fetch `1m` via REST API, aggregate all other TFs locally
- `_aggregate_1m(candles_1m, tf, tf_min)`: groups into aligned time windows, skips incomplete candles
- `_save_with_aggregates(candles_1m, repo)`: saves 1m + all AGG_TFS in one call
- `run_backfill` (auto-start): fetches last 2000 1m candles if DB has fewer
- `run_manual_backfill`: paginates backwards for the requested period, aggregates and saves

**Complete AGG_TFS coverage (`data/backfill.py`):**
- Original `AGG_TFS` only included 5m/15m/1h/4h/1d — missing 3m/30m/2h
- Added `3m (3), 30m (30), 2h (120)` → full set: 3m/5m/15m/30m/1h/2h/4h/1d
- Stale mismatched data repaired via `repair_integrity()` on the next startup

**TF integrity auto-repair on startup (`data/backfill.py → repair_integrity()`):**
- Checks proportions: `|actual - expected| / expected > 10%` for each TF
- On violation: deletes all aggregated TFs and recalculates from 1m candles
- Runs automatically every time `main.py` starts, before backfill
- Result: accumulated violations for all 5 pairs resolved in one startup

**Last 48h refresh from REST API (`data/backfill.py → refresh_recent()`):**
- New function: overwrites the last 48 hours of 1m candles from REST on every startup
- 2 requests × 1440 candles = full 48h coverage (API hard limit = 1440 per request)
- Fixes WS artifacts: WebSocket detects candle close by the next tick's `open_time` changing — exchange may not have finalized all trades at that exact moment
- Startup chain: `repair_integrity → refresh_recent → run_backfill`

**DB cleanup and recalculation:**
- Added `CandlesRepository.delete_timeframe(symbol, tf)` to clear a single TF
- All 5 pairs had stale aggregated TFs deleted and recalculated from 1m candles
- BTC/USDT: 43,225 1m → 14,407 3m → 8,644 5m → 2,881 15m → 1,440 30m → 720 1h → 360 2h → 179 4h → 29 1d

**SQLite WAL mode (`storage/database.py`):**
- `PRAGMA journal_mode=WAL` — concurrent readers with one writer (no more locks)
- `PRAGMA busy_timeout=30000` — 30s wait instead of instant `database is locked` error
- `PRAGMA synchronous=NORMAL` — reliability/speed balance
- `connect_args={"timeout": 30}` — driver-level timeout for aiosqlite

**Log size reduction (`core/logger.py`):**
- `LOG_LEVEL=DEBUG → INFO` in `.env` — stopped the flood of debug messages
- File logs always at `INFO` regardless of `LOG_LEVEL`
- `retention=7` files instead of `"30 days"` — prevents GB accumulation of log files
- `compression="gz"` — rotated files compressed automatically
- Removed `log.debug()` from `EventBus.subscribe/publish` — was generating 25+ lines/sec from candle events
- Project size: 913 MB → ~50 MB (after cleaning old logs)

**BackfillModal: multi-pair selection (`ui/react-app/src/components/DataView.tsx`):**
- Toggle buttons to select one or more pairs (blue border = selected)
- "All pairs / Deselect all" quick-toggle button
- All 5 pairs selected by default
- Start button adapts: "Load 5 pairs" / "Start loading"
- Time estimate scales with number of selected pairs

**Instant backfill notifications (`ui/react-app/src/hooks/useWebSocket.ts`):**
- New `startBackfill(symbol, period)` function exported from `useWebSocket`
- On click: immediately creates a notification (`addNotification`) and registers `taskId → notifId` in `notifMapRef`
- "Active downloads" panel in the modal appears instantly, without waiting for backend response
- WS `backfill.progress` events update the existing notification via `updateNotification` (no duplicates)

**Auto-load DB stats (`ui/react-app/src/components/DataView.tsx`):**
- Before: `useEffect([], [])` — command sent on mount but WS not yet open → silently dropped
- Now: `useEffect(() => { if (connected) onRequestStats() }, [connected])` — fires when WS is ready, re-fires on reconnect

**Cross-validation of DB data vs BingX API (`scripts/validate_candles.py`):**
- New script: 3 random 50-candle windows per pair from DB compared against BingX REST API
- Price tolerance `0.1%`, volume tolerance `0.1%` — realistic for WS vs REST settlement pipeline
- Final result after all fixes: 5/5 pairs ✓ OK, 750 checks, 0 mismatches
- Revealed WS artifact nature: BingX continuously settles recent candles; sub-0.1% is normal exchange behaviour
- Windows compatibility: `aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())` instead of aiodns

**Decisions:**
- Aggregating from 1m guarantees mathematical consistency across all TFs — no "artifact" data from API
- `repair_integrity` on every startup — protection against TF proportion drift during WS disconnects
- `refresh_recent` = 48h (2 × 1440) — covers full WS window with margin; one startup fixes everything
- `PRICE_TOL = 0.001` in validation — BingX adjusts closed candles within 0.1% until full settlement
- WAL + busy_timeout: SQLite without locks when analytics reads happen during WS data writes
- `startBackfill` in `useWebSocket` (not `DataView`) — `notifMapRef` lives here; no prop-drilling needed

**Postponed:**
- Progress timeline visualization on the Data tab (after completion — refresh DataView without re-requesting)

Tests:
  Unit:        —
  Integration: —
  Smoke:       ✅ 5/5 pairs, 750 checks vs BingX API, 0 mismatches
  Coverage:    n/a

Commits: `050c2dd` `744925c` `8512365` `76fe105` `bd5f6c6`
Next step: AI Advisor / ML Dataset (Phase 1-G)

---

### [2026-04-18] Phase 1-F: Chart, historical candles, DataView polish

**Done:**

**Closed-candle detector (`data/bingx_ws.py`):**
- BingX Futures WS does not send the `x` (is_closed) field in kline events
- Added `_prev_candles: dict[str, Candle]` state machine: a candle is considered closed when the `open_time` of the next tick changes
- Publishes `candle.1m.closed` (the completed candle) and `candle.1m.tick` (the current live candle)

**Historical backfill (`data/backfill.py`):**
- New module `run_backfill(symbols, rest_client, repo)`: on startup compares candle count in DB vs target (`TARGET_CANDLES`: 1m=1440, 5m=1440, 1h=720, etc.)
- If data is insufficient — fetches via BingX REST (up to 1440 candles per request)
- Launched as a background task via `asyncio.create_task()` in `main.py`

**REST endpoint for candles (`ui/ws_server.py`):**
- Added `GET /api/candles?symbol=&tf=&limit=` — direct HTTP access to `CandlesRepository`
- `Access-Control-Allow-Origin: *` CORS header — frontend can fetch without WS
- Fixed `'TextClause' object has no attribute '_isnull'` bug in `_send_db_stats`: replaced invalid `.cast(text("INTEGER"))` with `case((CandleModel.open <= 0, 1), else_=0)`

**Chart (`ui/react-app/src/components/ChartView.tsx`):**
- Full rewrite: TradingView Lightweight Charts v4, candlesticks + volume histogram
- Historical data fetched via `fetch('/api/candles?...')` directly (REST, not WS) — eliminates unreliable WS command→response chain
- Store updated directly: `useStore.getState().setHistoricalCandles(key, json.candles)`
- RT updates (`candle.1m.tick`) come via WS and are merged with history via `mergeCandles()`
- Toolbar: pair switcher (5 coins), timeframe buttons (6), current price + % change from first candle, DB/RT counters

**DataView (`ui/react-app/src/components/DataView.tsx`):**
- Candles table: grouped by symbol, collapsible groups (collapsed by default), header shows pair, TF, count, validation status
- `StatusIndicator` tooltip moved to `ReactDOM.createPortal(…, document.body)` — guaranteed to appear above any flex/overflow containers that were clipping it before
- Zustand `persist` middleware: saves `activeTab`, `chartSymbol`, `chartTf` across page refreshes
- Animated status dots: CSS classes `status-dot-ok` / `status-dot-err` with keyframe pulse animation

**Decisions:**
- REST instead of WS for historical candles: WS has no correlation ID or retry mechanism for responses — REST is semantically correct for a one-shot data request
- `createPortal` for tooltip: `position: fixed` inside a flex container with `overflow: hidden` does not escape it — portal into `document.body` solves this definitively
- Backfill as `asyncio.create_task` (not `await`): does not block module startup, data is fetched in parallel with the WS stream

**Postponed:**
- Backfill for TFs above 1m — low priority since TF Aggregator already builds them from 1m candles

Tests:
  Unit:        —
  Integration: —
  Smoke:       —
  Coverage:    n/a

Commit: `—`
Next step: AI Advisor or ML Dataset (Phase 1-G)

---

### [2026-04-17] Phase 1-F: UI — Electron + React + WebSocket Server

**Done:**
- `ui/ws_server.py` — aiohttp WebSocket server: broadcasts all Event Bus events to clients, handles commands (confirm_signal, reject_signal, close_position, set_mode, get_state), sends initial state on connect. Protocol: JSON with type=event|state|command|pong
- `ui/react-app/` — React + TypeScript app (Vite):
  - TypeScript types, Zustand store, WebSocket reconnect hook
  - Dashboard: open positions, signal queue, mode switcher, paper trading stats
  - ChartView: TradingView Lightweight Charts with live candle updates, symbol/tf selector
  - EventBusMonitor: live event stream with filter, color-coded by module, pause/clear
  - TradePanel: position form with risk-based size calculator
  - Analytics: trade journal table with PnL stats
  - Sidebar: tab navigation, event counter, connection status
- `ui/electron/main.js + preload.js` — Electron wrapper (1440×900, dev/prod modes)
- 12 unit tests for WS server (serialisation, commands, broadcast)

**Decisions:**
- `_serialise()` recurses into dict/list/objects and converts datetime → isoformat
- `weakref.WeakSet` for clients — auto-cleanup of disconnected WS connections
- Electron loads `http://localhost:5173` in dev, `dist/index.html` in production
- React reconnects every 3s on WS close

**Running the UI:**
```bash
cd ui/react-app && npm install && npm run dev   # browser: http://localhost:5173
# or
npm run electron:dev                            # Electron desktop
```

Tests:
  Unit:        ✅ 203/203
  Integration: —
  Smoke:       —
  Coverage:    n/a

Commit: `—`
Next step: Phase 1-G — AI Advisor + ML Dataset

---

### [2026-04-17] Phase 1-E: Signal Engine + Execution Engine

**Done:**
- `signals/signal_engine.py` — Signal Engine: generates signals from `mtf.score.updated` (score ≥ 60) and `correlation.divergence`. 5-minute TTL, deduplication by symbol+direction, `get_queue()`, `mark_executed()`, `tick()`. Publishes `signal.generated/expired/executed`
- `signals/anomaly_detector.py` — Anomaly Detector: flash crash (>3% over 3 candles), price spike (>3% in one candle), OB manipulation (spoof + high imbalance), slippage anomaly. 60s cooldown. Publishes `anomaly.flash_crash/price_spike/ob_manip/slippage`
- `execution/risk_guard.py` — Risk Guard: fixed 1% risk/trade, 5% daily stop, max 3 positions, max 10x leverage. Size formula: `size = capital × risk_pct / sl_pct × leverage`
- `execution/bingx_private.py` — Private API client: HMAC-SHA256 signing, market/limit orders, close position, get positions/balance. `dry_run=True` by default — logs without executing
- `execution/execution_engine.py` — Three modes (AUTO/SEMI_AUTO/ALERT_ONLY), switchable without restart. Semi-auto: 30s timeout, `confirm()`/`reject()`. Reacts to flash_crash (blocks 5 min) and ob_manip (10s delay)
- `main.py` — all new modules wired; `TRADING_MODE=paper` (dry_run), `INITIAL_CAPITAL` from env

**Decisions:**
- Tests need `await bus.start()` otherwise dispatch loop is not running — events queued but never delivered to subscribers
- `dry_run=True` by default — real BingX API only called when `TRADING_MODE=live`

**Postponed:**
- Semi-auto confirmation UI — Phase 1-F
- Real SL/TP via BingX API — after paper trading validation

Tests:
  Unit:        ✅ 191/191
  Integration: —
  Smoke:       —
  Coverage:    n/a

Commit: `—`
Next step: Phase 1-F — UI (Electron + React)

---

### [2026-04-17] Phase 1-D: Backtester & Strategy Builder

**Done:**
- `strategies/base_strategy.py` — `AbstractStrategy` ABC + `Signal` dataclass (direction, size_pct, sl_pct, tp_pct, confidence)
- `strategies/simple_ma_strategy.py` — MA Crossover example strategy used in tests and optimizer
- `backtester/engine.py` — bar-by-bar simulation, SL/TP checked against high/low each bar, commission both sides, compounding capital. `BacktestConfig`, `BacktestTrade`, `BacktestResult`
- `backtester/metrics.py` — all PRD-required metrics: Total PnL, Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio (annualised), avg trade duration, best/worst trade, trades/month
- `backtester/optimizer.py` — `GridSearchOptimizer`: exhaustive param grid, walk-forward validation (train_ratio=0.7), ranked by target_metric. `StrategyFingerprint`: best direction, volatility profile, SL/TP exit breakdown
- `backtester/demo_mode.py` — paper trading on live candle events; mirrors engine logic; publishes `demo.trade.opened/closed/stats.updated`
- 33 new unit tests (13 metrics + 10 engine + 7 optimizer + 5 demo)

**Decisions:**
- `entry_time is not None` check (not truthy) — `entry_time=0` is falsy, was silently skipping duration calculation
- `profit_factor=0.0` (not None) when gross_profit=0 and gross_loss>0 — mathematically correct
- Engine allows re-entry on same bar after SL/TP — strategy controls state via `on_close()`

**Postponed:**
- Bayesian Optimization — Phase 1-G or on demand (Grid Search is sufficient for MVP)
- DB integration for history loading — via `CandlesRepository.get_range()`

Tests:
  Unit:        ✅ 153/153
  Integration: —
  Smoke:       —
  Coverage:    n/a

Commit: `—`
Next step: Phase 1-E — Signal Engine + Execution Engine

---

### [2026-04-17] Phase 1-C: MTF Confluence + Correlation Engine

**Done:**
- `analytics/mtf_confluence.py` — weighted score 0–100 across all timeframes (1m→1M), multipliers for SMC/Volume/OB/Fear&Greed/Spoof confirmation. Explicit `subscribe_ta_for_symbols()` (wildcard not supported by EventBus). Publishes `mtf.score.updated` with `actionable`/`auto_eligible` flags
- `analytics/correlation.py` — Pearson correlation of pairs vs BTC/ETH (rolling 50-candle window), market regime detection (following/inverse/independent), divergence detector (pair normally follows BTC but last 3 candles diverged). Publishes `correlation.updated`, `correlation.divergence`, `correlation.matrix` (every 20 updates)
- `tests/unit/test_mtf_confluence.py` — 15 tests covering `_ta_direction`, score with TA/SMC/Volume/OB/Spoof, cap at 100, neutral signal removal, event publishing
- `tests/unit/test_correlation.py` — 23 tests covering `pearson`, `pct_changes`, `_market_regime`, `_check_divergence`, full `CorrelationEngine` lifecycle
- `main.py` — wired `MTFConfluenceEngine` and `CorrelationEngine`

**Decisions:**
- `subscribe_ta_for_symbols(symbols)` must be called explicitly after `start()` — EventBus has no wildcard subscription support
- Multiplier tests use a weak single-indicator signal (MACD only, base=25) so there's room to verify the multiplier effect before hitting the 100 cap

**Postponed:**
- Fear/Greed integration in MTF — deferred until `external_feeds.py` is implemented

Tests:
  Unit:        ✅ 120/120
  Integration: —
  Smoke:       —
  Coverage:    n/a

Commit: `—`
Next step: Phase 1-D — Backtester & Strategy Builder

---

### [2026-04-17] Phase 1-B: Order Book Processor

**Done:**
- `data/ob_processor.py` — full Order Book Processor:
  - `OrderBook` — local book state with apply_snapshot/apply_diff, imbalance, slippage_estimate, liquidity_walls
  - `SpoofDetector` — tracks large orders (> 5× avg), detects disappearance within 2s → `ob.spoof_detected`
  - `OBProcessor` — subscribes to `orderbook.update`, publishes `ob.state_updated`, `ob.pressure`, `ob.snapshot`, `ob.spoof_detected`
  - Periodic snapshots every 10s + pre-trade snapshot via `calc_slippage()`
- `storage/repositories/orderbook_repo.py` — persists orderbook snapshots

**Decisions:**
- Liquidity wall detection uses avg across all levels (including the wall itself) — test needed enough contrast between small orders and the wall
- Spoof detector cleans entries older than TTL*3 to avoid memory leaks
- Slippage calculated greedily across book levels — honest estimate of real execution cost

**Postponed:**
- Nothing

Tests:
  Unit:        ✅ 49/49
  Integration: —
  Smoke:       —
  Coverage:    n/a

Commit: `—`
Next step: Phase 1-C — Analytics Core: TA Engine, SmartMoney Engine, Volume Engine

---

### [2026-04-17] Phase 1-A: Data Layer + Storage

**Done:**
- `data/validator.py` — Pydantic v2 models: Candle, Trade, OrderBookSnapshot with full validation
- `data/rate_limit_guard.py` — token bucket with priority queue (HIGH/MEDIUM/LOW), 20 req/s limit
- `data/bingx_rest.py` — public REST client: historical klines, OI, funding rate
- `data/bingx_ws.py` — WebSocket client: kline_1m, depth20, trade subscriptions; auto-reconnect with backoff; gzip decoding
- `data/tf_aggregator.py` — 1m → 3m/5m/15m/30m/1h/2h/4h/6h/12h/1d aggregation; subscribes to candle.1m.closed
- `storage/database.py` — SQLAlchemy async engine, init_db(), singleton session factory
- `storage/models.py` — 9 ORM models per PRD schema
- `storage/repositories/candles_repo.py` — upsert/upsert_many, get_latest, get_range, count, delete_before

**Decisions:**
- Used `model_validator(mode='after')` instead of `field_validator` for high >= low check — in pydantic v2 field_validator fires before all fields are set
- `:memory:` SQLite in tests with singleton engine reset between tests
- `on_conflict_do_update` for upsert — SQLite-specific dialect

**Postponed:**
- `data/external_feeds.py` (Fear/Greed, news) — Phase 1-C

Tests:
  Unit:        ✅ 34/34
  Integration: —
  Smoke:       —
  Coverage:    n/a

Commit: `—`
Next step: Phase 1-A final — `scripts/init_db.py`, `scripts/sync_history.py`, wire up main.py with Data Collector + TF Aggregator + Storage

---

### [2026-04-17] Phase 1-A: Foundation infrastructure

**Done:**
- Created full project folder structure per PRD §18
- Created config files: `pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore`
- Implemented `core/logger.py` — loguru with console + file output, 10MB rotation, 30-day retention
- Implemented `core/event_bus.py` — asyncio pub/sub bus with dispatch loop, event logging, exception isolation per handler
- Implemented `core/base_module.py` — abstract base class for all modules (start/stop/heartbeat/health_check)
- Implemented `core/health_monitor.py` — heartbeat monitoring with 60s timeout, checks every 30s, publishes HEALTH_UPDATE to Event Bus
- Implemented `main.py` — entry point with graceful shutdown on Ctrl+C

**Decisions:**
- Used `datetime.now(timezone.utc)` instead of deprecated `utcnow()` — Python 3.13 raises DeprecationWarning on the old method
- Event Bus uses `asyncio.wait_for(timeout=1.0)` in dispatch loop to allow clean stop()
- Health Monitor uses task.cancel() for stop; Event Bus uses `_running` flag — different patterns intentionally based on behavior needs

**Postponed:**
- Nothing from Phase 1-A was postponed

Tests:
  Unit:        ✅ 13/13
  Integration: —
  Smoke:       —
  Coverage:    n/a

Commit: `—`
Next step: Phase 1-A continuation — Data Collector (bingx_rest.py, bingx_ws.py, rate_limit_guard.py), TF Aggregator, SQLite storage

---

### [2026-04-17] Architecture design

**Done:**
- Completed full product design session
- Defined concept: personal automated trading platform for BingX Futures/Spot, targeting SaaS in Phase 2
- Created PRD v1.0 — 20 sections, full system documentation
- Created all initial repository documents

**Decisions:**
- Event-driven architecture on asyncio — modules are independent, communicate only through the Event Bus. Allows developing and restarting modules without affecting others
- Timeframes: only 1m fetched from exchange, all others (up to 1M) aggregated locally — saves BingX rate-limit and enables non-standard TFs (2h, 3h)
- Order Book connected from day one — needed for manipulation detection (spoofing), slippage calculation, and future scalping
- ML Dataset written from day one, models to be trained later when sufficient data accumulates
- BingX API key stored only in Execution Engine — isolated from the rest of the system
- Data collector can be moved to a separate VPS with a different IP if rate-limit becomes an issue
- AI Advisor embedded with full system context: logs, events, positions, strategies
- Event Bus Monitor — dedicated UI tab, live stream of all events with filtering
- Intermediate indicator data (raw RSI, ema_fast before signal line) stored separately and analyzed as candidates for hybrid strategies
- Strategy Fingerprint — profile of conditions where a strategy performs well: market regime, volatility, session
- Snapshot system — full market state snapshot every N minutes for debugging and ML
- Development logs maintained separately: DEVLOG_RU.md and DEVLOG_EN.md
- Tests are a mandatory part of completing each module (Unit + Integration + Smoke 60 sec)

**Postponed:**
- Selection of specific top-5 trading pairs — to be determined at development start based on current volumes
- ML models — Phase 2, after sufficient dataset is accumulated
- Web interface — Phase 2, backend is designed so Electron can be replaced without rewriting the core

Tests:
  Unit:        — (development not started)
  Integration: —
  Smoke:       —
  Coverage:    —

Commit: `—`
Next step: Project initialization — folder structure, `pyproject.toml`, `.env.example`, base Event Bus, Health Monitor, Logger

---

<!-- TEMPLATE

### [YYYY-MM-DD] 

**Done:**
- 

**Decisions:**
- 

**Postponed:**
- 

Tests:
  Unit:        
  Integration: 
  Smoke:       
  Coverage:    

Commit: ``
Next step: 

-->
