# Журнал разработки — RU
## Криптовалютный торговый терминал

> **Правило:** Новая запись после каждой рабочей сессии или завершённого этапа.  
> Кратко: что сделано, какие решения приняты, что отложено и почему.  
> Английская версия ведётся параллельно в `DEVLOG_EN.md`.

---

## Формат записи

```
### [ГГГГ-ММ-ДД] Название этапа

**Что сделано:**
- пункт

**Решения:**
- решение и обоснование

**Отложено:**
- что и почему

Тесты:
  Unit:        ✅ / ❌ / — / ⏳
  Integration: ✅ / ❌ / — / ⏳
  Smoke:       ✅ / ❌ / — / ⏳
  Покрытие:    XX%

Коммит: `hash` или `—`
Следующий шаг: ...
```

**Статусы тестов:**
`✅` готов и зелёный · `❌` есть падения · `—` не применимо · `⏳` запланирован

---

## Записи

### [2026-04-18] Phase 1-F: График, исторические свечи, DataView polish

**Что сделано:**

**Детектор закрытых свечей (`data/bingx_ws.py`):**
- BingX Futures WS не отправляет поле `x` (is_closed) в kline-событиях
- Добавлен `_prev_candles: dict[str, Candle]` — стейт-машина: свеча считается закрытой когда `open_time` следующего тика изменился
- Публикует `candle.1m.closed` (предыдущая свеча) и `candle.1m.tick` (текущая живая свеча)

**Исторический бэкфилл (`data/backfill.py`):**
- Новый модуль `run_backfill(symbols, rest_client, repo)`: при старте сравнивает кол-во свечей в БД с целевым (`TARGET_CANDLES`: 1m=1440, 5m=1440, 1h=720 и т.д.)
- Если данных не хватает — докачивает через REST BingX (лимит 1440 свечей за запрос)
- Запускается как фоновая задача `asyncio.create_task()` в `main.py`

**REST-эндпоинт для свечей (`ui/ws_server.py`):**
- Добавлен `GET /api/candles?symbol=&tf=&limit=` — прямой HTTP доступ к `CandlesRepository`
- CORS-заголовок `Access-Control-Allow-Origin: *` — фронтенд может запрашивать данные без WS
- Исправлена ошибка `'TextClause' object has no attribute '_isnull'` в `_send_db_stats`: заменён невалидный `.cast(text("INTEGER"))` на `case((CandleModel.open <= 0, 1), else_=0)`

**График (`ui/react-app/src/components/ChartView.tsx`):**
- Полный редизайн: TradingView Lightweight Charts v4, свечи + гистограмма объёма
- Исторические данные загружаются через `fetch('/api/candles?...')` напрямую (REST, не WS) — устраняет ненадёжность цепочки WS-команда→ответ
- Стор обновляется напрямую: `useStore.getState().setHistoricalCandles(key, json.candles)`
- RT-обновления (`candle.1m.tick`) приходят через WS и объединяются с историей через `mergeCandles()`
- Тулбар: переключатель пар (5 монет), таймфрейм (6 кнопок), текущая цена + % изменения от первой свечи, счётчики БД/RT

**DataView (`ui/react-app/src/components/DataView.tsx`):**
- Таблица свечей: группировка по символу, сворачиваемые группы (по умолчанию свёрнуты), в шапке — пара, ТФ, кол-во свечей, статус валидации
- Тултип `StatusIndicator` переведён на `ReactDOM.createPortal(…, document.body)` — гарантированно появляется поверх любых flex/overflow контейнеров, которые раньше обрезали тултип
- `persist` middleware в Zustand: запоминает `activeTab`, `chartSymbol`, `chartTf` между перезагрузками страницы
- Анимированные индикаторы состояния: CSS-классы `status-dot-ok` / `status-dot-err` с keyframe-пульсацией

**Решения:**
- REST вместо WS для исторических свечей: WS не гарантирует доставку ответа на `get_candles`-команду (нет correlation ID, нет retry), REST семантически корректен для одноразового запроса данных
- `createPortal` для тултипа: `position: fixed` внутри flex-контейнера с `overflow: hidden` не выходит за его пределы — портал в `document.body` решает это раз и навсегда
- Бэкфилл как `asyncio.create_task` (не `await`): не блокирует запуск остальных модулей, данные докачиваются параллельно с началом работы WS-потока

**Отложено:**
- Бэкфилл для ТФ выше 1m (5m, 1h и т.д.) — REST `/klines` с нужным интервалом есть, но TF Aggregator уже делает это из 1m-свечей; приоритет низкий

Тесты:
  Unit:        —
  Integration: —
  Smoke:       —
  Покрытие:    н/д

Коммит: `—`
Следующий шаг: AI Advisor или ML Dataset (Phase 1-G)

---

### [2026-04-17] Phase 1-F: UI — Electron + React + WebSocket сервер

**Что сделано:**
- `ui/ws_server.py` — WebSocket сервер (aiohttp): транслирует все события Event Bus клиентам, обрабатывает команды (confirm_signal, reject_signal, close_position, set_mode, get_state), отправляет начальное состояние при подключении. Протокол: JSON с type=event|state|command|pong
- `ui/react-app/` — React + TypeScript приложение (Vite):
  - `src/types/index.ts` — все TypeScript типы (Signal, Position, BusEvent, Candle, TradeRecord)
  - `src/store/useStore.ts` — Zustand store: состояние системы, события, свечи, сделки, навигация
  - `src/hooks/useWebSocket.ts` — WS хук: подключение, реконнект, роутинг входящих сообщений в стор
  - `src/components/Dashboard.tsx` — открытые позиции, очередь сигналов, переключение режимов, paper trading статистика
  - `src/components/ChartView.tsx` — TradingView Lightweight Charts, переключение пар/таймфреймов, live candle updates
  - `src/components/EventBusMonitor.tsx` — живой поток событий с фильтрацией, цветовой кодировкой, паузой
  - `src/components/TradePanel.tsx` — форма открытия позиции, калькулятор размера по риску
  - `src/components/Analytics.tsx` — журнал сделок, win rate, PnL, profit factor
  - `src/components/Sidebar.tsx` — навигация, счётчик событий, статус подключения
- `ui/electron/main.js` + `preload.js` — Electron обёртка (1440×900, hiddenTitleBar, dev/prod режимы)
- 12 unit-тестов для WS сервера (сериализация, команды, broadcast)

**Решения:**
- `_serialise()` рекурсивно обходит dict/list/объекты и datetime → isoformat строки
- `_on_event` не рассылает если `not self._clients` — избегаем лишней сериализации
- `weakref.WeakSet` для клиентов — автоматическая очистка отключившихся WS соединений
- Electron загружает `http://localhost:5173` в dev режиме и `dist/index.html` в production
- WS реконнект каждые 3 секунды на стороне React

**Запуск UI:**
```bash
cd ui/react-app && npm install && npm run dev   # браузер: http://localhost:5173
# или
npm run electron:dev                            # Electron desktop app
```

Тесты:
  Unit:        ✅ 203/203
  Integration: —
  Smoke:       —
  Покрытие:    н/д

Коммит: `—`
Следующий шаг: Phase 1-G — AI Advisor + ML Dataset

---

### [2026-04-17] Phase 1-E: Signal Engine + Execution Engine

**Что сделано:**
- `signals/signal_engine.py` — Signal Engine: генерирует сигналы из `mtf.score.updated` (score ≥ 60) и `correlation.divergence`. TTL 5 минут, дедупликация по symbol+direction, `get_queue()`, `mark_executed()`, `tick()`. Публикует `signal.generated/expired/executed`
- `signals/anomaly_detector.py` — Anomaly Detector: flash crash (> 3% за 3 свечи), price spike (> 3% за свечу), OB манипуляция (spoof + высокий imbalance), slippage аномалия. Cooldown 60с против спама. Публикует `anomaly.flash_crash/price_spike/ob_manip/slippage`
- `execution/risk_guard.py` — Risk Guard: фиксированный риск 1%/сделку, дневной стоп-лосс 5%, макс. 3 позиции, макс. плечо 10x. Формула размера: `size = capital × risk_pct / sl_pct × leverage`
- `execution/bingx_private.py` — Private API client: HMAC-SHA256 подпись, market/limit ордера, close_position, get_positions, get_balance. `dry_run=True` по умолчанию — логирует вместо исполнения
- `execution/execution_engine.py` — Execution Engine: три режима (AUTO/SEMI_AUTO/ALERT_ONLY), переключение без перезапуска. Semi-auto: таймаут 30с, `confirm()`/`reject()`. Реагирует на anomaly.flash_crash (блокирует входы 5 мин), anomaly.ob_manip (задержка 10с)
- `main.py` — подключены все новые модули; `TRADING_MODE=paper` (dry_run), `INITIAL_CAPITAL` из env

**Решения:**
- `bus.subscribe` в тестах требует `await bus.start()` иначе dispatch loop не запущен и события не доставляются — фиксили в 3 тестах
- `dry_run=True` по умолчанию — реальный BingX API вызывается только при `TRADING_MODE=live`
- `_clear_flash_crash` через `call_later(300)` — не блокирует event loop при 5-минутной паузе

**Отложено:**
- UI для подтверждения semi-auto — Phase 1-F
- Реальная интеграция SL/TP через API BingX — после тестирования paper trading

Тесты:
  Unit:        ✅ 191/191
  Integration: —
  Smoke:       —
  Покрытие:    н/д

Коммит: `—`
Следующий шаг: Phase 1-F — UI (Electron + React)

---

### [2026-04-17] Phase 1-D: Backtester & Strategy Builder

**Что сделано:**
- `strategies/base_strategy.py` — абстрактный класс `AbstractStrategy` + `Signal` dataclass (direction, size_pct, sl_pct, tp_pct, confidence). Контракт для всех стратегий
- `strategies/simple_ma_strategy.py` — пример стратегии MA Crossover (fast/slow параметры), используется в тестах и оптимизаторе
- `backtester/engine.py` — `BacktestEngine`: поочерёдный обход свечей, управление позицией, проверка SL/TP по high/low каждого бара, комиссия обе стороны, сложные проценты. `BacktestConfig`, `BacktestTrade`, `BacktestResult`
- `backtester/metrics.py` — `compute_metrics()`: Total PnL, Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio (аннуализированный), avg duration, best/worst trade, trades/month
- `backtester/optimizer.py` — `GridSearchOptimizer`: перебор всех комбинаций параметров, walk-forward валидация (train_ratio=0.7), сортировка по target_metric. `StrategyFingerprint`: профиль стратегии (лучшее направление, волатильность, % SL/TP exits)
- `backtester/demo_mode.py` — `DemoMode`: paper trading на живых событиях, подписан на `candle.{tf}.closed`, симулирует позицию как Engine, публикует `demo.trade.opened/closed/stats.updated`
- 33 новых unit-теста (13 метрик + 10 engine + 7 optimizer + 5 demo)

**Решения:**
- `t.get("entry_time") is not None` вместо `t.get("entry_time")` — `entry_time=0` ложное значение, пропускалось в duration расчёте
- `profit_factor=0.0` (не None) когда gross_profit=0 и gross_loss>0 — математически корректно
- Engine позволяет повторный вход на той же свече после SL/TP — стратегия сама управляет состоянием через `on_close()`

**Отложено:**
- Bayesian Optimization — Phase 1-G или по необходимости (Grid Search достаточен для MVP)
- Интеграция с БД (загрузка исторических свечей) — через `CandlesRepository.get_range()`

Тесты:
  Unit:        ✅ 153/153
  Integration: —
  Smoke:       —
  Покрытие:    н/д

Коммит: `—`
Следующий шаг: Phase 1-E — Signal Engine + Execution Engine

---

### [2026-04-17] Phase 1-C: MTF Confluence + Correlation Engine

**Что сделано:**
- `analytics/mtf_confluence.py` — MTF Confluence Engine: взвешенный score 0–100 по всем ТФ (1m→1M), множители SMC/Volume/OB/Fear&Greed/Spoof. `subscribe_ta_for_symbols()` для явной подписки (wildcard не поддерживается шиной). Публикует `mtf.score.updated` с полями `actionable`/`auto_eligible`
- `analytics/correlation.py` — Correlation Engine: Pearson корреляция пар с BTC/ETH (скользящее окно 50 свечей), режим рынка (following/inverse/independent), детектор дивергенции (пара обычно следует за BTC, но за последние 3 свечи разошлись). Публикует `correlation.updated`, `correlation.divergence`, `correlation.matrix` (каждые 20 обновлений)
- `tests/unit/test_mtf_confluence.py` — 15 тестов: `_ta_direction`, score при TA/SMC/Volume/OB/Spoof, cap 100, удаление нейтрального сигнала, проверка публикации событий
- `tests/unit/test_correlation.py` — 23 теста: `pearson`, `pct_changes`, `_market_regime`, `_check_divergence`, `CorrelationEngine` (накопление, MIN_WINDOW, публикация, матрица, игнорирование неотслеживаемых символов)
- `main.py` — подключены `MTFConfluenceEngine` и `CorrelationEngine`

**Решения:**
- `subscribe_ta_for_symbols(symbols)` вызывается явно после `start()` — EventBus не поддерживает wildcard-паттерны (`ta.*.{tf}.updated`)
- Тест на "нейтральный сигнал удаляется": для полного нейтралитета нужно не передавать EMA-поля (иначе дефолты дают bull EMA cross)
- Тест на multiplier: при strength=1.0 на одном ТФ base уже 100 → нельзя проверить рост. Используем слабый сигнал (только MACD > 0) → base=25

**Отложено:**
- Sentiment Engine (Fear/Greed интеграция в MTF) — при реализации `external_feeds.py`

Тесты:
  Unit:        ✅ 120/120
  Integration: —
  Smoke:       —
  Покрытие:    н/д

Коммит: `—`
Следующий шаг: Phase 1-D — Backtester & Strategy Builder

---

### [2026-04-17] Phase 1-C: Analytics Core

**Что сделано:**
- `analytics/ta_engine.py` — TA Engine: RSI(14) с промежуточными avg_gain/avg_loss, MACD(12/26/9) с ema_fast/ema_slow, EMA(9/21/50/200), Bollinger Bands(20/2.0), ATR(14), VWAP (сессионный), Stochastic(14/3/3), поддержка/сопротивление, пивот-поинты, паттерны (doji, hammer, pin-bar, engulfing). Подписан на все ТФ, публикует `ta.{symbol}.{tf}.updated`
- `analytics/smartmoney.py` — SMC Engine: FVG (3-свечной паттерн), BOS (пробой swing high/low), CHoCH (смена характера), Order Block (последняя свеча против движения), Premium/Discount зоны. Публикует соответствующие события в Event Bus
- `analytics/volume_engine.py` — Volume Engine: CVD из потока сделок (real-time), дельта свечи из OHLCV (аппроксимация), Volume Profile с POC/VAH/VAL (70% value area)

**Решения:**
- RSI при avg_loss=0 (чистый рост) → RSI=100, не NaN. Использован `where()` вместо division-by-zero
- Hammer: `upper_wick <= body` (не строго <) — при одинаковых значениях тоже считается молотом
- OB тест: `lookback=5` чтобы окно содержало нужный паттерн — `candles[-lookback:]` выбирает последние N свечей
- Volume Profile: итеративный обход вокруг POC для построения Value Area (точная реализация без сортировки)

**Отложено:**
- Correlation Engine (7.4) — следующий шаг
- Sentiment Engine (7.5) — после external_feeds

Тесты:
  Unit:        ✅ 82/82
  Integration: —
  Smoke:       —
  Покрытие:    н/д

Коммит: `—`
Следующий шаг: Phase 1-C продолжение — MTF Confluence Engine + Correlation Engine

---

### [2026-04-17] Phase 1-B: Order Book Processor

**Что сделано:**
- `data/ob_processor.py` — полный Order Book Processor:
  - `OrderBook` — локальная копия стакана, apply_snapshot/apply_diff, imbalance, slippage_estimate, liquidity_walls, to_snapshot_dict
  - `SpoofDetector` — отслеживает крупные ордера (> 5× средний), детектирует исчезновение за < 2 сек → `ob.spoof_detected`
  - `OBProcessor` — подписан на `orderbook.update`, публикует `ob.state_updated`, `ob.pressure`, `ob.snapshot`, `ob.spoof_detected`
  - Периодические снимки каждые 10 сек + pre-trade снимок через `calc_slippage()`
- `storage/repositories/orderbook_repo.py` — сохранение снимков стакана в `orderbook_snapshots`

**Решения:**
- `liquidity_walls` считает стену как > N× среднего по всем уровням (включая саму стену) — при маленьких тестовых данных нужен достаточный контраст между мелкими ордерами и стеной
- Spoof detector сбрасывает запись если ордер прожил дольше TTL*3, чтобы не накапливать мусор
- Slippage рассчитывается жадно по уровням стакана — честная оценка реального исполнения

**Отложено:**
- Ничего

Тесты:
  Unit:        ✅ 49/49
  Integration: —
  Smoke:       —
  Покрытие:    н/д

Коммит: `—`
Следующий шаг: Phase 1-C — Analytics Core: TA Engine, SmartMoney Engine, Volume Engine

---

### [2026-04-17] Phase 1-A: Data Layer + Storage

**Что сделано:**
- `data/validator.py` — Pydantic v2 модели: Candle, Trade, OrderBookSnapshot с валидацией (цена > 0, high >= low, объём >= 0)
- `data/rate_limit_guard.py` — токен-бакет с приоритетами (HIGH/MEDIUM/LOW), лимит 20 req/s, экспоненциальный backoff
- `data/bingx_rest.py` — публичный REST клиент: исторические klines, OI, funding rate; маппинг символов BTC/USDT → BTC-USDT
- `data/bingx_ws.py` — WebSocket клиент: подписка на kline_1m, depth20, trade; авто-реконнект с backoff; gzip-декодирование BingX
- `data/tf_aggregator.py` — агрегатор 1m → 3m/5m/15m/30m/1h/2h/4h/6h/12h/1d; подписан на candle.1m.closed; публикует candle.{tf}.closed
- `storage/database.py` — SQLAlchemy async engine, init_db(), синглтон session factory
- `storage/models.py` — 9 ORM-моделей: candles, trades_raw, orderbook_snapshots, market_metrics, signals, trades_journal, strategies, anomalies, market_snapshots, system_logs
- `storage/repositories/candles_repo.py` — upsert/upsert_many, get_latest, get_range, count, delete_before

**Решения:**
- `model_validator(mode='after')` вместо `field_validator` для проверки high >= low — в pydantic v2 field_validator вызывается до того как все поля провалидированы, поэтому info.data.get('low') возвращает None
- `:memory:` SQLite в тестах + сброс синглтона движка через `_engine = None` перед каждым тестом
- `on_conflict_do_update` для upsert — SQLite-специфичный диалект aiosqlite

**Отложено:**
- `data/external_feeds.py` (Fear/Greed, новости) — реализуем при необходимости в Phase 1-C

Тесты:
  Unit:        ✅ 34/34
  Integration: —
  Smoke:       —
  Покрытие:    н/д

Коммит: `—`
Следующий шаг: Phase 1-A финал — `scripts/init_db.py`, `scripts/sync_history.py`, обновление `main.py` с Data Collector + TF Aggregator + Storage

---

### [2026-04-17] Phase 1-A: Базовая инфраструктура

**Что сделано:**
- Создана полная структура папок проекта согласно PRD §18
- Созданы конфигурационные файлы: `pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore`
- Реализован `core/logger.py` — loguru с консольным и файловым выводом, ротация 10MB, хранение 30 дней, логи на русском
- Реализован `core/event_bus.py` — asyncio pub/sub шина с dispatch-циклом, логированием событий, обработкой исключений в хендлерах
- Реализован `core/base_module.py` — абстрактный базовый класс для всех модулей (start/stop/heartbeat/health_check)
- Реализован `core/health_monitor.py` — мониторинг heartbeat с таймаутом 60с, проверка каждые 30с, публикует HEALTH_UPDATE в Event Bus
- Реализован `main.py` — точка входа с graceful shutdown по Ctrl+C

**Решения:**
- `datetime.now(timezone.utc)` вместо `utcnow()` — Python 3.13 выдаёт DeprecationWarning на устаревший метод
- Event Bus использует `asyncio.wait_for(timeout=1.0)` в dispatch-цикле чтобы корректно завершаться при stop()
- Health Monitor через cancel() останавливает фоновую задачу (в отличие от Event Bus, у которого флаг _running)

**Отложено:**
- Ничего из Phase 1-A не отложено

Тесты:
  Unit:        ✅ 13/13
  Integration: —
  Smoke:       —
  Покрытие:    н/д (нет cov плагина в данный момент)

Коммит: `—`
Следующий шаг: Phase 1-A продолжение — Data Collector (bingx_rest.py, bingx_ws.py, rate_limit_guard.py), TF Aggregator, SQLite storage

---

### [2026-04-17] Проектирование архитектуры

**Что сделано:**
- Проведена полная сессия проектирования продукта
- Определена концепция: персональная автоматизированная торговая платформа для BingX Futures/Spot с прицелом на SaaS в Phase 2
- Составлен PRD v1.0 — 20 разделов, полная документация системы
- Созданы все стартовые документы репозитория

**Решения:**
- Event-driven архитектура на asyncio — модули независимы, общаются только через Event Bus. Позволяет разрабатывать и перезапускать модули независимо друг от друга
- Таймфреймы: с биржи берём только 1m, все остальные (до 1M) агрегируем локально — экономит rate-limit BingX и даёт нестандартные ТФ (2h, 3h)
- Order Book подключаем с первого дня — нужен для детектора манипуляций (spoofing), расчёта slippage и будущего скальпинга
- ML Dataset пишем с первого дня, обучать модели будем позже когда накопятся данные
- API-ключ BingX хранится только в Execution Engine — изолирован от остальной системы
- Сборщик данных можно вынести на отдельный VPS с другим IP если упрёмся в rate-limit
- AI Advisor встроен с полным доступом к контексту системы: логи, события, позиции, стратегии
- Event Bus Monitor — отдельная вкладка UI, живой поток всех событий с фильтрацией
- Промежуточные данные индикаторов (raw RSI, ema_fast до сигнальной линии) сохраняются отдельно и анализируются как кандидаты для гибридных стратегий
- Strategy Fingerprint — профиль условий при которых стратегия работает: режим рынка, волатильность, сессия
- Snapshot система — полный срез рынка каждые N минут для отладки и ML
- Журналы разработки ведутся раздельно: DEVLOG_RU.md и DEVLOG_EN.md
- Тесты — обязательная часть завершения каждого модуля (Unit + Integration + Smoke 60 сек)

**Отложено:**
- Выбор конкретных топ-5 торговых пар — определим при старте разработки по текущим объёмам
- ML модели — Phase 2, после накопления достаточного датасета
- Web-интерфейс — Phase 2, бэкенд проектируется так чтобы Electron заменялся без переписывания ядра

Тесты:
  Unit:        — (разработка не начата)
  Integration: —
  Smoke:       —
  Покрытие:    —

Коммит: `—`
Следующий шаг: Инициализация проекта — структура папок, `pyproject.toml`, `.env.example`, базовый Event Bus, Health Monitor, Logger RU

---

<!-- ШАБЛОН

### [ГГГГ-ММ-ДД] 

**Что сделано:**
- 

**Решения:**
- 

**Отложено:**
- 

Тесты:
  Unit:        
  Integration: 
  Smoke:       
  Покрытие:    

Коммит: ``
Следующий шаг: 

-->
