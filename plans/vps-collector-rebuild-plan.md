# План: Перестройка VPS-сборщика

**Дата:** 2026-05-01  
**Основание:** БД повреждена, требуется пересборка с нуля с учётом нового понимания API BingX  
**Цель:** VPS — только надёжный сборщик данных + API для Desktop. Вся агрегация и аналитика — на Desktop.

---

## 1. 🎯 Философия

```
┌─────────────────────────────────────────────────────────┐
│  VPS (сборщик 24/7)                                      │
│  ┌──────────────────┐  ┌──────────────────────────────┐  │
│  │ BingX WS (spot)   │  │ BingX REST (история)         │  │
│  │ BingX WS (futures)│  │  - klines v3 (516д)          │  │
│  │                   │  │  - OI (текущий)              │  │
│  │ → свечи 1m raw    │  │  - funding rate (4 посл.)    │  │
│  │ → orderbook snap  │  │  - force orders (ликвидации) │  │
│  │ → trades raw      │  └──────────────────────────────┘  │
│  └──────────────────┘                                     │
│         ↓ сохраняет в БД                                   │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  SQLite: candles (только 1m spot + 1m futures)        │ │
│  │          orderbook_snapshots (spot + futures)          │ │
│  │          trade_raw (spot + futures)                    │ │
│  │          liquidations                                  │ │
│  │          futures_metrics (OI, funding)                 │ │
│  └──────────────────────────────────────────────────────┘ │
│         ↓ отдаёт через                                    │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  FastAPI :8800                                        │ │
│  │  - WS /ws — реалтайм события                          │ │
│  │  - REST /api/* — история + управление                 │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
         │ WS + REST (X-API-Key)
         ▼
┌─────────────────────────────────────────────────────────┐
│  Desktop (терминал)                                      │
│  - VPS Client (data/vps_client.py)                       │
│  - Агрегация 1m → 5m, 15m, 1h, 4h, 1d, 1W (локально)   │
│  - Analytics (TA, SMC, Volume, Correlation, MTF)         │
│  - Signals + Execution + Backtester + UI                 │
│  - BingX Private API (только ордера)                     │
└─────────────────────────────────────────────────────────┘
```

### Ключевые принципы

1. **VPS собирает ТОЛЬКО 1m сырые данные** — никакой агрегации на VPS
2. **VPS хранит только то, что нельзя восстановить** — свечи 1m, стакан, сделки, ликвидации
3. **Desktop агрегирует всё сам** — 5m, 15m, 1h, 4h, 1d, 1W из 1m
4. **Desktop — единственный источник истины для аналитики**
5. **VPS — dumb pipe**: собирает → сохраняет → отдаёт. Без логики.

---

## 2. 📊 Какие данные собираем на VPS

### 2.1 Через WebSocket (реалтайм, 24/7)

| Данные | Канал | Сохраняется в | Приоритет |
|--------|-------|---------------|-----------|
| Свечи 1m spot | `{symbol}@kline_1min` (WS spot) | `candles` (market_type='spot') | 🔴 High |
| Свечи 1m futures | `{symbol}@kline_1min` (WS futures) | `candles` (market_type='futures') | 🔴 High |
| Order book spot | `{symbol}@depth20` (WS spot) | `orderbook_snapshots` | 🟡 Medium |
| Order book futures | `{symbol}@depth20` (WS futures) | `orderbook_snapshots` | 🟡 Medium |
| Trades spot | `{symbol}@trade` (WS spot) | `trade_raw` | 🟡 Medium |
| Trades futures | `{symbol}@trade` (WS futures) | `trade_raw` | 🟡 Medium |

### 2.2 Через REST polling (периодически)

| Данные | Endpoint | Частота | Сохраняется в |
|--------|----------|---------|---------------|
| Open Interest | `/openApi/swap/v2/quote/openInterest` | Каждые 60с | `futures_metrics` |
| Funding Rate | `/openApi/swap/v2/quote/fundingRate` | Каждые 60с | `futures_metrics` |
| Ликвидации | `/openApi/swap/v2/trade/forceOrders` | Каждые 60с | `liquidations` |

### 2.3 Через REST backfill (однократно, при старте)

| Данные | Endpoint | Глубина |
|--------|----------|---------|
| Свечи 1m futures | v3 `/quote/klines` | **~516 дней** (с 2024-11-30) |
| Свечи 1m spot | v3 `/quote/klines` | **~424 дня** (с 2025-03-03) |
| Ликвидации | v2 `/trade/forceOrders` | Неизвестно (проверить) |

### 2.4 Что НЕ собираем на VPS (агрегируется на Desktop)

| Данные | Почему не на VPS |
|--------|------------------|
| 5m, 15m, 1h, 4h свечи | Агрегируются из 1m на Desktop |
| 1d, 1W свечи | Агрегируются из 1m на Desktop |
| Basis | Вычисляется из spot + futures свечей на Desktop |
| CVD | Вычисляется из trades на Desktop |
| Индикаторы | Вся аналитика на Desktop |

---

## 3. 🏗️ Архитектура VPS-сборщика

### 3.1 Компоненты

```
VPS Collector (main.py — RUN_MODE=collector)
├── Data Layer (24/7)
│   ├── BingXWebSocket (spot)      — свечи, стакан, сделки
│   ├── BingXFuturesWebSocket      — свечи, стакан, сделки
│   ├── BingXRestClient            — OI, Funding, Liquidations (polling)
│   └── RateLimitGuard             — защита от rate limit
│
├── Storage (SQLite)
│   ├── CandlesRepository          — запись свечей
│   ├── OrderBookRepository        — запись стакана
│   └── TasksRepository            — статус задач
│
├── Telemetry API (FastAPI :8800)
│   ├── WS /ws                     — реалтайм события → Desktop
│   ├── GET /api/candles           — история свечей
│   ├── GET /api/status            — состояние системы
│   ├── GET /api/health            — здоровье (CPU/RAM/диск)
│   ├── GET /api/symbols           — список пар
│   ├── POST /api/symbols/add      — добавить пару
│   ├── POST /api/symbols/remove   — удалить пару
│   ├── POST /api/backfill         — запуск backfill
│   ├── POST /api/validate         — запуск валидации
│   ├── POST /api/restart          — перезапуск модуля/сервера
│   ├── GET /api/data/stats        — статистика БД
│   ├── GET /api/data/gaps         — пропуски в данных
│   └── GET /api/logs              — стриминг логов
│
├── Telegram
│   ├── TelegramBot (tg_bot.py)    — команды /summary, /status, /health
│   ├── TelegramNotifier           — алёрты об ошибках
│   └── Watchdog (watchdog.py)     — ежедневный дайджест
│
└── Backfill Engine
    ├── auto_backfill()            — при старте: загрузка пропущенного
    ├── manual_backfill()          — по запросу Desktop (POST /api/backfill)
    └── repair_integrity()         — проверка целостности БД
```

### 3.2 Desktop-терминал

```
Desktop Terminal (main.py — RUN_MODE=terminal)
├── VPS Client (data/vps_client.py)
│   ├── WS → VPS :8800 (реалтайм события)
│   └── REST → VPS :8800 (история + управление)
│
├── Локальная агрегация
│   ├── TFAggregator — 1m → 5m, 15m, 1h, 4h, 1d, 1W
│   └── BasisCalculator — spot + futures → basis
│
├── Analytics
│   ├── TAEngine, SmartMoney, VolumeEngine
│   ├── CorrelationEngine, MTFConfluenceEngine
│   └── AnomalyDetector
│
├── Signals + Execution
│   ├── SignalEngine, ExecutionEngine
│   ├── RiskGuard, BingXPrivateClient
│   └── Backtester + Strategies
│
└── UI (React + WSServer :8765)
    ├── Dashboard, ChartView, PulseView
    ├── VpsSettingsModal (настройки подключения)
    └── TaskQueuePanel (управление backfill)
```

---

## 4. 🔄 Протокол VPS → Desktop

### 4.1 Реалтайм (WebSocket `/ws`)

VPS транслирует события своего Event Bus:

| Событие | Описание |
|---------|----------|
| `candle.1m.tick` | Новая свеча 1m spot (незакрытая) |
| `candle.1m.closed` | Закрытая свеча 1m spot |
| `futures.candle.1m.closed` | Закрытая свеча 1m futures |
| `orderbook.update` | Обновление стакана spot |
| `futures.orderbook.update` | Обновление стакана futures |
| `trade.raw` | Новая сделка spot |
| `futures.trade.raw` | Новая сделка futures |
| `futures.liquidation` | Ликвидация |
| `futures.basis.updated` | Базис (если считается на VPS) |
| `watchdog.*` | Статус WS-соединений |
| `backfill.progress` | Прогресс backfill |
| `backfill.complete` | Backfill завершён |
| `backfill.error` | Ошибка backfill |
| `validation.result` | Результат валидации |
| `heartbeat` | CPU/RAM/uptime (каждые 5с) |
| `error` | Критическая ошибка на VPS |

### 4.2 История (REST API)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `GET /api/candles?symbol=X&tf=1m&limit=N&market_type=spot` | GET | Свечи из БД VPS |
| `GET /api/status` | GET | Состояние: CPU, RAM, диск, uptime, модули |
| `GET /api/health` | GET | Здоровье системы |
| `GET /api/symbols` | GET | Список пар |
| `GET /api/data/stats` | GET | Статистика по таблицам БД |
| `GET /api/data/gaps` | GET | Пропуски в данных |
| `GET /api/logs` | GET | Стриминг логов (SSE) |
| `POST /api/symbols/add` | POST | Добавить пару |
| `POST /api/symbols/remove` | POST | Удалить пару |
| `POST /api/backfill` | POST | Запустить backfill |
| `POST /api/validate` | POST | Запустить валидацию |
| `POST /api/restart/{module}` | POST | Перезапустить модуль |
| `POST /api/restart/server` | POST | Перезапустить VPS |

### 4.3 Telegram-команды (бот)

Бот работает на VPS через `telemetry/tg_bot.py` (long polling, интервал 5с).

| Команда | Описание | Пример вывода |
|---------|----------|---------------|
| `/summary` | **Детальная сводка** — БД, свечи spot/futures, стаканы, ликвидации, OI, funding rate, trust score по парам | См. ниже |
| `/status` | **Статус сервисов** — collector, WS spot, WS futures, watchdog, uptime | `✅ Collector: active (2ч 15м)` |
| `/health` | **Здоровье системы** — CPU, RAM, диск, нагрузка | `🟢 CPU: 23% | RAM: 340/1024 MB | Диск: 45%` |
| `/symbols` | **Список пар** — trust score, последняя свеча, кол-во данных | `🟢 BTC/USDT: trust 99% | посл: 2026-05-01` |
| `/backfill` | **Статус backfill** — текущие задачи, прогресс, ошибки | `📥 Backfill: BTC 45% | ETH 100% ✅ | SOL ошибка ❌` |
| `/errors` | **Последние ошибки** — 5 последних ошибок из лога | `⚠️ 12:30 WS reconnect | 11:15 Backfill error ...` |
| `/help` | **Справка** | Список всех команд |

#### Пример вывода `/summary`:

```
📊 СВОДКА VPS — 2026-05-01 16:00 UTC
━━━━━━━━━━━━━━━━━━━━━━
💾 БД: 2.3 GB
🕯 Свечи: 4,521,340
   ├── spot 1m:  2,104,500 (424 дн)
   └── futures 1m: 2,416,840 (516 дн)
📖 Стаканы: 892,450
   ├── spot:    446,200
   └── futures: 446,250
💥 Ликвидации (24ч): 47
📊 OI (текущий): $12.4B
💰 Funding Rate: 0.0012%
━━━━━━━━━━━━━━━━━━━━━━
📈 По парам:
🟢 BTC: свечей 904k | стаканов 178k | ликв 12 | trust 99%
🟢 ETH: свечей 904k | стаканов 178k | ликв 8 | trust 99%
🟡 SOL: свечей 900k | стаканов 178k | ликв 15 | trust 95%
🟢 BNB: свечей 904k | стаканов 178k | ликв 5 | trust 99%
🟢 XRP: свечей 904k | стаканов 178k | ликв 7 | trust 99%
━━━━━━━━━━━━━━━━━━━━━━
🔌 Соединения:
✅ WS Spot:  Норма (0 ошибок)
✅ WS Futures: Норма (0 ошибок)
✅ REST:     Норма
━━━━━━━━━━━━━━━━━━━━━━
⏰ 2026-05-01 16:00 UTC
```

### 4.4 Уведомления об ошибках

| Канал | Что отправляет | Пример |
|-------|---------------|--------|
| **Telegram** | Watchdog VPS | "WS disconnected", "Backfill error", "Disk space low" |
| **Desktop WS** | Event Bus VPS | Те же события + "error" |
| **Desktop REST** | Polling Desktop | Desktop опрашивает `/api/status` каждые 5с |

---

## 5. 📋 Пошаговый план реализации

### Фаза 0: Подготовка (сейчас)

- [x] Исследована глубина API BingX
- [x] Создана документация API
- [x] Созданы скрипты backfill (`backfill_futures_deep.py`, `aggregate_timeframes.py`)
- [x] Созданы скрипты проверки БД (`check_tables.py`, `check_db_stats.py`)

### Фаза 1: Очистка БД на VPS

- [ ] Подключиться к VPS по SSH
- [ ] Остановить collector: `systemctl stop crypto-telemetry`
- [ ] Сделать backup старой БД: `cp /opt/collector/data/terminal.db /opt/collector/data/terminal.db.bak`
- [ ] Удалить повреждённые таблицы: `DROP TABLE candles; DROP TABLE orderbook_snapshots;`
- [ ] Пересоздать таблицы: `python -c "from storage.database import init_db; import asyncio; asyncio.run(init_db())"`
- [ ] Проверить: `python scripts/check_tables.py`

### Фаза 2: Backfill данных

- [ ] **Futures 1m** (516 дней): `python scripts/backfill_futures_deep.py`
  - 5 символов × ~516 дней = ~2.5M свечей
  - Время: ~5 минут
- [ ] **Spot 1m** (424 дня): `python scripts/clean_backfill.py`
  - 5 символов × ~424 дня = ~2M свечей
  - Время: ~4 минуты
- [ ] **Проверка**: `python scripts/check_db_stats.py`

### Фаза 3: Запуск collector

- [ ] Запустить collector: `systemctl start crypto-telemetry`
- [ ] Проверить логи: `journalctl -u crypto-telemetry -n 50`
- [ ] Проверить WS-подключения: `curl http://localhost:8800/status`
- [ ] Убедиться, что свечи пишутся в реальном времени

### Фаза 4: Доработка API VPS (если нужно)

- [ ] Проверить все REST endpoint'ы в `telemetry/server.py`
- [ ] Добавить недостающие: `/api/validate`, `/api/restart/server`
- [ ] Убедиться, что `/api/candles` возвращает данные корректно
- [ ] Проверить WS трансляцию событий

### Фаза 5: Desktop — агрегация

- [ ] Настроить локальный `TFAggregator` на Desktop для агрегации 1m → старшие ТФ
- [ ] Проверить, что `VPSClient` корректно получает данные
- [ ] Проверить ChartView — отображение свечей с VPS

### Фаза 6: Мониторинг

- [ ] Убедиться, что Telegram-уведомления работают
- [ ] Проверить watchdog (ежедневный дайджест)
- [ ] Проверить авто-восстановление при перезапуске VPS

---

## 6. 🚨 Обработка ошибок

| Сценарий | Действие VPS | Действие Desktop |
|----------|-------------|------------------|
| WS disconnect (BingX) | Авто-реконнект, лог, Telegram | Получает `watchdog.lost` → показывает статус |
| REST ошибка | Retry x3, лог | N/A |
| БД повреждена | `repair_integrity()` → Telegram | Получает `error` → уведомление |
| Backfill ошибка | Retry x3, Telegram `backfill.error` | Получает `backfill.error` → уведомление |
| VPS перезагрузка | Авто-старт через systemd | Desktop в цикле реконнекта |
| Ошибка валидации | Telegram `validation.result` | Получает `validation.result` |
| Диск заканчивается | Telegram-алерт | Получает `error` |

---

## 7. 📊 Таблица: что где хранится

| Данные | Хранится на VPS | Хранится на Desktop | Агрегируется |
|--------|----------------|---------------------|--------------|
| Свечи 1m spot | ✅ SQLite | ❌ (только кэш) | — |
| Свечи 1m futures | ✅ SQLite | ❌ (только кэш) | — |
| 5m, 15m, 1h, 4h, 1d, 1W | ❌ | ✅ Локально | Из 1m |
| Order book snapshots | ✅ SQLite | ❌ | — |
| Trades raw | ✅ SQLite | ❌ | — |
| Liquidations | ✅ SQLite | ❌ | — |
| OI, Funding Rate | ✅ SQLite | ❌ | — |
| Basis | ❌ | ✅ Локально | Из свечей |
| CVD | ❌ | ✅ Локально | Из trades |
| Индикаторы | ❌ | ✅ RAM | Из свечей |
| Сигналы | ❌ | ✅ SQLite | Из индикаторов |
| Сделки (журнал) | ❌ | ✅ SQLite | Из Execution |
| Результаты бэктестов | ❌ | ✅ SQLite | Из Backtester |

---

## 8. ⚙️ Команды управления (Desktop → VPS)

### 8.1 Управление парами

```bash
# Добавить пару
curl -X POST http://VPS:8800/api/symbols/add \
  -H "X-API-Key: key" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "DOGE/USDT"}'

# Удалить пару
curl -X POST http://VPS:8800/api/symbols/remove \
  -H "X-API-Key: key" \
  -d '{"symbol": "DOGE/USDT"}'
```

### 8.2 Управление backfill

```bash
# Запустить backfill для всех пар за 30 дней
curl -X POST http://VPS:8800/api/backfill \
  -H "X-API-Key: key" \
  -d '{"days": 30}'

# Запустить backfill для конкретной пары за конкретный период
curl -X POST http://VPS:8800/api/backfill \
  -H "X-API-Key: key" \
  -d '{"symbol": "BTC/USDT", "start": 1700000000000, "end": 1705000000000}'
```

### 8.3 Управление сервером

```bash
# Перезапустить модуль
curl -X POST http://VPS:8800/api/restart/futures_ws

# Перезапустить VPS сервер
curl -X POST http://VPS:8800/api/restart/server

# Запустить валидацию
curl -X POST http://VPS:8800/api/validate \
  -H "X-API-Key: key" \
  -d '{"symbol": "BTC/USDT", "days": 7}'
```

---

## 9. 📈 Метрики успеха

| Метрика | Цель | Как измерять |
|---------|------|-------------|
| Время доступа к свечам | < 100ms | `curl -w %{time_total} /api/candles` |
| Задержка WS | < 1s | Разница timestamp heartbeat VPS → Desktop |
| Потеря данных | < 0.1% | `data_verifier` проверка gaps |
| Uptime VPS | > 99% | `systemctl status crypto-telemetry` |
| Время восстановления после сбоя | < 30s | Авто-реконнект WS |

---

## 10. 🎯 Приоритет выполнения

| № | Задача | Время | Зависимости |
|---|--------|-------|-------------|
| 1 | Очистить БД на VPS + init_db | 5 мин | — |
| 2 | Запустить backfill futures 1m | 5 мин | #1 |
| 3 | Запустить backfill spot 1m | 4 мин | #1 |
| 4 | Запустить collector | 1 мин | #2, #3 |
| 5 | Проверить API endpoint'ы | 10 мин | #4 |
| 6 | Настроить Desktop (агрегацию) | 15 мин | #4 |
| 7 | Проверить Telegram-уведомления | 5 мин | #4 |
| 8 | Мониторинг 24ч | — | #5, #6, #7 |
