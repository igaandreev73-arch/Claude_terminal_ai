# План: Следующие шаги после перестройки VPS-сборщика

**Дата:** 2026-05-02
**Статус VPS:** Collector + API работают, БД 7.4M свечей

---

## 1. 🎯 Приоритеты

| Приоритет | Задача | Зачем |
|-----------|--------|-------|
| **P0** | Агрегация таймфреймов (1m → 5m, 15m, 1h, 4h, 1d, 1W) | Без этого нет аналитики на старших ТФ |
| **P1** | Подключение Desktop к VPS | Terminal mode не работает без VPSClient |
| **P2** | Починить trades_raw = 0 | Потеря данных о сделках |
| **P3** | Проверить liquidations | Убедиться что REST polling работает |
| **P4** | Добавить /api/validate и /api/restart в server.py | Управление VPS с Desktop |
| **P5** | Автоматическая агрегация на VPS (systemd таймер) | Не требует ручного запуска |

---

## 2. 📋 Детальный план по фазам

### Фаза 5: Агрегация таймфреймов на Desktop

**Проблема:** [`scripts/aggregate_timeframes.py`](../scripts/aggregate_timeframes.py) использует прямой `sqlite3.connect()` и жёстко зашитый путь `/opt/collector/data/terminal.db`. Несовместим с текущей архитектурой (SQLAlchemy async).

**Решение:** Создать новый скрипт `scripts/aggregate_vps.py`, который:
- Подключается к VPS через REST API (`/api/candles`)
- Скачивает 1m свечи порциями
- Агрегирует в старшие ТФ на Desktop
- Сохраняет в локальную БД Desktop через `CandlesRepository`

**Почему через REST, а не напрямую к БД VPS:**
- VPS — dumb pipe, не должен заниматься агрегацией
- Desktop получает данные через тот же канал, что и UI
- Не нужно открывать доступ к БД VPS

```
Desktop (aggregate_vps.py)
  │
  ├── GET /api/candles?symbol=X&tf=1m&limit=1000  (VPS REST)
  ├── Агрегация в 5m, 15m, 1h, 4h, 1d, 1W
  └── Сохранение в локальную БД Desktop (CandlesRepository)
```

**Шаги:**
1. Создать `scripts/aggregate_vps.py` с использованием `VPSClient.get_candles()`
2. Реализовать агрегацию: группировка по bucket, OHLCV
3. Сохранять через `CandlesRepository.upsert_many()`
4. Запустить для spot + futures, всех 5 символов
5. Проверить результат через `check_tables.py`

**Оценка:** ~30 минут на 5 символов × 2 market_type (скачивание + агрегация)

---

### Фаза 6: Подключение Desktop к VPS

**Проблема:** Desktop не может запуститься в terminal mode, т.к. VPSClient не настроен.

**Что нужно сделать:**

#### 6.1 Настроить `.env` на Desktop
```env
# VPS connection
VPS_HOST=194.238.29.158
VPS_PORT=8800
VPS_API_KEY=<тот же что на VPS>
VPS_WS_URL=ws://194.238.29.158:8800/ws
VPS_URL=http://194.238.29.158:8800
```

#### 6.2 Проверить `main.py` terminal mode
Убедиться, что при `RUN_MODE=terminal`:
- `VPSClient` создаётся и подключается
- WS-события от VPS публикуются в локальный Event Bus
- REST-запросы за историей идут на VPS, а не на BingX

#### 6.3 Тест
```bash
python main.py  # RUN_MODE=terminal по умолчанию на Desktop
# Должен подключиться к VPS WS, получать heartbeat
```

---

### Фаза 7: Починить trades_raw = 0

**Проблема:** Таблица `trades_raw` пуста, хотя WS подписан на `trade`.

**Где искать:**

1. [`bingx_ws.py:_on_trade()`](../data/bingx_ws.py:214) — публикует `trade.raw` в Event Bus
2. [`bingx_futures_ws.py:_on_trade()`](../data/bingx_futures_ws.py:248) — публикует `trade.raw` в Event Bus
3. [`main.py:_run_collector()`](../main.py:34) — должен быть подписчик на `trade.raw`

**Проверить:**
- Есть ли в `_run_collector()` подписка: `self._event_bus.subscribe("trade.raw", handler)`?
- Если нет — добавить обработчик, который сохраняет в `TradeRawModel`
- Если есть — проверить, не падает ли он с ошибкой (логи)

---

### Фаза 8: Проверить liquidations

**Проблема:** Таблица `liquidations` пуста.

**Возможные причины:**
- REST polling `forceOrders` работает, но ликвидаций просто не было на рынке
- Или polling не возвращает данные (ошибка аутентификации?)

**Проверить:**
```bash
# На VPS:
curl -s http://localhost:8800/metrics | grep liquidations
# Или в логах:
journalctl -u crypto-telemetry.service --since "1 hour ago" | grep -i liqui
```

---

### Фаза 9: API endpoints (опционально)

**Добавить в [`telemetry/server.py`](../telemetry/server.py):**

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/validate` | GET | Запустить валидацию данных на VPS |
| `/commands/restart/server` | POST | Перезапустить API-сервер |
| `/commands/restart/collector` | POST | Перезапустить collector (через systemctl) |

---

### Фаза 10: Автоматическая агрегация на VPS (опционально)

Если решим агрегировать на VPS:

```ini
# /etc/systemd/system/crypto-aggregator.service
[Unit]
Description=Crypto Telemetry Aggregator
After=crypto-telemetry.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /root/crypto-telemetry/scripts/aggregate_timeframes.py --market-type futures
ExecStart=/usr/bin/python3 /root/crypto-telemetry/scripts/aggregate_timeframes.py --market-type spot
```

```ini
# /etc/systemd/system/crypto-aggregator.timer
[Unit]
Description=Run aggregator every hour

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

---

## 3. 📊 Оценка времени

| Фаза | Задача | Время |
|------|--------|-------|
| 5 | Агрегация таймфреймов (скрипт + запуск) | 2-3 часа |
| 6 | Подключение Desktop к VPS | 1-2 часа |
| 7 | Починить trades_raw | 30 мин |
| 8 | Проверить liquidations | 15 мин |
| 9 | API endpoints | 1 час |
| 10 | Auto-aggregation (systemd) | 30 мин |

**Итого:** ~5-7 часов на всё

---

## 4. 🚨 Риски

| Риск | Вероятность | Mitigation |
|------|-------------|------------|
| VPS недоступен (SSH не проходит) | Средняя | Проверить через Telegram Bot /status |
| REST API VPS не отвечает на /api/candles с большими limit | Низкая | Использовать пагинацию (limit=1000) |
| Агрегация на Desktop займёт много времени | Низкая | 7.4M свечей × 2 запроса = ~15K запросов, ~5 мин |
| VPSClient не подключается (несовместимость версий) | Средняя | Проверить логи, обновить протокол |

---

## 5. ✅ Критерии успеха

- [ ] После агрегации: в БД Desktop есть свечи 5m, 15m, 1h, 4h, 1d, 1W для всех символов
- [ ] Desktop terminal mode запускается и получает данные с VPS
- [ ] `trades_raw` > 0 (появляются новые сделки)
- [ ] `liquidations` проверены (пусто = OK, нет ликвидаций)
- [ ] API VPS имеет endpoints для управления
