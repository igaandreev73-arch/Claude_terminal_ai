# PRD — Криптовалютный торговый терминал
**Версия:** 1.0  
**Дата:** 2026-04  
**Язык разработки:** Python  
**Среда:** VS Code + Claude Code  
**Статус:** Greenfield / Phase 1 — Desktop

---

## Содержание

1. [Концепция и цели](#1-концепция-и-цели)
2. [Технический стек](#2-технический-стек)
3. [GitHub Workflow](#3-github-workflow)
4. [Общая архитектура](#4-общая-архитектура)
5. [Data Layer — сбор данных](#5-data-layer)
6. [Storage — хранение данных](#6-storage)
7. [Analytics Core — аналитическое ядро](#7-analytics-core)
8. [Order Book Processor](#8-order-book-processor)
9. [Signal Engine](#9-signal-engine)
10. [Backtester и Strategy Builder](#10-backtester-и-strategy-builder)
11. [Execution Engine](#11-execution-engine)
12. [AI Advisor](#12-ai-advisor)
13. [Event Bus и мониторинг](#13-event-bus-и-мониторинг)
14. [Health Monitor и логирование](#14-health-monitor-и-логирование)
15. [UI — интерфейс](#15-ui)
16. [Risk Management](#16-risk-management)
17. [Фазы разработки](#17-фазы-разработки)
18. [Структура проекта](#18-структура-проекта)
19. [Глоссарий](#19-глоссарий)

---

## 1. Концепция и цели

### Что это

Персональная автоматизированная торговая платформа для фьючерсной и спотовой торговли на бирже BingX. Система самостоятельно собирает рыночные данные, анализирует рынок, формирует и тестирует торговые стратегии, генерирует сигналы и исполняет сделки в автоматическом или полуавтоматическом режиме.

### Цели Phase 1

- Один пользователь, одна биржа (BingX), Desktop-приложение
- Непрерывный сбор данных по топ-5 торговым парам (Futures + Spot)
- Аналитический центр: технический анализ, объёмный анализ, SmartMoney, корреляции
- Бэктестинг стратегий и их авто-оптимизация
- Три режима исполнения: авто / полуавто / только алёрт
- Полный мониторинг и логирование на русском языке

### Цели Phase 2 (будущее)

- SaaS-продукт для внешних пользователей
- Web-интерфейс (тот же Python бэкенд, меняется только UI)
- Мультибиржевая поддержка
- ML-модели на накопленных данных

### Торговые пары (старт)

Топ-5 пар по объёму на BingX Futures. Предварительный список:
`BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT`

Список настраивается в конфигурации — не зашит в код.

### Режимы торговли

- **Futures** (основной): бессрочные контракты (Perpetual Swaps)
- **Spot**: дополнительно, для арбитражных и хеджирующих позиций

---

## 2. Технический стек

### Backend (ядро системы)

| Компонент | Технология | Назначение |
|---|---|---|
| Язык | Python 3.11+ | Вся бизнес-логика |
| Асинхронность | asyncio + aiohttp | Параллельная обработка модулей |
| Event Bus | asyncio.Queue + pub/sub | Шина событий между модулями |
| WebSocket | websockets / aiohttp WS | Подключение к BingX WS |
| БД | SQLite (Phase 1) → PostgreSQL + TimescaleDB (Phase 2) | Хранение данных |
| ORM | SQLAlchemy (async) | Работа с БД |
| TA-библиотека | pandas-ta / TA-Lib | Технические индикаторы |
| ML | scikit-learn, lightgbm, tensorflow (Phase 2) | Машинное обучение |
| Планировщик | APScheduler | Периодические задачи |
| Логирование | loguru | Структурированные логи |
| Конфигурация | pydantic-settings + .env | Настройки системы |
| Тесты | pytest + pytest-asyncio | Модульное тестирование |

### Frontend (Desktop Phase 1)

| Компонент | Технология | Назначение |
|---|---|---|
| Фреймворк | Electron + React + TypeScript | Desktop-оболочка |
| Графики | TradingView Lightweight Charts | Свечные графики |
| Стакан | Кастомный компонент React | Order Book визуализация |
| Связь с backend | WebSocket (localhost) | Реалтайм данные в UI |
| Стилизация | Tailwind CSS | Стили |

> **Архитектурное решение:** Python-бэкенд поднимает локальный WebSocket сервер. Electron-фронтенд подключается к нему. При переходе на Web (Phase 2) — меняем только Electron на React-приложение в браузере. Бэкенд не трогаем.

### Внешние сервисы

| Сервис | Назначение | Тип доступа |
|---|---|---|
| BingX REST API | OHLCV история, аккаунт, ордера | Публичный + приватный (только Execution) |
| BingX WebSocket | Тики, стакан, сделки — реалтайм | Публичный |
| Alternative.me API | Fear & Greed Index | Публичный, без ключа |
| CryptoCompare / NewsAPI | Новостной фон | Публичный |

> **Важно:** API-ключ BingX хранится ТОЛЬКО в модуле Execution Engine. Все рыночные данные собираются через публичный API без аутентификации.

---

## 3. GitHub Workflow & Журнал разработки

### Правила коммитов

Каждый завершённый этап разработки фиксируется коммитом с двуязычным описанием:

```
[МОДУЛЬ] Краткое описание на русском

RU: Подробное описание что сделано, что изменено, почему
EN: Detailed description of what was done, what changed, why

Closes #<issue_number>
```

**Пример:**
```
[DATA] Реализован сборщик данных с WebSocket

RU: Добавлен DataCollector с поддержкой BingX WebSocket и REST.
    Реализован rate-limit guard с очередью запросов.
    Валидация входящих данных по JSON-схеме.

EN: Added DataCollector with BingX WebSocket and REST support.
    Implemented rate-limit guard with request queue.
    Added incoming data validation via JSON schema.

Closes #1
```

### Структура веток

```
main          — стабильные релизы
develop       — активная разработка
feature/xxx   — новый функционал
fix/xxx       — исправления
```

### Обязательные файлы в репозитории

```
README.md          — описание проекта (RU + EN)
ARCHITECTURE.md    — актуальная архитектура системы
CHANGELOG.md       — история изменений по версиям
docs/              — документация по модулям
.env.example       — шаблон переменных окружения (без секретов)
```

---

## 4. Общая архитектура

### Принцип: Event-Driven, независимые модули

Каждый модуль — это независимый `asyncio.Task` (или отдельный процесс для тяжёлых задач). Модули не вызывают друг друга напрямую. Всё общение — через центральную шину событий (Event Bus).

**Что это даёт:**
- Можно перезапустить любой модуль не прерывая остальные
- Во время разработки нового модуля все остальные продолжают работать
- Легко добавлять новые подписчики на существующие события
- Прозрачная отладка — все события видны в Event Bus Monitor

### Схема потока данных

```
BingX WS/REST (публичный)
        │
        ▼
[Data Collector] ──► [TF Aggregator] ──► [OB Processor]
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                      [Event Bus]
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
    [TA Engine]    [SmartMoney Engine]  [Volume Engine]
    [Correlation]  [ML Dataset Writer]  [Sentiment]
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                    [Signal Engine]
                    [MTF Confluence]
                            │
                    [Backtester] ◄──► [Strategy Builder]
                            │
                    [Execution Engine]
                    (приватный API-ключ)
                            │
                    [Health Monitor] + [Logger RU]
                            │
                         [UI]
                    [Event Bus Monitor]
                      [AI Advisor]
```

### Два сервера (опционально, но заложено в архитектуру)

```
Сервер A — сборщик (другой IP, VPS)    Сервер B — основной (десктоп)
──────────────────────────────────     ─────────────────────────────
Data Collector                         Analytics Core
TF Aggregator              ──sync──►   Signal Engine
OB Processor                           Execution Engine
ML Dataset Writer                      UI + AI Advisor
```

Сборщик работает 24/7. При запуске основного приложения — автоматическая синхронизация пропущенных данных.

---

## 5. Data Layer

### 5.1 Таймфреймы — стратегия агрегации

**С биржи получаем только:** `1m` (и `5m` как резервная проверка)

**Вычисляем локально из 1m-свечей:**

```
1m (с биржи)
 ├── 3m   = 3 × 1m
 ├── 5m   = 5 × 1m
 ├── 15m  = 15 × 1m
 ├── 30m  = 30 × 1m
 ├── 1h   = 60 × 1m
 ├── 2h   = 120 × 1m
 ├── 4h   = 240 × 1m
 ├── 6h   = 360 × 1m
 ├── 12h  = 720 × 1m
 ├── 1d   = 1440 × 1m
 ├── 1W   = 7 × 1d
 └── 1M   = 30 × 1d (календарный)
```

**Зачем это:** экономия rate-limit BingX, возможность строить нестандартные ТФ (2h, 3h), единый источник истины для всех таймфреймов.

**Модуль TF Aggregator** подписывается на событие `candle.1m.closed`, агрегирует свечи и публикует `candle.{tf}.closed` для каждого таймфрейма.

### 5.2 BingX Rate-Limit Guard

BingX ограничения (актуальны на 2024, проверять в docs):
- REST: 20 запросов/сек на IP
- WebSocket: до 30 подписок на соединение
- Переподключение: не чаще 1 раза в 5 сек

**Rate-Limit Guard реализует:**

```python
# Псевдокод структуры
class RateLimitGuard:
    # Приоритетная очередь запросов
    # HIGH: исполнение ордеров, аккаунт
    # MEDIUM: актуальные рыночные данные
    # LOW: исторические данные, синхронизация
    
    async def request(self, endpoint, priority=MEDIUM):
        # Ждёт своей очереди
        # Логирует все запросы
        # При 429 — экспоненциальный backoff
        # Статистика использования лимитов
```

**WebSocket стратегия:**
- Одно WS-соединение на пару (не переподключаться)
- Heartbeat каждые 30 сек (требование BingX)
- Авто-реконнект с экспоненциальным backoff при разрыве

### 5.3 Собираемые данные

| Тип данных | Источник | Частота | Публичный API |
|---|---|---|---|
| OHLCV 1m свечи | WS subscribe | Каждую минуту | ✅ |
| Order Book (20 уровней) | WS depth | ~100ms diff updates | ✅ |
| Последние сделки (trades) | WS trades | Реалтайм | ✅ |
| Open Interest | REST polling | Каждые 5 мин | ✅ |
| Funding Rate | REST polling | Каждые 8 часов | ✅ |
| Liquidations | WS (если доступно) | Реалтайм | ✅ |
| Fear & Greed Index | External API | 1 раз в час | ✅ |
| Новостной фон | External API | Каждые 15 мин | ✅ |
| Данные аккаунта | REST (приватный) | По запросу | ❌ (ключ) |

### 5.4 Валидация входящих данных

Каждый входящий пакет данных проходит валидацию:
- Проверка JSON-схемы (pydantic модели)
- Проверка временны́х меток (не старше N секунд)
- Проверка диапазонов значений (цена > 0, объём >= 0)
- При ошибке — событие `data.validation_error` в Event Bus, запись в лог

---

## 6. Storage

### 6.1 Структура базы данных

#### Таблица: `candles`
```sql
CREATE TABLE candles (
    id          INTEGER PRIMARY KEY,
    symbol      TEXT NOT NULL,        -- 'BTC/USDT'
    timeframe   TEXT NOT NULL,        -- '1m', '5m', '1h', ...
    open_time   INTEGER NOT NULL,     -- Unix timestamp ms
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      REAL NOT NULL,
    is_closed   BOOLEAN DEFAULT TRUE,
    source      TEXT DEFAULT 'exchange', -- 'exchange' | 'aggregated'
    created_at  INTEGER DEFAULT (strftime('%s','now')),
    UNIQUE(symbol, timeframe, open_time)
);
CREATE INDEX idx_candles_lookup ON candles(symbol, timeframe, open_time DESC);
```

#### Таблица: `orderbook_snapshots`
```sql
CREATE TABLE orderbook_snapshots (
    id          INTEGER PRIMARY KEY,
    symbol      TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,     -- Unix timestamp ms
    bids_top5   TEXT NOT NULL,        -- JSON: [[price, qty], ...]
    asks_top5   TEXT NOT NULL,        -- JSON: [[price, qty], ...]
    bid_volume  REAL,                 -- суммарный объём bid топ-20
    ask_volume  REAL,                 -- суммарный объём ask топ-20
    imbalance   REAL,                 -- (bid-ask)/(bid+ask)
    trigger     TEXT DEFAULT 'periodic' -- 'periodic'|'anomaly'|'pre_trade'
);
```

#### Таблица: `trades_raw`
```sql
CREATE TABLE trades_raw (
    id          INTEGER PRIMARY KEY,
    symbol      TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    price       REAL NOT NULL,
    quantity    REAL NOT NULL,
    side        TEXT NOT NULL,        -- 'buy' | 'sell'
    trade_id    TEXT UNIQUE
);
```

#### Таблица: `market_metrics`
```sql
CREATE TABLE market_metrics (
    id              INTEGER PRIMARY KEY,
    symbol          TEXT NOT NULL,
    timestamp       INTEGER NOT NULL,
    open_interest   REAL,
    funding_rate    REAL,
    long_short_ratio REAL,
    fear_greed_index INTEGER,
    UNIQUE(symbol, timestamp)
);
```

#### Таблица: `signals`
```sql
CREATE TABLE signals (
    id              INTEGER PRIMARY KEY,
    symbol          TEXT NOT NULL,
    timestamp       INTEGER NOT NULL,
    direction       TEXT NOT NULL,    -- 'long' | 'short' | 'exit'
    score           REAL NOT NULL,    -- 0-100
    timeframe       TEXT NOT NULL,    -- основной ТФ сигнала
    strategy_id     TEXT NOT NULL,
    indicators      TEXT,             -- JSON: детали индикаторов
    mtf_confirm     TEXT,             -- JSON: подтверждение по ТФ
    status          TEXT DEFAULT 'pending', -- pending|executed|expired|rejected
    created_at      INTEGER DEFAULT (strftime('%s','now'))
);
```

#### Таблица: `trades_journal`
```sql
CREATE TABLE trades_journal (
    id              INTEGER PRIMARY KEY,
    symbol          TEXT NOT NULL,
    mode            TEXT NOT NULL,    -- 'futures' | 'spot'
    direction       TEXT NOT NULL,    -- 'long' | 'short'
    entry_price     REAL NOT NULL,
    exit_price      REAL,
    quantity        REAL NOT NULL,
    leverage        INTEGER DEFAULT 1,
    sl_price        REAL,
    tp_price        REAL,
    pnl_usdt        REAL,
    pnl_percent     REAL,
    commission      REAL,
    entry_time      INTEGER NOT NULL,
    exit_time       INTEGER,
    signal_id       INTEGER REFERENCES signals(id),
    execution_mode  TEXT,             -- 'auto'|'semi'|'manual'
    notes           TEXT,
    tags            TEXT              -- JSON массив тегов
);
```

#### Таблица: `strategies`
```sql
CREATE TABLE strategies (
    id              TEXT PRIMARY KEY, -- 'rsi_ema_cross_v1'
    name            TEXT NOT NULL,
    description     TEXT,
    type            TEXT NOT NULL,    -- 'ta'|'smartmoney'|'volume'|'hybrid'|'ml'
    params          TEXT NOT NULL,    -- JSON: параметры стратегии
    is_active       BOOLEAN DEFAULT FALSE,
    is_demo         BOOLEAN DEFAULT FALSE,
    fingerprint     TEXT,             -- JSON: при каких условиях работает
    created_at      INTEGER,
    updated_at      INTEGER
);
```

#### Таблица: `backtest_results`
```sql
CREATE TABLE backtest_results (
    id              INTEGER PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    period_start    INTEGER NOT NULL,
    period_end      INTEGER NOT NULL,
    total_trades    INTEGER,
    win_rate        REAL,
    profit_factor   REAL,
    max_drawdown    REAL,
    total_pnl       REAL,
    sharpe_ratio    REAL,
    params_used     TEXT,             -- JSON
    created_at      INTEGER DEFAULT (strftime('%s','now'))
);
```

#### Таблица: `ml_dataset`
```sql
CREATE TABLE ml_dataset (
    id              INTEGER PRIMARY KEY,
    symbol          TEXT NOT NULL,
    timestamp       INTEGER NOT NULL,
    timeframe       TEXT NOT NULL,
    -- Ценовые фичи
    price_change_1  REAL,             -- изменение за 1 свечу
    price_change_5  REAL,
    price_change_20 REAL,
    volatility_20   REAL,
    -- TA фичи
    rsi_14          REAL,
    rsi_raw         REAL,             -- промежуточный RSI без сглаживания
    macd_line       REAL,
    macd_signal     REAL,
    macd_hist       REAL,
    bb_position     REAL,             -- позиция цены внутри BB (0-1)
    bb_width        REAL,
    ema_9           REAL,
    ema_21          REAL,
    ema_50          REAL,
    ema_200         REAL,
    -- Volume фичи
    volume_ratio    REAL,             -- объём / средний объём 20
    cvd             REAL,             -- cumulative volume delta
    oi_change       REAL,             -- изменение OI
    -- OB фичи
    ob_imbalance    REAL,             -- bid/ask ratio
    ob_bid_vol      REAL,
    ob_ask_vol      REAL,
    ob_spread       REAL,
    -- SmartMoney фичи
    has_fvg         BOOLEAN,
    has_bos         BOOLEAN,
    has_choch       BOOLEAN,
    near_ob         BOOLEAN,          -- цена у Order Block
    -- Контекст рынка
    market_regime   TEXT,             -- 'trend'|'range'|'volatile'
    fear_greed      INTEGER,
    btc_correlation REAL,             -- корреляция с BTC за последние N свечей
    -- Метки (заполняются постфактум)
    label_1         REAL,             -- изменение цены через 1 свечу
    label_5         REAL,             -- через 5 свечей
    label_20        REAL,             -- через 20 свечей
    label_direction TEXT,             -- 'up'|'down'|'flat' через 5 свечей
    UNIQUE(symbol, timestamp, timeframe)
);
```

#### Таблица: `anomalies`
```sql
CREATE TABLE anomalies (
    id              INTEGER PRIMARY KEY,
    symbol          TEXT NOT NULL,
    timestamp       INTEGER NOT NULL,
    type            TEXT NOT NULL,    -- 'price_spike'|'volume_spike'|'spoof'|'slippage'|'flash'
    severity        TEXT NOT NULL,    -- 'low'|'medium'|'high'|'critical'
    description     TEXT,
    data_snapshot   TEXT,             -- JSON: состояние рынка в момент аномалии
    resolved        BOOLEAN DEFAULT FALSE
);
```

#### Таблица: `market_snapshots`
```sql
-- Полный срез состояния рынка каждые N минут
-- Золото для отладки: можно "отмотать" систему назад
CREATE TABLE market_snapshots (
    id              INTEGER PRIMARY KEY,
    timestamp       INTEGER NOT NULL,
    symbol          TEXT NOT NULL,
    data            TEXT NOT NULL     -- JSON: цена, OB, индикаторы, активные сигналы
);
```

#### Таблица: `system_logs`
```sql
CREATE TABLE system_logs (
    id          INTEGER PRIMARY KEY,
    timestamp   INTEGER NOT NULL,
    level       TEXT NOT NULL,        -- 'DEBUG'|'INFO'|'WARNING'|'ERROR'|'CRITICAL'
    module      TEXT NOT NULL,
    message     TEXT NOT NULL,
    details     TEXT                  -- JSON: дополнительный контекст
);
```

---

## 7. Analytics Core

### 7.1 TA Engine — технический анализ

**Принцип:** Каждый индикатор — отдельная функция. Промежуточные значения тоже сохраняются и анализируются отдельно.

**Реализованные индикаторы:**

| Индикатор | Параметры | Промежуточные данные |
|---|---|---|
| RSI | period=14 (настраивается) | raw RSI, avg_gain, avg_loss |
| MACD | 12/26/9 (настраивается) | ema_fast, ema_slow до вычитания |
| EMA | 9, 21, 50, 200 | — |
| Bollinger Bands | 20/2.0 | средняя линия, верхняя, нижняя, ширина |
| ATR | 14 | true_range per candle |
| VWAP | сессионный | накопленный объём |
| Stochastic | 14/3/3 | %K, %D |
| Уровни | авто | поддержки, сопротивления, пивот-поинты |
| Паттерны свечей | — | молот, поглощение, доджи, пин-бар |

**Анализ промежуточных данных:** Каждое промежуточное значение (например, raw RSI без сглаживания, ema_fast до сигнальной линии MACD) записывается в `ml_dataset`. Если промежуточный показатель имеет предсказательную силу — он становится отдельным кандидатом для гибридной стратегии.

**Работа на всех ТФ одновременно:** TA Engine подписывается на `candle.{tf}.closed` для всех таймфреймов и всех пар. Результаты публикует как `ta.{symbol}.{tf}.updated`.

### 7.2 SmartMoney Engine

| Концепция | Описание | Событие |
|---|---|---|
| FVG (Fair Value Gap) | Имбаланс цены, неперекрытый гэп | `smc.fvg.detected` |
| BOS (Break of Structure) | Пробой структуры рынка | `smc.bos.detected` |
| CHoCH (Change of Character) | Смена характера движения | `smc.choch.detected` |
| Order Block | Зона накопления крупных ордеров | `smc.ob.identified` |
| Ликвидность | Зоны выше/ниже ключевых уровней | `smc.liquidity.mapped` |
| Premium/Discount | Положение цены в диапазоне | `smc.zone.updated` |

### 7.3 Volume Engine

| Показатель | Описание |
|---|---|
| CVD (Cumulative Volume Delta) | Накопленная разница buy/sell объёмов |
| OI (Open Interest) | Открытый интерес и его изменение |
| Volume Profile | Объём на уровнях цены (POC, VAH, VAL) |
| Funding Rate анализ | Экстремальные значения = сигнал разворота |
| Long/Short Ratio | Соотношение лонговых и шортовых позиций |
| Delta per candle | Объём buy - объём sell на каждой свече |

### 7.4 Correlation Engine

Отдельный модуль для анализа корреляций:

- Корреляция каждой пары с BTC и ETH (Pearson, скользящее окно)
- Корреляция между парами портфеля (матрица)
- Определение режима рынка: пара движется сама или следует за BTC
- Выявление расхождений (divergence): пара должна была пойти с BTC, но не пошла — торговая возможность

### 7.5 Sentiment Engine

- **Fear & Greed Index**: значение + история + интерпретация
- **Новостной фон**: NLP-тональность новостей по каждой паре (positive/negative/neutral)
- Всё это — фичи в `ml_dataset`, но также влияет на скоринг сигналов

### 7.6 MTF Confluence Engine

Ключевой модуль. Собирает сигналы от всех аналитических модулей по всем таймфреймам и вычисляет итоговый score.

**Логика скоринга (0–100):**

```
Базовый score = сумма весов подтверждений

Веса по таймфреймам:
  1m:  0.05    3m:  0.07    5m:  0.10
  15m: 0.12    30m: 0.13    1h:  0.15
  4h:  0.17    1d:  0.12    1W:  0.06    1M: 0.03

Множители:
  +15% если SmartMoney подтверждает
  +10% если Volume подтверждает (CVD + OI)
  +10% если OB imbalance в нужную сторону
  -20% если Fear&Greed экстремален против сигнала
  -30% если обнаружен spoof в стакане

Минимальный score для сигнала: 60
Минимальный для авто-исполнения: 80
```

---

## 8. Order Book Processor

Отдельный независимый модуль. Работает с реалтайм данными стакана.

### 8.1 Реконструкция стакана

BingX отдаёт снимок (snapshot) + инкрементальные обновления (diff). OB Processor:
1. Получает первый snapshot (20 уровней)
2. Применяет diff-обновления в реалтайм
3. Поддерживает локальную копию актуального стакана

### 8.2 Что анализируется

**Imbalance (дисбаланс bid/ask):**
```
imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
> +0.3  → давление покупателей
< -0.3  → давление продавцов
```

**Spoofing детектор:**
- Заявка размером > N×средний ордер появилась и исчезла за < 2 секунды без исполнения
- Событие: `ob.spoof_detected` с описанием
- Понижает score текущих сигналов

**Расчёт slippage перед входом:**
- Перед каждой сделкой система считает: при покупке X контрактов, сколько уровней стакана будет съедено?
- Если реальная цена исполнения отличается от текущей > порога — вход откладывается

**Стены ликвидности:**
- Уровни с аномально большим объёмом ордеров
- Сильные уровни поддержки/сопротивления по стакану

### 8.3 Хранение снимков

- **Периодически:** каждые 10 секунд — агрегированный снимок (топ-5 уровней + суммарные объёмы)
- **При аномалии:** полный снимок 20 уровней
- **Перед каждой сделкой:** полный снимок (привязан к `trades_journal`)

### 8.4 ML-фичи из стакана

15–20 признаков для `ml_dataset`: bid/ask ratio на разных глубинах, скорость изменения imbalance, наличие крупных заявок, spread, история изменений за последние N обновлений.

---

## 9. Signal Engine

### 9.1 Генерация сигналов

Signal Engine подписывается на результаты MTF Confluence и генерирует торговые сигналы:

```
Событие: signal.generated
Поля:
  - symbol: 'BTC/USDT'
  - direction: 'long' | 'short' | 'exit'
  - score: 87.3
  - timeframe: '1h'    # основной таймфрейм
  - strategy_id: 'smc_rsi_v2'
  - entry_price: 43210.5
  - sl_price: 42800.0   # рассчитывается автоматически
  - tp_levels: [43800, 44500, 45200]  # несколько уровней TP
  - indicators: {...}   # детали индикаторов
  - mtf_confirm: {...}  # подтверждения по таймфреймам
  - ob_snapshot: {...}  # состояние стакана
  - expires_at: timestamp
```

### 9.2 Аномалия-детектор

Мониторит поток данных и реагирует немедленно:

| Тип аномалии | Триггер | Действие |
|---|---|---|
| Price spike | Изменение цены > 2% за 1 минуту | `anomaly.price_spike` → проверить позиции |
| Volume spike | Объём > 5× средний | `anomaly.volume_spike` → усилить мониторинг |
| Flash crash | Цена упала > 3% за 30 сек | `anomaly.flash_crash` → приостановить исполнение |
| Slippage detected | Реальная цена сделки > расчётной на 0.5% | `anomaly.slippage` → запись в журнал |
| OB manipulation | Spoofing или резкое исчезновение ликвидности | `anomaly.ob_manip` → снизить score |

### 9.3 Качество сигнала

Каждый сигнал получает атрибуты качества:
- **Score (0–100):** итоговый скор MTF Confluence
- **Confidence:** насколько стратегия уверена (на основе бэктеста)
- **Risk/Reward:** соотношение потенциальной прибыли к убытку
- **Market regime fit:** насколько текущий режим рынка подходит этой стратегии

---

## 10. Backtester и Strategy Builder

### 10.1 Backtester

Движок бэктестинга на исторических данных из локальной БД.

**Параметры запуска:**
```
strategy_id: str
symbol: str
timeframe: str
period_start: datetime
period_end: datetime
initial_capital: float
leverage: int
commission: float  # % от объёма
slippage_model: 'fixed' | 'orderbook'  # фиксированный или по реальному стакану
```

**Метрики результата:**
- Total PnL (абсолютный и %)
- Win Rate
- Profit Factor
- Maximum Drawdown
- Sharpe Ratio
- Среднее время в сделке
- Лучшая и худшая сделка
- Количество сделок в месяц

### 10.2 Авто-оптимизация параметров

```
Цель: максимизировать PnL при drawdown < порога

Метод: Grid Search + Bayesian Optimization
Параметры: диапазоны для каждого параметра стратегии
Валидация: walk-forward (не переобучение на одном периоде)

Результат: лучший набор параметров + fingerprint стратегии
```

**Strategy Fingerprint** — профиль стратегии:
```json
{
  "best_market_regime": "trend",
  "best_timeframes": ["1h", "4h"],
  "best_volatility": "medium",
  "best_session": "london+ny_overlap",
  "avoid_when": ["high_fear_greed", "low_volume"]
}
```

### 10.3 Hybrid Strategy Builder

Система построения гибридных стратегий:

1. **Анализ промежуточных индикаторов** — тестируем каждый sub-индикатор отдельно как предсказатель
2. **Ранжирование по предсказательной силе** — статистическая значимость каждого компонента
3. **Конструктор комбо** — собираем стратегию из компонентов с лучшими показателями
4. **Совместимость fingerprint'ов** — гибрид строится не вслепую, а из стратегий с совместимыми условиями работы

**Пример гибрида:**
```
IF rsi_raw (промежуточный) > 75 
AND ob_imbalance < -0.3         # стакан давит вниз
AND smc.choch == True           # смена характера
AND btc_correlation > 0.8       # BTC подтверждает
THEN short, score = weighted_sum(...)
```

### 10.4 Demo Mode (Paper Trading)

- Работает на живых данных BingX (не исторических)
- Все сделки записываются как реальные (со всеми комиссиями, slippage)
- Статистика демо сравнивается с реальной торговлей
- Если расхождение демо/реал > 15% — предупреждение (проблема в модели исполнения)

---

## 11. Execution Engine

### 11.1 Три режима исполнения

Переключаются в интерфейсе без перезапуска системы:

**Auto mode:**
- Сигнал с score ≥ 80 исполняется автоматически
- Размер позиции рассчитывается по риск-менеджменту
- SL/TP выставляются автоматически
- Лог каждого действия

**Semi-auto mode:**
- Сигнал приходит → уведомление с деталями
- Пользователь нажимает "Подтвердить" или "Отклонить"
- Таймаут: если не ответил за N секунд → сигнал истекает
- После подтверждения — исполнение как в авто

**Alert only mode:**
- Только уведомление с деталями сигнала
- Пользователь торгует вручную на бирже
- Можно вручную зафиксировать сделку в журнале

### 11.2 Работа с API (приватный)

API-ключ BingX хранится только здесь. Изолированный модуль.

```
Поддерживаемые операции:
- Открытие позиции (market / limit)
- Выставление SL/TP ордеров
- Частичное закрытие позиции
- Полное закрытие позиции
- Получение статуса ордеров
- Получение данных аккаунта
```

### 11.3 Реакция на аномалии в реалтайм

Execution Engine подписывается на `anomaly.*` события:

- `anomaly.flash_crash` → немедленный стоп всех новых входов, проверка открытых позиций
- `anomaly.slippage` → запись в журнал, пересчёт slippage модели
- `anomaly.ob_manip` → задержка входа, ожидание стабилизации стакана

---

## 12. AI Advisor

### 12.1 Концепция

Встроенный AI-ассистент с полным доступом к внутреннему состоянию системы. Не просто чат — это агент с контекстом всей платформы.

### 12.2 Контекст, который получает AI

```python
context = {
    "system_health": health_monitor.get_all_statuses(),
    "recent_events": event_bus.get_last_n(100),
    "active_positions": execution.get_positions(),
    "pending_signals": signal_engine.get_queue(),
    "strategy_performance": backtester.get_recent_stats(),
    "anomalies_last_hour": anomaly_log.get_recent(),
    "error_logs": logger.get_errors_last_hour(),
    "market_snapshot": snapshot_service.get_latest(),
    "active_strategies": strategy_manager.get_active(),
}
```

### 12.3 Задачи AI Advisor

| Категория | Пример запроса | Что делает |
|---|---|---|
| Диагностика | "Почему Volume Engine лагает?" | Анализирует логи и события, предлагает решение |
| Объяснение сигнала | "Почему BTC получил score 87?" | Разбирает все компоненты сигнала |
| Анализ стратегии | "Почему winrate упал с 68% до 54%?" | Сравнивает периоды, ищет изменения |
| Рекомендация | "Какие параметры RSI лучше для SOL на 1h?" | Анализирует бэктест результаты |
| Рыночный контекст | "Как сейчас коррелируют наши пары?" | Читает correlation engine |
| Помощь с кодом | "Вот ошибка в модуле — исправь" | Видит логи и предлагает правку |
| Риски | "Оцени риски текущих открытых позиций" | Анализирует позиции + рыночный контекст |

### 12.4 Автоматические уведомления

AI Advisor активируется автоматически при:
- `health.module_error` — предлагает диагностику
- `strategy.winrate_drop` — анализирует причину
- `anomaly.critical` — объясняет что происходит
- Раз в день — краткий дайджест: статистика, аномалии, рекомендации

### 12.5 Интеграция

- Использует Anthropic API (claude-sonnet-4-20250514)
- Чат-интерфейс в отдельной панели UI
- История диалогов сохраняется в БД
- Язык: русский

---

## 13. Event Bus и мониторинг

### 13.1 Event Bus

Реализация на `asyncio.Queue` с pub/sub паттерном:

```python
# Пример топиков событий
TOPICS = {
    # Data
    "candle.{tf}.closed":     "Свеча закрыта на таймфрейме",
    "ob.updated":             "Обновление стакана",
    "data.validation_error":  "Ошибка валидации данных",
    
    # Analytics
    "ta.{symbol}.{tf}.updated":  "TA пересчитан",
    "smc.fvg.detected":          "Обнаружен FVG",
    "smc.bos.detected":          "Пробой структуры",
    
    # Signals
    "signal.generated":       "Новый сигнал",
    "signal.expired":         "Сигнал истёк",
    "signal.executed":        "Сигнал исполнен",
    
    # Execution
    "order.placed":           "Ордер выставлен",
    "order.filled":           "Ордер исполнен",
    "position.opened":        "Позиция открыта",
    "position.closed":        "Позиция закрыта",
    
    # Anomalies
    "anomaly.price_spike":    "Скачок цены",
    "anomaly.spoof_detected": "Обнаружен spoofing",
    "anomaly.flash_crash":    "Flash crash",
    
    # System
    "health.module_ok":       "Модуль работает нормально",
    "health.module_warning":  "Предупреждение модуля",
    "health.module_error":    "Ошибка модуля",
}
```

### 13.2 Event Bus Monitor UI

Встроенная вкладка в интерфейсе терминала:

**Верхняя панель:**
- Статус каждого модуля (зелёный/жёлтый/красный dot)
- Количество событий в минуту
- Суммарная латентность

**Живой поток событий:**
- Фильтрация по типу: DATA / SIGNAL / EXEC / SYS / ANOMALY
- Фильтрация по паре
- Поиск по содержимому
- Каждое событие: время, тип, payload, латентность обработки

**Детали модуля** (клик на модуль):
- Последние N событий этого модуля
- Статистика ошибок
- Кнопки: Перезапустить / Пауза / Детали

---

## 14. Health Monitor и логирование

### 14.1 Health Monitor

Каждый модуль регистрируется в Health Monitor и сообщает о своём состоянии:

```python
# Каждый модуль реализует:
class BaseModule:
    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            module_name="ta_engine",
            status="ok",          # ok | warning | error | stopped
            last_heartbeat=now(),
            metrics={
                "processed_events": 1240,
                "avg_latency_ms": 12,
                "errors_last_hour": 0,
            },
            message="Работает нормально"
        )
```

Health Monitor проверяет все модули каждые 30 секунд. Если модуль не ответил — `health.module_error`.

### 14.2 Логирование

**Принципы:**
- Все логи на **русском языке**
- Структурированный формат (loguru + JSON)
- Уровни: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Ротация: файлы по дням, хранение 30 дней
- Критические ошибки → дублируются в `system_logs` таблицу БД

**Формат лога:**
```
2026-04-17 14:23:41.821 | INFO | ta_engine | BTC/USDT 1h: RSI=67.3, MACD бычий, BB середина
2026-04-17 14:23:41.654 | WARNING | volume_engine | CVD расчёт задержан на 340ms (норма <100ms)
2026-04-17 14:23:38.002 | INFO | execution | Открыта позиция BTC/USDT Long 0.05 BTC @ 43210.5
```

**Что логируется обязательно:**
- Каждый запрос к BingX API (статус, время ответа)
- Каждый сгенерированный сигнал
- Каждое торговое действие (открытие, закрытие, изменение SL/TP)
- Все ошибки с полным traceback
- Старт/стоп каждого модуля
- Превышение лимитов BingX

---

## 15. UI

### 15.1 Вкладки интерфейса

**Dashboard:**
- Открытые позиции + нереализованный PnL
- Активные сигналы в очереди
- Статус системы (Health Monitor сводка)
- PnL за день/неделю/месяц

**Chart View:**
- Свечной график (TradingView Lightweight Charts)
- Переключение пар и таймфреймов
- Наложение индикаторов (EMA, BB, VWAP, уровни)
- Отображение сигналов на графике
- Order Book визуализация (глубина рынка)
- Тепловая карта ликвидности

**Trade Panel:**
- Быстрое открытие позиции (размер, плечо, SL/TP)
- Калькулятор размера позиции по риску (%)
- Список открытых ордеров

**Strategy Lab:**
- Список стратегий + их статистика
- Запуск бэктеста
- Результаты оптимизации
- Hybrid Builder интерфейс

**Analytics:**
- Trade Journal с фильтрацией
- PnL-кривая
- Статистика по стратегиям, парам, сессиям
- Анализ ошибок и аномалий

**Event Bus Monitor:**
- Живой поток событий (см. раздел 13.2)

**AI Advisor:**
- Чат-интерфейс
- История диалогов
- Контекстные уведомления

### 15.2 Desktop → Web переход

При переходе на Web (Phase 2):
- Python бэкенд остаётся без изменений
- Electron заменяется на React-приложение в браузере
- Тот же WebSocket протокол для реалтайм данных
- Добавляется аутентификация пользователей

---

## 16. Risk Management

### 16.1 Параметры (настраиваются)

```
max_risk_per_trade: 1-2% от депозита
max_open_positions: 3-5
max_daily_drawdown: 5%
max_total_drawdown: 15%
default_leverage: 5-10x (зависит от стратегии)
min_risk_reward: 1.5
```

### 16.2 Расчёт размера позиции

```
risk_amount = deposit * max_risk_per_trade / 100
position_size = risk_amount / (entry_price - sl_price)
```

### 16.3 Автоматические защиты

- Если daily drawdown > лимита → стоп всех новых входов до следующего дня
- Если total drawdown > лимита → перевод в Alert-only режим, уведомление
- Проверка slippage перед каждым входом
- Ограничение одной позиции на пару одновременно

---

## 17. Фазы разработки

### Phase 1-A: Фундамент (Недели 1-3)

**Цель:** Система собирает данные непрерывно, всё остальное строится на этом.

- [ ] Настройка проекта (структура, venv, .env, git)
- [ ] Event Bus базовая реализация
- [ ] Health Monitor базовая реализация
- [ ] Logger RU настройка
- [ ] BingX REST клиент с Rate-Limit Guard
- [ ] BingX WebSocket клиент (1m свечи, топ-5 пар)
- [ ] Валидация входящих данных
- [ ] Storage: SQLite, таблицы candles, system_logs
- [ ] TF Aggregator (1m → все ТФ)
- [ ] Первый коммит: `[FOUNDATION] Базовая инфраструктура и сборщик данных`

### Phase 1-B: Order Book (Недели 4-5)

- [ ] WebSocket подписка на стакан
- [ ] OB Processor (реконструкция, diff updates)
- [ ] Imbalance расчёт
- [ ] Spoofing детектор
- [ ] Snapshot storage
- [ ] ML-фичи из стакана → ml_dataset
- [ ] Коммит: `[OB] Обработчик стакана и детектор манипуляций`

### Phase 1-C: Analytics Core (Недели 6-8)

- [ ] TA Engine (RSI, MACD, EMA, BB, ATR, уровни)
- [ ] Промежуточные данные индикаторов в ml_dataset
- [ ] SmartMoney Engine (FVG, BOS, CHoCH, OB)
- [ ] Volume Engine (CVD, OI, delta)
- [ ] Correlation Engine
- [ ] MTF Confluence Engine + скоринг
- [ ] Коммит: `[ANALYTICS] TA + SmartMoney + Volume + MTF Confluence`

### Phase 1-D: Backtester (Недели 9-11)

- [ ] Backtester движок на исторических данных
- [ ] Метрики: PnL, winrate, drawdown, Sharpe
- [ ] Strategy Builder базовый
- [ ] Авто-оптимизация параметров (Grid Search)
- [ ] Strategy Fingerprint
- [ ] Demo mode (paper trading на живых данных)
- [ ] Коммит: `[BACKTESTER] Движок тестирования и оптимизации стратегий`

### Phase 1-E: Signal + Execution (Недели 12-14)

- [ ] Signal Engine + аномалия-детектор
- [ ] Risk Guard (размер позиции, лимиты)
- [ ] Execution Engine: Semi-auto режим (первый запуск)
- [ ] Execution Engine: Auto режим
- [ ] Execution Engine: Alert-only режим
- [ ] Реакция на аномалии в реалтайм
- [ ] Коммит: `[EXECUTION] Движок исполнения, три режима, риск-менеджмент`

### Phase 1-F: UI (Параллельно с 1-C, 1-D, 1-E)

- [ ] Electron + React + TypeScript проект
- [ ] WebSocket сервер на Python стороне
- [ ] Dashboard
- [ ] Chart View (TradingView Lightweight Charts)
- [ ] Event Bus Monitor
- [ ] Trade Panel
- [ ] Analytics вкладка
- [ ] Коммит: `[UI] Desktop интерфейс: Dashboard, Charts, Event Bus Monitor`

### Phase 1-G: AI Advisor + ML Dataset (Недели 15-16)

- [ ] AI Advisor: интеграция Anthropic API
- [ ] Контекст системы → AI
- [ ] Чат-интерфейс в UI
- [ ] Проверка полноты ml_dataset (все фичи собираются)
- [ ] Hybrid Strategy Builder (анализ промежуточных индикаторов)
- [ ] Коммит: `[AI] AI Advisor и гибридный конструктор стратегий`

### Phase 2: Web + SaaS (будущее)

- [ ] React web-приложение (замена Electron)
- [ ] Аутентификация пользователей
- [ ] PostgreSQL + TimescaleDB (замена SQLite)
- [ ] ML-модели на накопленных данных
- [ ] Мультибиржевая поддержка

---

## 18. Структура проекта

```
crypto-terminal/
├── .env                        # Секреты (в .gitignore)
├── .env.example                # Шаблон (в git)
├── .gitignore
├── README.md                   # RU + EN описание
├── ARCHITECTURE.md             # Актуальная архитектура
├── CHANGELOG.md                # История версий
├── requirements.txt
├── pyproject.toml
│
├── core/                       # Ядро системы
│   ├── event_bus.py            # Шина событий
│   ├── health_monitor.py       # Мониторинг модулей
│   ├── base_module.py          # Базовый класс модуля
│   └── logger.py               # Настройка loguru
│
├── data/                       # Сбор данных
│   ├── bingx_rest.py           # REST клиент
│   ├── bingx_ws.py             # WebSocket клиент
│   ├── rate_limit_guard.py     # Rate-limit управление
│   ├── tf_aggregator.py        # Агрегация таймфреймов
│   ├── ob_processor.py         # Order Book обработчик
│   ├── external_feeds.py       # Fear/Greed, новости
│   └── validator.py            # Валидация данных
│
├── storage/                    # Хранение данных
│   ├── database.py             # SQLAlchemy настройка
│   ├── models.py               # ORM модели таблиц
│   ├── repositories/           # Репозитории по таблицам
│   │   ├── candles_repo.py
│   │   ├── signals_repo.py
│   │   ├── trades_repo.py
│   │   └── ml_dataset_repo.py
│   └── migrations/             # Alembic миграции
│
├── analytics/                  # Аналитическое ядро
│   ├── ta_engine.py            # Технический анализ
│   ├── smartmoney.py           # SmartMoney концепции
│   ├── volume_engine.py        # Объёмный анализ
│   ├── correlation.py          # Корреляционный анализ
│   ├── sentiment.py            # Сентимент рынка
│   └── mtf_confluence.py       # MTF скоринг
│
├── signals/                    # Сигнальная система
│   ├── signal_engine.py        # Генератор сигналов
│   ├── anomaly_detector.py     # Детектор аномалий
│   └── risk_guard.py           # Риск-менеджмент
│
├── strategies/                 # Стратегии
│   ├── base_strategy.py        # Базовый класс
│   ├── ta_strategies/          # TA-стратегии
│   ├── smc_strategies/         # SmartMoney стратегии
│   ├── hybrid_builder.py       # Гибридный конструктор
│   └── configs/                # JSON конфиги стратегий
│
├── backtester/                 # Бэктестинг
│   ├── engine.py               # Движок бэктеста
│   ├── optimizer.py            # Авто-оптимизация
│   ├── metrics.py              # Расчёт метрик
│   └── paper_trading.py        # Demo режим
│
├── execution/                  # Исполнение
│   ├── execution_engine.py     # Главный модуль
│   ├── order_manager.py        # Управление ордерами
│   └── bingx_private.py        # Приватный API (с ключом)
│
├── ml/                         # Машинное обучение
│   ├── dataset_writer.py       # Запись фичей
│   ├── feature_engineering.py  # Инженерия признаков
│   └── models/                 # ML модели (Phase 2)
│
├── ai_advisor/                 # AI Ассистент
│   ├── advisor.py              # Основная логика
│   ├── context_builder.py      # Сборка контекста
│   └── prompts.py              # Системные промпты
│
├── ui/                         # Frontend
│   ├── electron/               # Electron оболочка
│   └── react-app/              # React приложение
│       ├── src/
│       │   ├── components/
│       │   │   ├── Dashboard/
│       │   │   ├── ChartView/
│       │   │   ├── EventBusMonitor/
│       │   │   ├── TradingPanel/
│       │   │   ├── Analytics/
│       │   │   └── AIAdvisor/
│       │   └── hooks/
│       └── package.json
│
├── tests/                      # Тесты
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── docs/                       # Документация
│   ├── modules/                # По каждому модулю
│   ├── api/                    # BingX API заметки
│   └── strategies/             # Описание стратегий
│
├── scripts/                    # Утилиты
│   ├── init_db.py              # Инициализация БД
│   ├── sync_history.py         # Загрузка исторических данных
│   └── health_check.py         # Проверка системы
│
└── main.py                     # Точка входа
```

---

## 19. Глоссарий

| Термин | Расшифровка |
|---|---|
| BOS | Break of Structure — пробой рыночной структуры |
| CHoCH | Change of Character — смена характера движения |
| CVD | Cumulative Volume Delta — накопленная дельта объёма |
| FVG | Fair Value Gap — гэп справедливой стоимости |
| MTF | Multi TimeFrame — мультитаймфреймный анализ |
| OB | Order Block — блок ордеров (SmartMoney) |
| OI | Open Interest — открытый интерес |
| SMC | Smart Money Concepts — концепции умных денег |
| ТА | Технический Анализ |
| ТФ | Таймфрейм |
| PnL | Profit and Loss — прибыль и убыток |
| SL | Stop Loss — стоп-лосс |
| TP | Take Profit — тейк-профит |
| Spoof | Spoofing — манипуляция фиктивными ордерами |
| Slippage | Проскальзывание — разница расчётной и реальной цены |
| Fingerprint | Профиль условий работы стратегии |
| Event Bus | Шина событий — центральный канал межмодульного общения |
| Rate-limit | Ограничение количества запросов к API |
| Drawdown | Просадка — снижение капитала от максимума |
| Sharpe Ratio | Коэффициент Шарпа — доходность с учётом риска |
| Walk-forward | Метод валидации на скользящем временном окне |

---

*Документ создан: апрель 2026*  
*Следующее обновление: после завершения Phase 1-A*


---

## Дополнение к разделу 3: Журнал разработки (DEVLOG.md)

### Назначение

`DEVLOG.md` — живой журнал разработки. Ведётся параллельно с git-коммитами.  
Разница: коммит фиксирует **код**, журнал фиксирует **решения и контекст**.

### Когда писать запись

- После каждой рабочей сессии (даже если нет коммита)
- После принятия архитектурного решения
- При откладывании задачи — обязательно писать **почему**
- При обнаружении проблемы — что нашли, как решили

### Правила

- Двуязычно: **RU** + **EN** в каждой записи
- Кратко: 5–15 строк, без воды
- Обязательные поля: дата, что сделано, хэш коммита (или `—`), следующий шаг
- Файл хранится в корне репозитория рядом с README.md

### Как использовать с Claude Code

В начале новой сессии разработки говори:  
*«Прочитай DEVLOG.md и PRD.md. Продолжаем с того места где остановились.»*

Claude Code восстановит контекст и не будет переспрашивать о принятых решениях.

---

## Раздел 20: Тестирование компонентов

### 20.1 Принцип

Каждый модуль тестируется **до** того как на него начинают полагаться другие модули.  
Нет зелёных тестов — модуль не считается завершённым, даже если код написан.

### 20.2 Три уровня тестов

**Уровень 1 — Юнит-тесты (Unit tests)**  
Тестируем каждую функцию изолированно. Внешние зависимости (БД, API) заменяются моками.

```
Где: tests/unit/
Когда: пишется одновременно с кодом функции
Запуск: pytest tests/unit/ -v
Покрытие: минимум 80% для каждого модуля
```

Примеры:
- `test_tf_aggregator.py` — правильно ли агрегируются 1m свечи в 1h?
- `test_rate_limit_guard.py` — соблюдается ли очередь при превышении лимита?
- `test_ob_imbalance.py` — правильно ли считается дисбаланс стакана?
- `test_rsi_calculation.py` — совпадает ли RSI с эталонным значением?

**Уровень 2 — Интеграционные тесты (Integration tests)**  
Тестируем взаимодействие модулей через Event Bus. Реальная БД (тестовая), без внешних API.

```
Где: tests/integration/
Когда: после завершения группы связанных модулей
Запуск: pytest tests/integration/ -v
```

Примеры:
- `test_data_to_storage.py` — данные от коллектора доходят до БД корректно?
- `test_candle_triggers_ta.py` — закрытая свеча запускает пересчёт TA?
- `test_signal_flow.py` — сигнал проходит от MTF Confluence до Signal Engine?

**Уровень 3 — Smoke-тесты на живых данных**  
Быстрая проверка что система поднимается и получает реальные данные. Без торговли.

```
Где: tests/smoke/
Когда: перед каждым коммитом фазы
Запуск: python scripts/smoke_test.py --duration 60
```

Что проверяется за 60 секунд:
- WebSocket подключился и получил хотя бы одну свечу
- Rate-limit guard не выдал ошибок
- Все модули отрапортовали health_check = ok
- Event Bus доставил события без потерь
- БД записала данные корректно

### 20.3 Тестовые данные (Fixtures)

```
tests/fixtures/
├── candles_btc_1m_100.json     — 100 реальных 1m свечей BTC
├── orderbook_snapshot.json     — снимок стакана
├── ta_expected_values.json     — эталонные значения индикаторов
└── bingx_ws_messages.json      — записанные WS-сообщения для replay
```

Фикстуры записываются один раз с реального API и используются в тестах вместо живого подключения.

### 20.4 Чеклист готовности модуля

Модуль считается **завершённым и готовым к интеграции** только если:

- [ ] Юнит-тесты написаны и зелёные (`pytest tests/unit/test_{module}.py`)
- [ ] Покрытие кода ≥ 80% (`pytest --cov`)
- [ ] Интеграционный тест с Event Bus пройден
- [ ] Smoke-тест на живых данных пройден (60 сек без ошибок)
- [ ] Health check возвращает `status: ok`
- [ ] Логи читаемы и информативны (проверить вручную)
- [ ] Запись в DEVLOG.md добавлена

### 20.5 Инструменты

```python
# requirements-dev.txt
pytest>=7.4
pytest-asyncio>=0.23      # тесты async функций
pytest-cov>=4.1           # покрытие кода
pytest-mock>=3.12         # моки и патчи
freezegun>=1.4            # заморозка времени в тестах
respx>=0.20               # мок HTTP-запросов (aiohttp)
```

### 20.6 Запуск тестов — команды

```bash
# Все юнит-тесты
pytest tests/unit/ -v

# Конкретный модуль
pytest tests/unit/test_tf_aggregator.py -v

# С покрытием
pytest tests/unit/ --cov=core --cov-report=term-missing

# Интеграционные
pytest tests/integration/ -v

# Smoke (живые данные, 60 сек)
python scripts/smoke_test.py --duration 60

# Всё сразу перед коммитом
pytest tests/unit/ tests/integration/ -v && python scripts/smoke_test.py
```

### 20.7 Тесты по фазам разработки

| Фаза | Что тестируем | Тип |
|---|---|---|
| 1-A | Event Bus, Rate-limit Guard, TF Aggregator, валидация | Unit + Integration |
| 1-B | OB Processor, imbalance, spoofing детектор | Unit + Integration |
| 1-C | Каждый индикатор по эталонным значениям, MTF скоринг | Unit + Integration |
| 1-D | Backtester на исторических данных, метрики | Unit + Integration |
| 1-E | Execution в demo-режиме (без реальных денег) | Integration + Smoke |
| 1-F | WebSocket сервер UI, доставка событий в интерфейс | Integration |
| Каждая | Smoke-тест 60 сек на живых данных | Smoke |
