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
