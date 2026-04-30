# Полный план выполнения: от текущего состояния до production

**Дата:** 2026-04-30
**Статус:** Архитектура мигрирована, код на GitHub, Desktop работает в terminal-mode

---

## Содержание

1. [Фаза 0: Проверка Desktop (браузер)](#фаза-0-проверка-desktop-браузер)
2. [Фаза 1: Развёртывание VPS (collector)](#фаза-1-развёртывание-vps-collector)
3. [Фаза 2: Heartbeat VPS → Desktop](#фаза-2-heartbeat-vps--desktop)
4. [Фаза 3: Graceful degradation](#фаза-3-graceful-degradation)
5. [Фаза 4: Auto backfill при старте](#фаза-4-auto-backfill-при-старте)
6. [Фаза 5: Кэширование свечей](#фаза-5-кэширование-свечей)
7. [Фаза 6: Оптимизация VPS](#фаза-6-оптимизация-vps)
8. [Фаза 7: Data quality dashboard](#фаза-7-data-quality-dashboard)

---

## Фаза 0: Проверка Desktop (браузер)

**Цель:** Убедиться, что фронтенд работает корректно после миграции архитектуры.
**Оценка:** 1-2ч
**Зависимости:** Нет (Desktop уже запущен)

### Шаг 0.1 — Открыть Pulse-вкладку

| Действие | Ожидание |
|----------|----------|
| Открыть `http://localhost:8765` | Страница загружается |
| Перейти на вкладку "Пульс" | Блок "Соединения" с 8 соединениями |
| Проверить `ws_ui` | stage = "normal" (есть клиенты WS) или "lost" |
| Проверить `local_db` | stage = "normal" (БД доступна) |
| Проверить `vps_ws`, `vps_server`, `vps_db` | stage из `vpsActive` (online/offline/unknown) |
| Проверить `bingx_private` | stage = "stopped" (пока не настроен) |

**Критерий:** Все соединения отображаются, нет пустых/сломанных блоков.

### Шаг 0.2 — Проверить блок "Сервер VPS"

| Действие | Ожидание |
|----------|----------|
| Если VPS запущен | CPU, RAM, uptime, database stats |
| Если VPS не запущен | "Нет данных" или "VPS недоступен" |

### Шаг 0.3 — Проверить консоль браузера (F12)

| Что искать | Ожидание |
|------------|----------|
| `[WS] Connected to ws://localhost:8765` | WS UI подключён |
| `[VPS] Status error: ...` | Допустимо, если VPS не запущен |
| `pulse_state` в Network-вкладке | Приходит объект с connections/modules/data_rows |
| Любые `console.error` | **Не должно быть** — если есть, фиксим |

### Шаг 0.4 — Проверить ChartView

| Действие | Ожидание |
|----------|----------|
| Открыть вкладку с графиком | График загружается |
| Выбрать символ + таймфрейм | Свечи подгружаются |
| Переключить пару | Новые свечи загружаются |

### Шаг 0.5 — Проверить тесты

```bash
cd c:\Users\Admin\Claude_terminal_ai
pytest tests/ -v --tb=short
```

**Критерий:** Все 203 теста проходят (или известное количество).

### Шаг 0.6 — Зафиксировать результаты

Если всё ок → переход к Фазе 1.
Если есть ошибки → создать задачу на исправление.

---

## Фаза 1: Развёртывание VPS (collector)

**Цель:** Запустить collector-mode на VPS `132.243.235.173`.
**Оценка:** 1.5-2ч
**Зависимости:** Доступ к VPS по SSH, Фаза 0 завершена

### Шаг 1.1 — Подготовка VPS

```bash
# Подключение по SSH
ssh root@132.243.235.173

# Базовая настройка
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git ufw
```

### Шаг 1.2 — Клонирование репозитория

```bash
cd /opt
git clone https://github.com/igaandreev73-arch/Claude_terminal_ai collector
cd collector
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Шаг 1.3 — Создать .env на VPS

Файл `/opt/collector/.env`:

```ini
RUN_MODE=collector

# BingX Public API (read-only — только для сбора данных)
BINGX_API_KEY=<public_spot_key>
BINGX_API_SECRET=<public_spot_secret>
BINGX_FUTURES_API_KEY=<public_futures_key>
BINGX_FUTURES_API_SECRET=<public_futures_secret>

# VPS API Key (для аутентификации Desktop → VPS)
VPS_API_KEY=vps_telemetry_key_2026

# Telegram (опционально)
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=

# Символы
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT,BNB/USDT,SUI/USDT,PEPE/USDT,WIF/USDT,ADA/USDT,XRP/USDT

# Логирование
LOG_LEVEL=INFO
DB_PATH=data/collector.db
```

### Шаг 1.4 — Создать директорию для логов

```bash
mkdir -p /opt/collector/logs
```

### Шаг 1.5 — Настроить deploy-файлы

Проверить и поправить пути в systemd-сервисах.

**`/etc/systemd/system/crypto-telemetry.service`:**

```ini
[Unit]
Description=Crypto Collector - VPS Data Collector + Telemetry API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/collector
EnvironmentFile=/opt/collector/.env
Environment=RUN_MODE=collector
ExecStart=/opt/collector/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=append:/opt/collector/logs/collector.log
StandardError=append:/opt/collector/logs/collector.log

[Install]
WantedBy=multi-user.target
```

### Шаг 1.6 — Запустить collector

```bash
systemctl daemon-reload
systemctl enable crypto-telemetry
systemctl start crypto-telemetry
systemctl status crypto-telemetry  # должен быть active (running)
```

### Шаг 1.7 — Проверить API VPS

```bash
# Health-check
curl http://localhost:8800/health
# → {"status": "ok", ...}

# Status
curl http://localhost:8800/status
# → {"service": {...}, "system": {...}, "database": {...}}

# Symbols
curl http://localhost:8800/symbols
# → ["BTC/USDT", "ETH/USDT", ...]
```

### Шаг 1.8 — Настроить firewall

```bash
ufw allow ssh
ufw allow 8800  # Telemetry API
ufw enable
```

> **Важно:** Ограничить доступ к порту 8800 только с IP Desktop:
> ```bash
> ufw allow from <DESKTOP_IP> to any port 8800
> ufw deny 8800  # запретить всем остальным
> ```

### Шаг 1.9 — Настроить Watchdog (опционально)

```bash
cp /opt/collector/deploy/crypto-watchdog.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable crypto-watchdog
systemctl start crypto-watchdog
```

### Шаг 1.10 — Настроить Validator (опционально)

```bash
cp /opt/collector/deploy/crypto-validator.service /etc/systemd/system/
cp /opt/collector/deploy/crypto-validator.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable crypto-validator.timer
systemctl start crypto-validator.timer
```

### Шаг 1.11 — Проверить Desktop → VPS

На Desktop выполнить:

```bash
curl http://132.243.235.173:8800/health?api_key=vps_telemetry_key_2026
```

**Критерий:** Ответ 200 OK.

### Шаг 1.12 — Проверить Pulse на Desktop

Открыть `localhost:8765` → вкладка "Пульс":
- `vps_ws` → online (если VPSClient подключился через WS)
- `vps_server` → online (REST доступен)
- `vps_db` → online (БД на VPS доступна)
- Блок "Сервер VPS" → CPU/RAM/uptime с VPS

---

## Фаза 2: Heartbeat VPS → Desktop

**Цель:** Добавить heartbeat-канал, чтобы Desktop узнавал о состоянии VPS за <10 сек (вместо polling раз в 5 сек).
**Оценка:** 4-5ч
**Зависимости:** Фаза 1 завершена (VPS работает)

### Шаг 2.1 — Добавить heartbeat в telemetry/server.py

**Файл:** `telemetry/server.py`

**Описание:** Добавить фоновую задачу, которая раз в 5 сек отправляет heartbeat всем WS-клиентам.

```python
# Новый модуль: heartbeat loop
async def _heartbeat_loop() -> None:
    """Отправляет heartbeat всем подключённым WS-клиентам раз в 5 секунд."""
    while True:
        await asyncio.sleep(5)
        if not _ws_clients:
            continue
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            uptime = time.time() - psutil.boot_time()
            msg = {
                "type": "heartbeat",
                "cpu_percent": cpu,
                "ram_used_mb": round(ram.used / 1024 / 1024, 1),
                "ram_total_mb": round(ram.total / 1024 / 1024, 1),
                "uptime_sec": int(uptime),
                "ts": int(time.time() * 1000),
            }
            await _broadcast(msg)
        except Exception:
            pass
```

**Изменения в lifespan:**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_watch())
    asyncio.create_task(_heartbeat_loop())  # <-- добавить
    ...
```

**Критерий:** WS-клиенты получают `{"type": "heartbeat", ...}` каждые 5 сек.

### Шаг 2.2 — Обработка heartbeat в VPSClient

**Файл:** `data/vps_client.py`

**Описание:** В `_on_message()` добавить обработку `heartbeat`.

```python
# В _on_message(), после парсинга JSON:
if data.get("type") == "heartbeat":
    self._last_heartbeat = data.get("ts", 0)
    self._last_heartbeat_data = data
    self.is_connected = True
    self._reconnect_attempts = 0
    self.reconnect_delay = 1.0
    return  # не публикуем в Event Bus (это системное, не торговое)
```

**Новые атрибуты:**

```python
self._last_heartbeat: int = 0
self._last_heartbeat_data: dict = {}
```

**Новый метод:**

```python
@property
def seconds_since_heartbeat(self) -> float:
    if self._last_heartbeat == 0:
        return float('inf')
    return time.time() - self._last_heartbeat / 1000
```

**Критерий:** VPSClient обновляет `_last_heartbeat` при получении heartbeat.

### Шаг 2.3 — Пробросить heartbeat в pulse_state

**Файл:** `ui/ws_server.py`

**Описание:** В `_handle_get_pulse_state()` добавить данные heartbeat.

```python
# После секции connections:
vps_heartbeat = {
    "seconds_since": vps_client.seconds_since_heartbeat if self._vps_client else float('inf'),
    "cpu_percent": vps_client._last_heartbeat_data.get("cpu_percent") if self._vps_client else None,
    "ram_used_mb": vps_client._last_heartbeat_data.get("ram_used_mb") if self._vps_client else None,
    "uptime_sec": vps_client._last_heartbeat_data.get("uptime_sec") if self._vps_client else None,
}
```

**Новый параметр WSServer:** `vps_client: VPSClient | None = None`

**Критерий:** pulse_state содержит `vps_heartbeat` с актуальными данными.

### Шаг 2.4 — Обновить PulseView.tsx

**Файл:** `ui/react-app/src/components/PulseView.tsx`

**Описание:** В блоке "Сервер VPS" добавить индикатор heartbeat.

```tsx
// В VpsServerBlock():
const hb = pulseState?.vps_heartbeat
const hbAge = hb?.seconds_since ?? Infinity
const hbColor = hbAge < 15 ? '#22c55e' : hbAge < 30 ? '#eab308' : '#ef4444'

// Отобразить:
<div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
  <span style={{ width: 8, height: 8, borderRadius: '50%', background: hbColor }} />
  <span>Heartbeat: {hbAge < 60 ? `${Math.round(hbAge)}с назад` : 'Нет сигнала'}</span>
</div>
```

**Критерий:** Пользователь видит зелёную/жёлтую/красную точку heartbeat.

### Шаг 2.5 — Обновить useStore.ts

**Файл:** `ui/react-app/src/store/useStore.ts`

**Описание:** Добавить `vps_heartbeat` в интерфейс `PulseState`.

```typescript
export interface VpsHeartbeat {
  seconds_since: number
  cpu_percent: number | null
  ram_used_mb: number | null
  uptime_sec: number | null
}

// В PulseState:
vps_heartbeat: VpsHeartbeat | null
```

---

## Фаза 3: Graceful degradation

**Цель:** При недоступности VPS Desktop переходит в безопасный режим.
**Оценка:** 6ч
**Зависимости:** Фаза 2 (heartbeat)

### Шаг 3.1 — Добавить флаг _data_stale в VPSClient

**Файл:** `data/vps_client.py`

**Описание:** Если heartbeat не приходит >60 сек — данные считаются устаревшими.

```python
@property
def is_data_stale(self) -> bool:
    """True, если нет heartbeat >60 сек или WS отключён."""
    if not self.is_connected:
        return True
    return self.seconds_since_heartbeat > 60
```

**Критерий:** `vps_client.is_data_stale = True` через 60 сек после отключения VPS.

### Шаг 3.2 — Пробросить stale flag в pulse_state

**Файл:** `ui/ws_server.py`

**Описание:** В pulse_state добавить `vps_data_stale: bool`.

```python
"vps_data_stale": vps_client.is_data_stale if self._vps_client else True,
```

**Критерий:** При отключении VPS `pulse_state.vps_data_stale = true`.

### Шаг 3.3 — Баннер в PulseView.tsx

**Файл:** `ui/react-app/src/components/PulseView.tsx`

**Описание:** Если `vps_data_stale = true` — показать красный баннер.

```tsx
// В начале PulseView():
const isStale = pulseState?.vps_data_stale ?? true

return (
  <>
    {isStale && (
      <div style={{
        background: '#7f1d1d', color: '#fca5a5',
        padding: '8px 16px', borderRadius: 8,
        marginBottom: 12, fontSize: 13, fontWeight: 500,
      }}>
        ⚠️ Данные устарели: VPS недоступен. Сигналы отключены.
      </div>
    )}
    {/* остальные блоки */}
  </>
)
```

**Критерий:** Баннер появляется при отключении VPS.

### Шаг 3.4 — Guard в Signal Engine

**Файл:** `signals/signal_engine.py`

**Описание:** Не генерировать сигналы, если данные устарели.

```python
# В методе generate_signals():
if hasattr(self, '_vps_client') and self._vps_client.is_data_stale:
    log.warning("Данные устарели (VPS недоступен) — сигналы не генерируются")
    return []
```

**Альтернатива (без внедрения VPSClient в Signal Engine):** Использовать Event Bus — публиковать событие `system.data_stale` и подписывать Signal Engine на него.

**Критерий:** При stale-данных Signal Engine возвращает пустой список.

### Шаг 3.5 — Guard в Execution Engine

**Файл:** `execution/execution_engine.py`

**Описание:** Не исполнять ордера при stale-данных.

```python
# В execute_signal():
if self._data_stale:
    log.warning("Данные устарели — ордер не исполнен")
    return {"error": "data_stale", "message": "VPS недоступен"}
```

**Критерий:** Execution Engine отклоняет ордера при stale-данных.

---

## Фаза 4: Auto backfill при старте Desktop

**Цель:** При включении Desktop после простоя автоматически подтягивать пропущенные свечи.
**Оценка:** 4ч
**Зависимости:** Фаза 1 (VPS работает)

### Шаг 4.1 — Добавить статус backfill в VPSClient

**Файл:** `data/vps_client.py`

**Описание:** Добавить отслеживание статуса backfill-процесса.

```python
self._backfill_status: str = "idle"  # idle | running | done | failed
self._backfill_progress: int = 0
self._backfill_total: int = 0
```

**Новый метод:**

```python
async def start_backfill(self, symbol: str | None = None, days: int = 30) -> dict:
    """Запускает backfill на VPS."""
    result = await self._rest_post("/backfill", {"symbol": symbol, "days": days})
    self._backfill_status = "running"
    return result
```

**Подписка на события backfill:**

```python
# В _on_message():
if data.get("type") == "backfill.progress":
    self._backfill_progress = data.get("current", 0)
    self._backfill_total = data.get("total", 0)
elif data.get("type") == "backfill.complete":
    self._backfill_status = "done"
elif data.get("type") == "backfill.error":
    self._backfill_status = "failed"
```

**Критерий:** VPSClient отслеживает прогресс backfill.

### Шаг 4.2 — Запуск backfill при старте terminal

**Файл:** `main.py`

**Описание:** В `_run_terminal()` после подключения VPSClient запустить backfill.

```python
# После vps_client.start():
async def _auto_backfill():
    await asyncio.sleep(5)  # дать VPS время инициализироваться
    log.info("Запуск автоматического backfill (1 день)...")
    result = await vps_client.start_backfill(days=1)
    log.info(f"Backfill запущен: {result}")

asyncio.create_task(_auto_backfill())
```

**Критерий:** При старте Desktop автоматически запускается backfill на 1 день.

### Шаг 4.3 — Отобразить прогресс backfill в PulseView.tsx

**Файл:** `ui/react-app/src/components/PulseView.tsx`

**Описание:** Добавить индикатор прогресса backfill.

```tsx
// В блоке "Сервер VPS" или отдельным блоком:
const bf = pulseState?.backfill
if (bf?.status === 'running') {
  const pct = bf.total > 0 ? Math.round(bf.progress / bf.total * 100) : 0
  // Показать progress bar
}
```

**Критерий:** Пользователь видит прогресс backfill.

### Шаг 4.4 — Обновить useStore.ts

**Файл:** `ui/react-app/src/store/useStore.ts`

**Описание:** Добавить `backfill` в `PulseState`.

```typescript
export interface BackfillStatus {
  status: 'idle' | 'running' | 'done' | 'failed'
  progress: number
  total: number
  symbol: string | null
}
```

---

## Фаза 5: Кэширование свечей

**Цель:** In-memory кэш для быстрых повторных запросов свечей.
**Оценка:** 4ч
**Зависимости:** Нет

### Шаг 5.1 — Создать core/cache.py

**Файл:** `core/cache.py` (новый)

```python
"""In-memory кэш свечей для Desktop."""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CacheEntry:
    data: list[dict]
    created_at: float = field(default_factory=time.time)
    access_count: int = 0


class CandlesCache:
    """LRU-кэш свечей с максимальным количеством записей."""

    def __init__(self, maxsize: int = 100, ttl_sec: int = 300):
        self._maxsize = maxsize
        self._ttl_sec = ttl_sec
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

    def _key(self, symbol: str, tf: str, limit: int) -> str:
        return f"{symbol}:{tf}:{limit}"

    def get(self, symbol: str, tf: str, limit: int) -> list[dict] | None:
        key = self._key(symbol, tf, limit)
        entry = self._cache.get(key)
        if entry is None:
            return None
        # Проверка TTL
        if time.time() - entry.created_at > self._ttl_sec:
            del self._cache[key]
            return None
        entry.access_count += 1
        self._cache.move_to_end(key)
        return entry.data

    def set(self, symbol: str, tf: str, limit: int, data: list[dict]) -> None:
        key = self._key(symbol, tf, limit)
        self._cache[key] = CacheEntry(data=data)
        self._cache.move_to_end(key)
        # LRU eviction
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate(self, symbol: str, tf: str) -> None:
        """Инвалидировать все записи для symbol+tf (любой limit)."""
        prefix = f"{symbol}:{tf}:"
        keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._cache[k]

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def stats(self) -> dict:
        return {
            "size": self.size,
            "maxsize": self._maxsize,
            "ttl_sec": self._ttl_sec,
        }
```

**Критерий:** Кэш работает как LRU, поддерживает TTL, инвалидацию.

### Шаг 5.2 — Интегрировать кэш в VPSClient

**Файл:** `data/vps_client.py`

**Описание:** В `get_candles()` добавить параметр `use_cache=True`.

```python
def __init__(self, event_bus: EventBus) -> None:
    ...
    self._cache = CandlesCache(maxsize=100, ttl_sec=300)

async def get_candles(
    self, symbol: str, tf: str = "1m", limit: int = 500,
    market_type: str = "spot", use_cache: bool = True,
) -> list[Candle]:
    if use_cache:
        cached = self._cache.get(symbol, tf, limit)
        if cached is not None:
            return [Candle(**c) for c in cached]

    result = await self._rest_get("/api/candles", {
        "symbol": symbol, "tf": tf, "limit": str(limit),
        "market_type": market_type,
    })
    candles_data = result.get("candles", [])

    if use_cache:
        self._cache.set(symbol, tf, limit, candles_data)

    return [Candle(**c) for c in candles_data]
```

**Критерий:** Повторный запрос тех же свечей возвращается из кэша (latency <1ms).

### Шаг 5.3 — Инвалидация кэша при новых свечах

**Файл:** `data/vps_client.py`

**Описание:** При получении новой свечи через WS — инвалидировать кэш для этого symbol+tf.

```python
# В _on_message():
if data.get("type") in ("candle.1m.tick", "candle.1m.closed"):
    symbol = data.get("symbol", "")
    if symbol:
        self._cache.invalidate(symbol, "1m")
```

**Критерий:** После получения новой свечи кэш для этого symbol+tf очищается.

---

## Фаза 6: Оптимизация VPS

**Цель:** Обеспечить стабильную работу VPS (1 vCPU, 1GB RAM) под нагрузкой.
**Оценка:** 7ч
**Зависимости:** Фаза 1 (VPS работает)

### Шаг 6.1 — Добавить метрики в /metrics

**Файл:** `telemetry/server.py`

**Описание:** Расширить endpoint `/metrics` — добавить per-module CPU и RAM.

```python
@app.get("/metrics")
async def metrics(request: Request):
    _auth(request)
    import psutil
    proc = psutil.Process()
    return {
        "cpu_percent": psutil.cpu_percent(),
        "ram_percent": psutil.virtual_memory().percent,
        "ram_used_mb": round(psutil.virtual_memory().used / 1024 / 1024, 1),
        "process_cpu": proc.cpu_percent(),
        "process_ram_mb": round(proc.memory_info().rss / 1024 / 1024, 1),
        "disk_used_gb": round(psutil.disk_usage("/").used / 1024**3, 2),
        "disk_free_gb": round(psutil.disk_usage("/").free / 1024**3, 2),
        "uptime_sec": int(time.time() - psutil.boot_time()),
        "connections": len(_ws_clients),
        "events_per_min": _events_per_min(),
    }
```

**Критерий:** `/metrics` отдаёт полную картину нагрузки.

### Шаг 6.2 — Профилировать TF Aggregator

**Файл:** `data/tf_aggregator.py`

**Описание:** Добавить логирование времени выполнения агрегации.

```python
# В методе агрегации:
import time
t0 = time.monotonic()
# ... агрегация ...
elapsed = time.monotonic() - t0
if elapsed > 0.1:  # если >100ms — логировать
    log.warning(f"TF Aggregator: {symbol} {tf} занял {elapsed:.3f}с")
```

**Критерий:** В логах видны медленные агрегации.

### Шаг 6.3 — Оптимизировать batch-запись в БД

**Файл:** `storage/repositories/candles_repo.py`

**Описание:** Увеличить batch size и использовать `executemany`.

```python
# Текущий BATCH_SIZE
BATCH_SIZE = 500  # было 100

# Использовать INSERT INTO ... VALUES (...), (...), ... вместо executemany
async def upsert_many(self, candles: list[Candle]) -> int:
    if not candles:
        return 0
    from sqlalchemy import text
    async with factory() as session:
        processed = 0
        for i in range(0, len(candles), BATCH_SIZE):
            batch = candles[i : i + BATCH_SIZE]
            values = ",".join([
                f"(:s{i}, :tf{i}, :ot{i}, :o{i}, :h{i}, :l{i}, :c{i}, :v{i})"
            ])
            # ... batch insert ...
            processed += len(batch)
        await session.commit()
        return processed
```

**Критерий:** Вставка 1000 свечей занимает <1 сек (было >3 сек).

### Шаг 6.4 — Ограничить количество символов

**Файл:** `.env` на VPS

**Рекомендация:** Начать с 5 пар, добавить остальные после профилирования.

```ini
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT
```

**Критерий:** VPS стабильно работает с CPU <50%, RAM <500MB.

### Шаг 6.5 — Настроить swap на VPS

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

---

## Фаза 7: Data quality dashboard

**Цель:** Визуализировать качество данных по символам и таймфреймам.
**Оценка:** 6ч
**Зависимости:** Фаза 1 (VPS работает)

### Шаг 7.1 — Создать DataQualityView.tsx

**Файл:** `ui/react-app/src/components/DataQualityView.tsx` (новый)

**Описание:** Отдельная вкладка с историей trust_score, списком ошибок верификации.

```tsx
import { useState, useEffect } from 'react'
import { useStore } from '../store/useStore'

export default function DataQualityView() {
  const pulseState = useStore(s => s.pulseState)
  const [history, setHistory] = useState<any[]>([])

  // Накопление истории trust_score
  useEffect(() => {
    if (pulseState?.data_rows) {
      setHistory(prev => {
        const entry = {
          ts: Date.now(),
          rows: pulseState.data_rows,
        }
        return [...prev.slice(-100), entry]  // хранить последние 100 снимков
      })
    }
  }, [pulseState?.data_rows])

  // ... визуализация
}
```

**Критерий:** Пользователь видит историю trust_score за последние N снимков.

### Шаг 7.2 — Добавить вкладку в Sidebar

**Файл:** `ui/react-app/src/components/Sidebar.tsx`

**Описание:** Добавить пункт "Качество данных".

```tsx
{/* ... существующие пункты ... */}
<NavItem to="/data-quality" icon={BarChartIcon} label="Качество данных" />
```

**Критерий:** Пользователь может перейти на вкладку "Качество данных".

### Шаг 7.3 — График trust_score по времени

**Файл:** `ui/react-app/src/components/DataQualityView.tsx`

**Описание:** Использовать canvas/SVG для отрисовки графика trust_score.

```tsx
// Упрощённый график через div-бары
{history.map((entry, i) => (
  <div key={i} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
    <span style={{ width: 80, fontSize: 10, color: 'var(--text-muted)' }}>
      {new Date(entry.ts).toLocaleTimeString()}
    </span>
    {entry.rows.map((row: any) => (
      <div key={row.symbol + row.timeframe} style={{
        width: Math.max(row.trust_score / 2, 2),
        height: 12,
        background: row.trust_score >= 80 ? '#22c55e' : row.trust_score >= 50 ? '#eab308' : '#ef4444',
        borderRadius: 2,
      }} title={`${row.symbol} ${row.timeframe}: ${row.trust_score}%`} />
    ))}
  </div>
))}
```

**Критерий:** Пользователь видит динамику качества данных.

---

## Сводный план по фазам

| Фаза | Название | Часы | Зависимости | Результат |
|------|----------|------|-------------|-----------|
| 0 | Проверка Desktop (браузер) | 1-2 | — | UI работает корректно |
| 1 | Развёртывание VPS | 1.5-2 | Фаза 0 | VPS собирает данные |
| 2 | Heartbeat VPS → Desktop | 4-5 | Фаза 1 | Обнаружение проблем <10 сек |
| 3 | Graceful degradation | 6 | Фаза 2 | Безопасность при отказе VPS |
| 4 | Auto backfill | 4 | Фаза 1 | Автоподтягивание данных |
| 5 | Кэширование свечей | 4 | — | Быстрые повторные запросы |
| 6 | Оптимизация VPS | 7 | Фаза 1 | Стабильность под нагрузкой |
| 7 | Data quality dashboard | 6 | Фаза 1 | Прозра