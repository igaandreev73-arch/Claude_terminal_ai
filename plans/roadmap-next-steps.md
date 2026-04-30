# Roadmap: Следующие шаги после миграции архитектуры

## Три направления развития

---

## 🔵 Направление A: Проверка работы в браузере (Desktop)

**Цель:** Убедиться, что фронтенд корректно отображает состояние системы после миграции.

### A1. Проверить Pulse-вкладку (localhost:8765)

| Шаг | Действие | Ожидаемый результат | Критерий приёмки |
|-----|----------|---------------------|-------------------|
| 1 | Открыть `http://localhost:8765` в браузере | Страница загружается, WebSocket подключается | Вкладка "Пульс" активна |
| 2 | Перейти на вкладку "Пульс" | Блок "Соединения" отображается | Видны: `ws_ui`, `vps_ws`, `vps_server`, `vps_db`, `local_db`, `bingx_private` |
| 3 | Проверить статусы соединений | VPS-соединения показывают stage из `vpsActive` (polling) | `vps_ws` = online/offline/unknown |
| 4 | Проверить блок "Сервер VPS" | Отображаются CPU, RAM, uptime с VPS | Данные приходят через `useVpsTelemetry` polling |
| 5 | Проверить блок "Статус данных" | Видны строки с symbol/timeframe/trust_score | Данные приходят через pulseState |

### A2. Проверить ChartView

| Шаг | Действие | Ожидаемый результат |
|-----|----------|---------------------|
| 1 | Открыть вкладку с графиком | График загружается |
| 2 | Переключить символ/таймфрейм | Свечи подгружаются через `fetchVpsCandles()` (REST к VPS) |

### A3. Проверить консоль браузера

| Проверка | Ожидание |
|----------|----------|
| WS подключение | `[WS] Connected to ws://localhost:8765` |
| Ошибки VPS | Если VPS недоступен — `[VPS] Status error: ...` (не критично) |
| pulse_state | Приходит объект с `connections`, `modules`, `data_rows` |

### Риски и mitigation

| Риск | Mitigation |
|------|------------|
| WS UI не переподключается после перезагрузки | Проверить `useWebSocket.ts` reconnect logic |
| VPS_API_KEY не заполнен | VPSClient получает 403 — добавить проверку в `.env` |
| Pulse-данные не приходят | Проверить `_handle_get_pulse_state` в `ws_server.py` |

---

## 🟢 Направление B: Настройка VPS (132.243.235.173)

**Цель:** Развернуть collector-mode на VPS, настроить systemd-сервис, обеспечить мониторинг.

### B1. Подготовка VPS

```bash
# Оценка: 15 минут
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git
```

### B2. Клонирование и настройка

```bash
# Оценка: 10 минут
git clone https://github.com/igaandreev73-arch/Claude_terminal_ai /opt/crypto-telemetry
cd /opt/crypto-telemetry
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### B3. Файл .env на VPS

```
RUN_MODE=collector
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT,BNB/USDT,SUI/USDT,PEPE/USDT,WIF/USDT,ADA/USDT,XRP/USDT
BINGX_API_KEY=<vps_bingx_key_public_only>
BINGX_API_SECRET=<vps_bingx_secret_public_only>
BINGX_FUTURES_API_KEY=<vps_futures_key>
BINGX_FUTURES_API_SECRET=<vps_futures_secret>
VPS_API_KEY=<сгенерировать сложный ключ>
TELEGRAM_BOT_TOKEN=<опционально>
TELEGRAM_CHAT_ID=<опционально>
```

> **Важно:** На VPS используются **только Public API** ключи BingX (read-only). Private API для ордеров — только на Desktop.

### B4. Настройка systemd

```bash
# Оценка: 10 минут
cp deploy/crypto-telemetry.service /etc/systemd/system/
# Проверить пути в .service (WorkingDirectory, ExecStart)
systemctl daemon-reload
systemctl enable crypto-telemetry
systemctl start crypto-telemetry
systemctl status crypto-telemetry
```

### B5. Настройка Watchdog + Telegram

```bash
# Оценка: 5 минут
cp deploy/crypto-watchdog.service /etc/systemd/system/
systemctl enable crypto-watchdog
systemctl start crypto-watchdog
```

### B6. Настройка Validator (опционально)

```bash
# Оценка: 5 минут
cp deploy/crypto-validator.service /etc/systemd/system/
cp deploy/crypto-validator.timer /etc/systemd/system/
systemctl enable crypto-validator.timer
systemctl start crypto-validator.timer
```

### B7. Проверка VPS

```bash
# Оценка: 5 минут
curl http://localhost:8800/health
curl http://localhost:8800/status
curl http://localhost:8800/symbols
```

### B8. Настройка Desktop для подключения к VPS

В `.env` на Desktop добавить/проверить:

```
VPS_HOST=132.243.235.173
VPS_PORT=8800
VPS_API_KEY=<тот же ключ, что на VPS>
```

### Риски и mitigation

| Риск | Mitigation |
|------|------------|
| VPS 1 vCPU, 1GB RAM не тянет сбор | Ограничить количество символов, отключить ненужные модули |
| VPS перезагрузился | systemd auto-restart + Watchdog с Telegram-уведомлением |
| Порт 8800 не открыт | Настроить ufw: `ufw allow 8800` (ограничить по IP Desktop) |

---

## 🟡 Направление C: Новый функционал / улучшения

**Цель:** Добавить фичи, улучшить мониторинг, оптимизировать производительность.

### C1. Мониторинг VPS (High priority)

**Проблема:** Сейчас Desktop узнаёт о состоянии VPS только через polling `useVpsTelemetry` (раз в 10 сек).

**Решение:** Добавить heartbeat-канал VPS → Desktop через WS.

| Задача | Описание | Оценка |
|--------|----------|--------|
| C1.1 | Добавить heartbeat-сообщение в `telemetry/server.py` (раз в 5 сек: `{"type": "heartbeat", "cpu": ..., "ram": ..., "uptime": ...}`) | 2ч |
| C1.2 | В `VPSClient._on_message()` обрабатывать `heartbeat` и обновлять `_last_heartbeat` | 1ч |
| C1.3 | В `useVpsTelemetry.ts` добавить счётчик `seconds_since_last_heartbeat` | 1ч |
| C1.4 | В `PulseView.tsx` добавить индикатор "VPS heartbeat: Xs назад" | 1ч |

**Критерий успеха:** Если VPS упал — Desktop показывает "VPS offline" через <10 сек (вместо текущих ~30 сек polling).

### C2. Graceful degradation при недоступности VPS (High priority)

**Проблема:** Если VPS недоступен, Desktop не получает данные, но UI продолжает показывать устаревшую информацию.

**Решение:** Добавить механизм graceful degradation.

| Задача | Описание | Оценка |
|--------|----------|--------|
| C2.1 | В `VPSClient` добавить флаг `_data_stale` — True, если нет данных >60 сек | 1ч |
| C2.2 | В `_handle_get_pulse_state` добавить `vps_data_stale: bool` | 1ч |
| C2.3 | В `PulseView.tsx` показывать баннер "⚠️ Данные устарели: VPS недоступен" | 2ч |
| C2.4 | Отключить генерацию сигналов при stale-данных (Signal Engine guard) | 2ч |

**Критерий успеха:** При падении VPS Desktop переходит в safe-режим за <60 сек.

### C3. Кэширование свечей на Desktop (Medium priority)

**Проблема:** При каждом открытии графика `ChartView` делает REST-запрос к VPS. При частых переключениях символов/таймфреймов — избыточная нагрузка.

**Решение:** Локальный in-memory кэш свечей на Desktop.

| Задача | Описание | Оценка |
|--------|----------|--------|
| C3.1 | Создать `core/cache.py` — `CandlesCache` (dict key=symbol+tf, value=list[Candle], maxsize=50) | 2ч |
| C3.2 | В `VPSClient.get_candles()` добавить параметр `use_cache=True` | 1ч |
| C3.3 | В `ChartView.fetchCandles()` добавить проверку кэша перед REST | 1ч |

**Критерий успеха:** Повторный запрос тех же свечей не уходит на VPS (latency <1ms вместо ~100ms).

### C4. Автоматический backfill при подключении Desktop (Medium priority)

**Проблема:** Если Desktop был выключен несколько часов, при включении свечи за этот период отсутствуют.

**Решение:** При старте `_run_terminal()` автоматически запускать backfill на VPS.

| Задача | Описание | Оценка |
|--------|----------|--------|
| C4.1 | В `main.py._run_terminal()` после `vps_client.start()` вызвать `vps_client.start_backfill(days=1)` | 1ч |
| C4.2 | В `VPSClient` добавить статус backfill-процесса (running/done/failed) | 1ч |
| C4.3 | В `PulseView.tsx` отображать прогресс backfill | 2ч |

**Критерий успеха:** При включении Desktop после 8ч простоя — все свечи за 8ч подтягиваются автоматически.

### C5. Оптимизация VPS (Low priority)

**Проблема:** VPS (1 vCPU, 1GB RAM) может не справляться с пиковой нагрузкой (много символов, все таймфреймы).

**Решение:** Профилирование и оптимизация.

| Задача | Описание | Оценка |
|--------|----------|--------|
| C5.1 | Добавить метрики в `/metrics` — CPU/RAM per module | 2ч |
| C5.2 | Профилировать TF Aggregator (самый тяжёлый модуль) | 2ч |
| C5.3 | Оптимизировать batch-запись в БД (уменьшить число транзакций) | 3ч |

**Критерий успеха:** VPS держит 10 символов, 10+ таймфреймов, CPU <70%, RAM <700MB.

### C6. Data trust dashboard (Low priority)

**Проблема:** Сейчас trust_score виден только в блоке "Статус данных" на Pulse.

**Решение:** Выделить отдельную вкладку "Качество данных" с историей и трендами.

| Задача | Описание | Оценка |
|--------|----------|--------|
| C6.1 | Создать компонент `DataQualityView.tsx` | 3ч |
| C6.2 | Добавить график trust_score по времени | 2ч |
| C6.3 | Добавить список последних ошибок верификации | 1ч |

**Критерий успеха:** Пользователь видит динамику качества данных за последние 24ч.

---

## Приоритеты и порядок выполнения

| Приоритет | Направление | Задача | Эффект |
|-----------|-------------|--------|--------|
| 🔴 P0 | B | Развернуть VPS | Без этого система не работает |
| 🔴 P0 | A | Проверить браузер | Убедиться, что миграция не сломала UI |
| 🟡 P1 | C1 | Heartbeat VPS | Быстрое обнаружение проблем |
| 🟡 P1 | C2 | Graceful degradation | Безопасность при отказе VPS |
| 🟢 P2 | C4 | Auto backfill | Удобство использования |
| 🟢 P2 | C3 | Кэширование свечей | Производительность UI |
| 🔵 P3 | C5 | Оптимизация VPS | Стабильность при нагрузке |
| 🔵 P3 | C6 | Data quality dashboard | Прозрачность данных |

---

## Оценка суммарных трудозатрат

| Направление | Часы |
|-------------|------|
| A: Проверка браузера | 1-2ч |
| B: Настройка VPS | 1-2ч |
| C1: Heartbeat | 4-5ч |
| C2: Graceful degradation | 6ч |
| C3: Кэширование | 4ч |
| C4: Auto backfill | 4ч |
| C5: Оптимизация VPS | 7ч |
| C6: Data quality | 6ч |
| **Итого** | **~33-36ч** |
