# Changelog / История версий

Все значимые изменения фиксируются в этом файле.  
All notable changes are documented in this file.

Формат основан на [Keep a Changelog](https://keepachangelog.com/).  
Format based on [Keep a Changelog](https://keepachangelog.com/).

Версионирование: `MAJOR.MINOR.PATCH`
- `MAJOR` — архитектурные изменения, несовместимые с предыдущей версией
- `MINOR` — новый функционал, обратно совместимый
- `PATCH` — исправления, мелкие улучшения

---

## [Unreleased] — В разработке

### Planned / Запланировано
- AI Advisor: встроенный ассистент с контекстом системы / Built-in AI advisor with full system context
- ML Dataset: сбор и разметка обучающих данных / ML training dataset collection and labelling

---

## [0.9.0] — 2026-04-19

### Added / Добавлено
- `data/backfill.py` — `repair_integrity()`: авторемонт пропорций TF при каждом старте / TF proportion auto-repair on every startup
- `data/backfill.py` — `refresh_recent()`: перезапись последних 48ч из REST для устранения WS-артефактов / 48h REST overwrite to fix WS artifacts (2 × 1440 candles)
- `data/backfill.py` — полный `AGG_TFS`: добавлены 3m, 30m, 2h / complete AGG_TFS: added 3m, 30m, 2h
- `storage/database.py` — SQLite WAL-режим, busy_timeout=30s, synchronous=NORMAL / WAL mode, busy timeout, NORMAL sync
- `storage/repositories/candles_repo.py` — `delete_timeframe(symbol, tf)` для очистки отдельного TF / method to delete a single TF
- `scripts/validate_candles.py` — кросс-валидация 750 случайных свечей vs BingX REST API / 750-candle cross-validation vs BingX REST API
- `ui/react-app` — мультиселект пар в BackfillModal, «Все пары / Снять все» / multi-pair selection in BackfillModal
- `ui/react-app` — мгновенные уведомления при запуске загрузки (без ожидания WS-ответа) / instant download notifications (no WS round-trip)
- `ui/react-app` — автозагрузка статистики БД при открытии вкладки Данные / auto-load DB stats on Data tab open

### Fixed / Исправлено
- **Критический:** BingX v3 klines API возвращает dict, не массив — `row[0]` → `row["time"]` и т.д. / **Critical:** BingX v3 klines returns dict, not array
- Нарушения пропорций TF (5m > 1m) из-за независимой загрузки каждого TF / TF proportion violations (5m > 1m) from independent per-TF fetching
- Ошибка `database is locked` при параллельной записи и чтении / `database is locked` error under concurrent read+write
- Статистика БД не загружалась при открытии вкладки после обновления страницы / DB stats not loading on tab open after page refresh
- Панель активных загрузок не появлялась сразу после нажатия кнопки / Active downloads panel not appearing immediately on button click

### Changed / Изменено
- `core/logger.py` — retention 30 дней → 7 файлов, compression=gz, всегда INFO в файле / retention 30 days → 7 files, gz compression, always INFO in file
- `core/event_bus.py` — убраны `log.debug()` в subscribe/publish (25+ строк/сек от candle-событий) / removed debug logs from subscribe/publish
- `.env` — `LOG_LEVEL=DEBUG → INFO`
- `data/backfill.py` — `PRICE_TOL` валидации 1e-8 → 0.001 (реалистичный допуск биржи) / validation tolerance 1e-8 → 0.001 (realistic exchange tolerance)

---

## [0.8.0] — 2026-04-18

### Added / Добавлено
- `data/bingx_ws.py` — детектор закрытых свечей по смене `open_time` следующего тика / closed-candle detector via next tick's `open_time` change
- `data/backfill.py` — `run_backfill()`: исторический бэкфилл при старте / historical backfill on startup
- `ui/ws_server.py` — REST endpoint `GET /api/candles` для прямого доступа фронтенда к свечам / REST candle endpoint for frontend
- `ui/react-app` — TradingView Lightweight Charts v4, свечи + объём / candlestick chart + volume histogram
- `ui/react-app` — `DataView`: таблица по символам, сворачиваемые группы, статус валидации / collapsible symbol groups, validation status
- `ui/react-app` — Zustand `persist`: сохранение вкладки, пары, TF между перезагрузками / persist active tab/symbol/tf across refreshes
- `ui/react-app` — `ReactDOM.createPortal` для тултипов поверх overflow-контейнеров / portal tooltips above overflow containers

---

## [0.7.0] — 2026-04-17

### Added / Добавлено
- `ui/ws_server.py` — WebSocket сервер aiohttp: Event Bus → клиенты, команды управления / aiohttp WS server bridging Event Bus to clients
- `ui/react-app/` — React + TypeScript + Vite: Dashboard, ChartView, EventBusMonitor, TradePanel, Analytics, Sidebar
- `ui/electron/` — Electron обёртка 1440×900, dev/prod режимы / Electron wrapper with dev/prod modes
- `signals/signal_engine.py` — скоринг сигналов, TTL 5 мин, дедупликация / signal scoring, 5-min TTL, deduplication
- `signals/anomaly_detector.py` — flash crash, price spike, OB манипуляция, cooldown 60с / flash crash, price spike, OB manipulation detection
- `execution/risk_guard.py` — 1% риск/сделку, дневной стоп 5%, макс. 3 позиции / 1% risk/trade, 5% daily stop, max 3 positions
- `execution/bingx_private.py` — HMAC-SHA256 подпись, market/limit ордера, dry_run / signed private API, dry_run mode
- `execution/execution_engine.py` — AUTO/SEMI_AUTO/ALERT_ONLY режимы, anti-flash-crash пауза / three execution modes with flash-crash guard
- `analytics/mtf_confluence.py` — взвешенный score 0–100 по всем TF, множители SMC/Volume/OB / weighted MTF score with SMC/Volume/OB multipliers
- `analytics/correlation.py` — Pearson корреляция с BTC/ETH, режим рынка, детектор дивергенции / Pearson correlation, market regime, divergence detector
- `analytics/ta_engine.py` — RSI, MACD, EMA, Bollinger, ATR, VWAP, Stochastic, паттерны / full TA suite
- `analytics/smartmoney.py` — FVG, BOS, CHoCH, Order Block, Premium/Discount / full SMC suite
- `analytics/volume_engine.py` — CVD, дельта свечи, Volume Profile с POC/VAH/VAL / CVD, delta, Volume Profile
- `data/ob_processor.py` — реконструкция стакана, SpoofDetector, снимки каждые 10с / full OB reconstruction with spoof detection
- `backtester/engine.py` — бар-за-баром, SL/TP по high/low, комиссии, компаундинг / bar-by-bar SL/TP simulation with compounding
- `backtester/metrics.py` — PnL, Win Rate, Profit Factor, Sharpe, Max Drawdown / full metrics suite
- `backtester/optimizer.py` — Grid Search + Walk-forward валидация / Grid Search with walk-forward validation
- `backtester/demo_mode.py` — paper trading на live событиях / live paper trading mode
- 203 unit-тестов / 203 unit tests

---

## [0.1.0] — 2026-04-17

### Added / Добавлено
- Создан репозиторий проекта / Repository created
- `PRD.md` — полная архитектура системы (20 разделов) / full system architecture (20 sections)
- `README.md` — описание проекта (RU + EN)
- `DEVLOG_RU.md` — журнал разработки на русском / Russian development log
- `DEVLOG_EN.md` — development log in English
- `CHANGELOG.md` — история версий / version history
- `core/logger.py` — loguru, ротация 10MB, 30 дней / loguru with rotation and retention
- `core/event_bus.py` — asyncio pub/sub шина / asyncio pub/sub event bus
- `core/base_module.py` — абстрактный базовый класс / abstract module base class
- `core/health_monitor.py` — heartbeat мониторинг 30с / 30s heartbeat monitoring
- `main.py` — точка входа, graceful shutdown / entry point with graceful shutdown
- `data/validator.py` — Pydantic v2 модели Candle/Trade/OB / Pydantic v2 data models
- `data/rate_limit_guard.py` — токен-бакет с приоритетами / priority token bucket
- `data/bingx_rest.py` — публичный REST клиент klines/OI/funding / public REST client
- `data/bingx_ws.py` — WS клиент, авто-реконнект, gzip / WS client with auto-reconnect and gzip
- `data/tf_aggregator.py` — агрегация 1m → все TF / 1m → all TF aggregation
- `storage/database.py` — SQLAlchemy async engine, init_db() / async SQLAlchemy engine
- `storage/models.py` — 9 ORM-моделей / 9 ORM models
- `storage/repositories/candles_repo.py` — upsert/upsert_many/get_latest/count / candle repository

### Decisions / Решения
- Выбран стек: Python 3.11+, asyncio, Electron + React, SQLite → PostgreSQL / Stack: Python 3.11+, asyncio, Electron + React, SQLite → PostgreSQL
- Выбрана архитектура: Event-driven, независимые модули / Event-driven architecture with independent modules
- Определены фазы: Phase 1 Desktop → Phase 2 Web SaaS / Phases: Phase 1 Desktop → Phase 2 Web SaaS
- Биржа старта: BingX (Futures + Spot) / Exchange: BingX (Futures + Spot)
