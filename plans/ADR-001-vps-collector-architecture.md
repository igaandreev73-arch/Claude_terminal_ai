# ADR-001: VPS-сборщик + Desktop-терминал

**Статус:** Предложено  
**Дата:** 2026-04-29  
**Автор:** AI Architect  

---

## Контекст

Исходная архитектура PRD предполагала два сервера:

```
Сервер A — сборщик (VPS)    Сервер B — основной (десктоп)
─────────────────────────   ─────────────────────────────
Data Collector               Analytics Core
TF Aggregator     ──sync──►  Signal Engine
OB Processor                 Execution Engine
ML Dataset Writer            UI + AI Advisor
```

Однако текущая реализация имеет **два независимых сборщика** — каждый со своим прямым подключением к BingX (WS + REST). Это приводит к:
- Удвоенному потреблению rate-limit BingX
- Риску рассинхронизации данных
- Отсутствию механизма синхронизации между серверами
- Бессмысленной нагрузке на Desktop, который работает не 24/7

## Решение

Перейти к архитектуре **VPS-only сборщик**, где VPS — единственный источник публичных рыночных данных, а Desktop — аналитический терминал, получающий данные с VPS.

### Схема

```
BingX Public API
       │
       ▼
┌──── VPS (132.243.235.173) ────────────────────────┐
│  Режим: COLLECTOR (24/7)                          │
│                                                    │
│  data/bingx_ws.py          — WS spot               │
│  data/bingx_futures_ws.py  — WS futures            │
│  data/bingx_rest.py        — REST история/OI/Funding│
│  data/tf_aggregator.py     — агрегация ТФ           │
│  data/ob_processor.py      — стакан                 │
│  data/watchdog.py          — мониторинг WS           │
│  data/basis_calculator.py  — базис                  │
│  data/data_verifier.py     — верификация            │
│  telemetry/watchdog.py     — Telegram алёрты        │
│  scripts/validate_and_fill.py — каждые 6ч           │
│                                                    │
│  telemetry/server.py (FastAPI :8800)                │
│    ├── WS /ws  ── реалтайм события → Desktop       │
│    ├── GET /api/candles ── история → Desktop        │
│    ├── GET /data/* ────── статистика → Desktop      │
│    └── POST /backfill ── управление → Desktop       │
└────────────────────────────────────────────────────┘
                          │
                    WS + REST (X-API-Key)
                          ▼
┌──── Desktop (локальный ПК) ────────────────────────┐
│  Режим: TERMINAL (по запросу)                      │
│                                                    │
│  WS клиент → VPS :8800  (реалтайм данные)          │
│  REST клиент → VPS :8800 (исторические данные)     │
│  execution/bingx_private.py → BingX Private API     │
│    (только ордера, ключ хранится локально)          │
│                                                    │
│  analytics/ta_engine.py     — TA индикаторы         │
│  analytics/smartmoney.py    — SMC                   │
│  analytics/volume_engine.py — объёмный анализ       │
│  analytics/correlation.py   — корреляции            │
│  analytics/mtf_confluence.py — MTF скоринг          │
│  signals/signal_engine.py   — сигналы               │
│  signals/anomaly_detector.py — аномалии             │
│  execution/execution_engine.py — исполнение         │
│  execution/risk_guard.py    — риск-менеджмент       │
│  backtester/*               — бэктестинг            │
│  strategies/*               — стратегии             │
│  ui/*                       — Electron + React      │
└────────────────────────────────────────────────────┘
```

### Разделение модулей

#### На VPS (COLLECTOR) — только Data Layer
| Модуль | Файл | Причина |
|---|---|---|
| BingX WS spot | `data/bingx_ws.py` | Должен работать 24/7 |
| BingX WS futures | `data/bingx_futures_ws.py` | Должен работать 24/7 |
| BingX REST | `data/bingx_rest.py` | Должен работать 24/7 |
| Rate Limit Guard | `data/rate_limit_guard.py` | Часть REST клиента |
| TF Aggregator | `data/tf_aggregator.py` | Каждую минуту |
| OB Processor | `data/ob_processor.py` | 24/7 |
| Watchdog | `data/watchdog.py` | Мониторинг WS |
| Basis Calculator | `data/basis_calculator.py` | Каждую минуту |
| Data Verifier | `data/data_verifier.py` | Периодически |
| Telemetry API | `telemetry/server.py` | Интерфейс для Desktop |
| Telegram Watchdog | `telemetry/watchdog.py` | Мониторинг VPS |
| Backfill | `data/backfill.py` | Авторемонт при старте |
| Validator | `data/validator.py` | Валидация данных |

#### На Desktop (TERMINAL) — Analytics + Signals + Execution + UI
| Модуль | Файл | Причина |
|---|---|---|
| TA Engine | `analytics/ta_engine.py` | Требует CPU |
| SmartMoney | `analytics/smartmoney.py` | Требует CPU |
| Volume Engine | `analytics/volume_engine.py` | Требует CPU |
| Correlation | `analytics/correlation.py` | Требует CPU |
| MTF Confluence | `analytics/mtf_confluence.py` | Зависит от Analytics |
| Signal Engine | `signals/signal_engine.py` | Рядом с UI |
| Anomaly Detector | `signals/anomaly_detector.py` | Рядом с Execution |
| Execution Engine | `execution/execution_engine.py` | Рядом с UI (semi-auto) |
| Risk Guard | `execution/risk_guard.py` | Часть Execution |
| BingX Private | `execution/bingx_private.py` | Ключ только локально |
| Backtester | `backtester/*` | Тяжёлые вычисления |
| Strategies | `strategies/*` | Часть бэктестера |
| UI | `ui/*` | Desktop-приложение |

#### На обоих (общее ядро)
| Модуль | Файл |
|---|---|
| Event Bus | `core/event_bus.py` |
| Logger | `core/logger.py` |
| Base Module | `core/base_module.py` |
| Health Monitor | `core/health_monitor.py` |
| Storage (модели) | `storage/models.py`, `storage/database.py` |
| Repositories | `storage/repositories/*` |

### Протокол VPS → Desktop

**1. Реалтайм события — WebSocket (`/ws`)**

VPS транслирует события своего Event Bus Desktop'у через WebSocket:

```
VPS Event Bus → telemetry/server.py WS endpoint → Desktop WS клиент
```

Транслируются те же события, что сейчас в `BROADCAST_EVENTS` (`ui/ws_server.py`):
- `candle.1m.tick`, `candle.1m.closed` — свечи
- `futures.candle.1m.closed` — фьючерсные свечи
- `orderbook.update` — стакан
- `futures.liquidation` — ликвидации
- `watchdog.*` — статус соединений
- `futures.basis.updated` — базис

Desktop НЕ публикует события в Event Bus VPS — только подписывается.

**2. Исторические данные — REST**

```
Desktop → GET http://132.243.235.173:8800/api/candles?symbol=BTC/USDT&tf=1m&limit=500
       → GET http://132.243.235.173:8800/data/status
       → GET http://132.243.235.173:8800/data/gaps
```

**3. Команды управления — REST (Desktop → VPS)**

```
POST /backfill    — запуск загрузки истории
POST /symbols/add — добавить пару
POST /symbols/remove — удалить пару
```

Команды торговли (confirm_signal, close_position, set_mode) остаются на Desktop.

**4. Аутентификация**

`X-API-Key` из `.env` — уже реализовано в `telemetry/server.py`.

### BingX Private API

Desktop сохраняет прямое REST-подключение к BingX Private API только для:
- Открытия/закрытия ордеров
- Получения баланса
- Получения статуса позиций

API-ключ хранится **только** в `.env` на Desktop. На VPS его нет.

### Режимы запуска

Один `main.py` с флагом `RUN_MODE`:

```bash
# .env на VPS
RUN_MODE=collector
VPS_API_KEY=...
WS_HOST=0.0.0.0
WS_PORT=8800

# .env на Desktop
RUN_MODE=terminal
VPS_HOST=132.243.235.173
VPS_PORT=8800
VPS_API_KEY=...
BINGX_API_KEY=...       # только для Private API
BINGX_API_SECRET=...    # только для Private API
```

### Что делать с дублированием кода

Модули из списка "общее ядро" присутствуют в обоих репозиториях (фактически одна кодовая база). Это осознанное решение:
- VPS и Desktop используют одну ветку git
- При деплое на VPS — `RUN_MODE=collector`
- При запуске на Desktop — `RUN_MODE=terminal`
- Изменения в core/storage применяются к обоим сразу

---

## Последствия

### Положительные
- Единый источник рыночных данных — никакой рассинхронизации
- Экономия rate-limit BingX (один набор WS/REST подключений)
- VPS (1 vCPU, 1GB RAM) справляется со сбором — нагрузка лёгкая
- Desktop не тратит ресурсы на сбор данных — только аналитика
- Данные не теряются когда Desktop выключен
- Не нужна синхронизация БД между серверами

### Отрицательные
- Desktop зависит от VPS — если VPS недоступен, терминал не получит данные
- Дополнительная задержка на передачу данных через VPS (но в локальной сети/быстром интернете — <5ms)
- Нужно доработать `telemetry/server.py` (WS endpoint)
- Нужно изменить `main.py` (два режима запуска)
- Нужен новый клиент на Desktop для подключения к VPS вместо прямого BingX

### Риски и mitigation
| Риск | Mitigation |
|---|---|
| VPS недоступен | Desktop кэширует последние N свечей локально, при восстановлении VPS — дозагрузка пропущенного |
| Задержка WS > 100ms | WS VPS → Desktop в одной сети (или через быстрый интернет) — задержка < 5ms |
| Desktop не получает события пока выключен | VPS хранит все данные в БД — Desktop дозапрашивает пропущенное при старте |

---

## Статус реализации

- [ ] ADR утверждён
- [ ] `main.py` — режимы COLLECTOR / TERMINAL
- [ ] `telemetry/server.py` — WS endpoint для трансляции событий
- [ ] Новый модуль `data/vps_client.py` — WS + REST клиент для Desktop
- [ ] `core/config.py` — централизованная конфигурация режимов
- [ ] `.env.example` — обновлён под два режима
- [ ] Документация обновлена
- [ ] Старый код прямых BingX-подключений на Desktop удалён

---

## Ссылки

- PRD.md — раздел 4 "Два сервера"
- `telemetry/server.py` — текущая реализация VPS API
- `ui/ws_server.py` — текущая реализация WS для фронтенда (образец для VPS WS)
- `main.py` — точка входа, требует рефакторинга
