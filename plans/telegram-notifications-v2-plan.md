# План: Telegram-уведомления 2.0

## Мотивация
Расширить Telegram-функционал: добавить бот-команды для запроса сводок, event-based оповещения о задачах/сбоях, улучшить дайджест, добавить тестирование.

---

## Текущее состояние

### Уже есть:
- `telemetry/watchdog.py` — мониторинг сервиса, свежести данных, диска, ежедневный дайджест в 09:00 UTC
- `core/telegram_notifier.py` — ALERT/RESOLVE с дедупликацией для Desktop
- `telemetry/server.py` — `_tg()`, `POST /telegram/test`, `POST /telegram/config`, `GET /telegram/status`

### Чего не хватает:
- Бот-команды (`/summary`, `/status`, `/health`)
- Оповещения о задачах (backfill, валидация)
- Оповещения о крупных ликвидациях
- Оповещения о gap'ах в данных
- Тестирование уведомлений

---

## Компонент 1: Telegram Bot Commands

### Новый файл: `telemetry/tg_bot.py`
```python
class TelegramBot:
    """Long-polling Telegram бот для команд."""
    
    async def start(self): ...
    async def stop(self): ...
    async def _poll_loop(self):
        # Каждые 5 сек проверяет updates
        # Обрабатывает команды: /summary, /status, /health, /symbols, /help
    async def _handle_summary(self) -> str:
        # Берёт данные из _datastats() + _sys() + _dbstats()
        # Формирует HTML-сообщение со сводкой
    async def _handle_status(self) -> str:
        # Статус сервисов, WS, watchdog
    async def _handle_health(self) -> str:
        # CPU, RAM, диск, uptime
```

### Команды бота:
| Команда | Описание | Пример ответа |
|---------|----------|---------------|
| `/summary` | Сводка по БД | Размер, свечи (spot/fut), стаканы (spot/fut), ликвидации, диск |
| `/status` | Статус сервисов | Collector: active, WS: connected, Watchdog: running |
| `/health` | Здоровье системы | CPU 23%, RAM 45%, Диск 62%, Uptime 12d |
| `/symbols` | Пары с trust_score | BTC 95%, ETH 94%, SOL 93% |
| `/help` | Список команд | /summary, /status, /health, /symbols |

### Интеграция в `main.py`:
```python
from telemetry.tg_bot import TelegramBot
tg_bot = TelegramBot()
asyncio.create_task(tg_bot.start())
# ... в stop:
await tg_bot.stop()
```

---

## Компонент 2: Event-based Notifications

### В `main.py` — подписки на EventBus:

```python
# Завершение backfill
async def _on_task_completed(event):
    d = event.data
    if d.get("type") == "backfill":
        await _tg(f"✅ Backfill {d['symbol']} завершён: +{d['count']} свечей")

# Ошибка backfill  
async def _on_task_failed(event):
    d = event.data
    await _tg(f"❌ Ошибка backfill {d['symbol']}: {d['error']}")

# Ошибка валидации
async def _on_validation_error(event):
    d = event.data
    await _tg(f"⚠️ Валидация {d['symbol']}: {d['error']}")

# Gap в данных
async def _on_data_gap(event):
    d = event.data
    await _tg(f"🕳 Пропуск данных {d['symbol']}: {d['count']} свечей ({d['from']} - {d['to']})")

# Крупная ликвидация (> $100k)
async def _on_liquidation(event):
    d = event.data
    value = d.get("value_usd") or 0
    if value > 100_000:
        await _tg(f"💥 Ликвидация {d['symbol']} {d['side']} ${value:,.0f}")

# WS disconnected
async def _on_ws_disconnected(event):
    d = event.data
    await _tg(f"⚠️ {d.get('name', 'WS')} отключён, реконнект через {d.get('reconnect_in', '?')}с")
```

### Логика:
- ALERT только при ошибках/аномалиях (норма — тишина)
- Ликвидации — только > $100k (настраиваемый порог)
- WS disconnected — ALERT, WS connected — RESOLVE (уже есть в watchdog)

---

## Компонент 3: Улучшение дайджеста

### В `telemetry/watchdog.py` — расширить ежедневный дайджест:
```python
# Текущий дайджест:
# 🕯 Свечей: 1 250 000
# 📖 Снимков стакана: 250 000
# 💥 Ликвидаций: 150
# 💾 БД: 256.3 MB | Диск: 62%

# Новый дайджест:
# 📊 Ежедневный дайджест VPS
# ━━━━━━━━━━━━━━━━━━
# 🕯 Свечи: 1 250 000 (spot 750k / fut 500k)
# 📖 Стаканы: 250 000 (spot 150k / fut 100k)
# 💥 Ликвидации: 150 (за сутки: 15)
# 💾 БД: 256.3 MB | Диск: 62% (свободно 18.5 GB)
# ⏱ Uptime: 12d 4h
# ━━━━━━━━━━━━━━━━━━
```

---

## Компонент 4: REST endpoint для тестирования

### В `telemetry/server.py` — добавить:
```python
@app.post("/telegram/test/alert")
async def tg_test_alert(body: TgTestAlert, request: Request):
    """Симулирует ALERT: ws_down, disk_full, data_stale, liq_high"""
    _auth(request)
    msg = _simulate_alert(body.type)
    ok = await _tg(msg)
    return {"ok": ok, "type": body.type, "sent": msg[:80]}

@app.post("/telegram/test/resolve")
async def tg_test_resolve(body: TgTestResolve, request: Request):
    """Симулирует RESOLVE"""
    _auth(request)
    msg = _simulate_resolve(body.type)
    ok = await _tg(msg)
    return {"ok": ok, "type": body.type, "sent": msg[:80]}
```

---

## Компонент 5: Скрипт тестирования

### Новый файл: `scripts/test_alerts.py`
```python
# Тестирует:
# 1. Симуляция отключения WS → ALERT
# 2. Симуляция восстановления WS → RESOLVE
# 3. Симуляция переполнения диска → ALERT
# 4. Симуляция ошибки backfill → ALERT
# 5. Симуляция крупной ликвидации → ALERT
# 6. Проверка /summary → ответ
# 7. Проверка /status → ответ
```

---

## Порядок реализации

| Шаг | Что делаем | Файлы | Оценка |
|-----|-----------|-------|--------|
| 1 | Telegram Bot Commands | `telemetry/tg_bot.py` (новый), `main.py` | ~2ч |
| 2 | Event-based Notifications | `main.py` | ~1ч |
| 3 | Улучшение дайджеста | `telemetry/watchdog.py` | ~30м |
| 4 | REST endpoint тестирования | `telemetry/server.py` | ~30м |
| 5 | Скрипт тестирования | `scripts/test_alerts.py` (новый) | ~1ч |
| 6 | Тесты + коммит | — | ~30м |

---

## Дополнительные идеи (на будущее)

1. **Оповещения о крупных движениях рынка** — BTC > 3% за 5 мин
2. **Оповещения об аномалиях** — spike/flash crash от AnomalyDetector
3. **Оповещения о сигналах стратегий** — новая торговая идея
4. **Еженедельный отчёт** — по воскресеньям: статистика за неделю
5. **Оповещение о rate limit** —接近 лимита API
6. **Оповещение о частых реконнектах** — > N переподключений WS за час

---

## Файлы для изменения/создания
| Файл | Статус | Изменения |
|------|--------|-----------|
| `telemetry/tg_bot.py` | **Новый** | Telegram Bot Commands |
| `telemetry/server.py` | Изменить | REST endpoint для тестирования |
| `telemetry/watchdog.py` | Изменить | Расширенный дайджест |
| `main.py` | Изменить | Подписки на события + запуск бота |
| `scripts/test_alerts.py` | **Новый** | Скрипт тестирования уведомлений |

## Что НЕ меняется
- Модули Analytics, Signals, Execution, Backtester, Storage
- Существующие тесты
- UI/фронтенд
