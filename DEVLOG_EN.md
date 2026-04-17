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
