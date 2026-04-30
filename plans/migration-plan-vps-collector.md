# План миграции: VPS-only сборщик + Desktop-терминал

**Основание:** ADR-001 (VPS-Collector Architecture)  
**Статус:** Черновик  
**Дата:** 2026-04-29

---

## Этап 1: Подготовка (сделать до любых изменений кода)

### 1.1 Обновить `.env.example`

Добавить переменные для двух режимов:

```bash
# --- Режим запуска: collector / terminal ---
RUN_MODE=terminal

# --- VPS (только для terminal) ---
VPS_HOST=132.243.235.173
VPS_PORT=8800
VPS_API_KEY=vps_telemetry_key_2026

# --- Desktop (только для terminal) ---
BINGX_API_KEY=your_api_key_here
BINGX_API_SECRET=your_api_secret_here
```

### 1.2 Создать `core/config.py`

Централизованная конфигурация, читающая `.env` и предоставляющая typed-поля для всех модулей.

```python
# core/config.py — псевдокод
class AppConfig:
    RUN_MODE: Literal["collector", "terminal"]
    VPS_HOST: str
    VPS_PORT: int
    VPS_API_KEY: str
    SYMBOLS: list[str]
    BINGX_API_KEY: str
    BINGX_API_SECRET: str
    ...
```

---

## Этап 2: VPS — Telemetry WS endpoint

### 2.1 Добавить WebSocket в `telemetry/server.py`

Сейчас там только REST. Нужно добавить:

- `@app.websocket("/ws")` — принимает подключения от Desktop
- Фоновую задачу, которая подписывается на Event Bus VPS и транслирует события в WS
- Аутентификацию при подключении (проверка `X-API-Key`)
- Обработку команд от Desktop (ping, get_state)

**Образец:** [`ui/ws_server.py`](ui/ws_server.py) — там уже есть готовая реализация WS для фронтенда. Можно взять за основу:
- `_serialise()` — сериализация событий
- `_broadcast()` — рассылка всем клиентам
- `BROADCAST_EVENTS` — список транслируемых событий

### 2.2 Добавить REST endpoint `/api/candles`

Сейчас на VPS нет endpoint'а для свечей. Нужно добавить:

```python
@router.get("/api/candles")
async def get_candles(symbol: str, tf: str, limit: int, market_type: str = "spot"):
    # Прямой запрос к SQLite БД VPS
    # Аналог: ui/ws_server.py → _candles_http_handler()
```

**Образец:** тот же [`ui/ws_server.py:_candles_http_handler()`](ui/ws_server.py:138).

---

## Этап 3: Desktop — новый клиент для подключения к VPS

### 3.1 Создать `data/vps_client.py`

Новый модуль — замена прямых BingX-подключений на Desktop.

```python
# data/vps_client.py — псевдокод
class VPSClient:
    """Клиент для получения данных с VPS вместо прямого BingX."""

    # WS подключение к VPS :8800/ws
    # Получает: свечи, стакан, сделки, ликвидации, watchdog-события
    # Публикует в локальный Event Bus Desktop'а

    # REST запросы к VPS :8800
    async def get_candles(symbol, tf, limit) -> list[Candle]
    async def get_status() -> dict
    async def start_backfill(symbol, period) -> str
```

### 3.2 Модифицировать `main.py`

Добавить режимы запуска:

```python
# main.py — псевдокод
config = AppConfig()

if config.RUN_MODE == "collector":
    # VPS: только Data Layer
    rate_guard = RateLimitGuard()
    rest_client = BingXRestClient(event_bus, rate_guard)
    ws_client = BingXWebSocket(event_bus, symbols)
    futures_ws = BingXFuturesWebSocket(event_bus, symbols)
    tf_aggregator = TFAggregator(event_bus)
    ob_processor = OBProcessor(event_bus)
    watchdog = Watchdog(event_bus, rest_client)
    basis_calculator = BasisCalculator(event_bus)
    data_verifier = DataVerifier(event_bus)
    # + telemetry/server.py (уже запущен отдельно через uvicorn)

elif config.RUN_MODE == "terminal":
    # Desktop: Analytics + Signals + Execution + UI
    vps_client = VPSClient(event_bus, config)
    ta_engine = TAEngine(event_bus)
    smc_engine = SmartMoneyEngine(event_bus)
    volume_engine = VolumeEngine(event_bus)
    mtf_engine = MTFConfluenceEngine(event_bus)
    correlation_engine = CorrelationEngine(event_bus, symbols)
    signal_engine = SignalEngine(event_bus)
    anomaly_detector = AnomalyDetector(event_bus)
    risk_guard = RiskGuard(RiskConfig())
    api_client = BingXPrivateClient(...)  # Только Private API
    execution_engine = ExecutionEngine(...)
    ws_server = WSServer(...)  # UI WebSocket (локальный, для React)
```

---

## Этап 4: Миграция Desktop на VPS-данные

### 4.1 Заменить WS-подписки

**Сейчас:** Desktop подписывается на `candle.*` от своего `BingXWebSocket`.  
**После:** Desktop подписывается на те же события, но от `VPSClient`, который получает их с VPS через WS.

События не меняются — меняется источник. Все подписчики (TF Aggregator, Analytics, Storage) продолжают работать без изменений.

### 4.2 Заменить REST-запросы

**Сейчас:** `/api/candles` на `localhost:8765` (локальный WS Server).  
**После:** `/api/candles` на `132.243.235.173:8800` (VPS).

Достаточно поменять base URL в `ChartView.tsx` и других компонентах.

### 4.3 Убрать ненужные модули на Desktop

В режиме `terminal` не запускаются:
- `BingXWebSocket` — данные идут через VPS
- `BingXFuturesWebSocket` — данные идут через VPS
- `BingXRestClient` (публичный) — данные идут через VPS
- `RateLimitGuard` — не нужен, т.к. нет прямых REST-запросов к BingX
- `TFAggregator` — агрегация уже сделана на VPS (но можно и локально дублировать для независимости)
- `OBProcessor` — уже обработан на VPS
- `Watchdog` — уже работает на VPS
- `BasisCalculator` — уже считается на VPS
- `DataVerifier` — уже проверяет на VPS

**Остаётся на Desktop:**
- `BingXPrivateClient` — только для ордеров (Private API)
- Весь Analytics Core
- Signals
- Execution
- Backtester
- UI

---

## Этап 5: Обработка краевых случаев

### 5.1 Desktop включился после простоя

1. Подключается к VPS WS — получает текущее состояние (последние свечи, статус соединений)
2. Запрашивает через REST последние N свечей для заполнения локального кэша
3. Analytics Core пересчитывает индикаторы на актуальных данных
4. Система готова

**Оценка времени:** 1-2 секунды.

### 5.2 VPS недоступен

Desktop не может получить данные. Варианты поведения:
- **Offline-режим:** Desktop использует последний кэш (если есть) и показывает "VPS disconnected"
- **Авто-восстановление:** Desktop пытается переподключиться каждые 5 секунд
- **Alert:** Telegram-уведомление (через `TelegramNotifier` на Desktop)

### 5.3 VPS перезагружается

- WS-соединение рвётся → Desktop входит в цикл переподключения
- VPS поднимается → `repair_integrity()` + `refresh_recent()` + `run_backfill()` на VPS
- Desktop подключается и получает актуальные данные

---

## Этап 6: Развёртывание

### 6.1 На VPS

```bash
# Установка
git clone <repo> /opt/collector
cd /opt/collector
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# EDIT .env: RUN_MODE=collector, VPS_API_KEY=...

# systemd сервисы (уже есть в deploy/)
cp deploy/crypto-telemetry.service /etc/systemd/system/
cp deploy/crypto-watchdog.service /etc/systemd/system/
cp deploy/crypto-validator.service /etc/systemd/system/
cp deploy/crypto-validator.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now crypto-telemetry
systemctl enable --now crypto-watchdog
systemctl enable --now crypto-validator.timer
```

### 6.2 На Desktop

```bash
# Установка
git clone <repo> ~/crypto-terminal
cd ~/crypto-terminal
python -m venv venv
venv\Scripts\activate  # или source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# EDIT .env: RUN_MODE=terminal, VPS_HOST=132.243.235.173, BINGX_API_KEY=...

# Запуск
python main.py
# + UI: cd ui/react-app && npm install && npm run dev
```

---

## Порядок реализации (по шагам)

| № | Шаг | Файлы | Затрагивает |
|---|---|---|---|
| 1 | Создать `core/config.py` | Новый файл | Оба режима |
| 2 | Обновить `.env.example` | `.env.example` | Оба режима |
| 3 | Добавить WS endpoint в `telemetry/server.py` | `telemetry/server.py` | VPS |
| 4 | Добавить `/api/candles` в `telemetry/server.py` | `telemetry/server.py` | VPS |
| 5 | Создать `data/vps_client.py` | Новый файл | Desktop |
| 6 | Рефакторинг `main.py` — два режима | `main.py` | Оба режима |
| 7 | Обновить `ui/ws_server.py` — поддержка VPS-источника | `ui/ws_server.py` | Desktop |
| 8 | Обновить фронтенд (base URL для REST) | `ui/react-app/src/...` | Desktop |
| 9 | Обновить `deploy/` файлы под collector режим | `deploy/*` | VPS |
| 10 | Интеграционное тестирование | — | Оба режима |

---

## Что НЕ меняется

- Все модули Analytics, Signals, Execution, Backtester — **без изменений**
- Модели БД и репозитории — **без изменений**
- Event Bus — **без изменений**
- React-компоненты (кроме base URL) — **без изменений**
- Логика расчёта индикаторов, скоринга, сигналов — **без изменений**

---

## Риски

| Риск | Вероятность | Mitigation |
|---|---|---|
| Задержка WS VPS→Desktop > 50ms | Низкая | VPS и Desktop в одной стране, 1 Гбит/с канал |
| Потеря событий при переполнении буфера WS | Средняя | VPS хранит все данные в БД — Desktop дозапрашивает пропущенное |
| Desktop не может подключиться к VPS | Низкая | Авто-реконнект + Telegram-уведомление |
| Конфликт версий кода на VPS и Desktop | Средняя | Один репозиторий, одна ветка, git pull перед запуском |
