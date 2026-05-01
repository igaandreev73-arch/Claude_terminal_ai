# Журнал разработки - 2026-04-29

## [Шаг 3-4] WS endpoint + /api/candles в telemetry/server.py
- **Время:** 17:40-17:42
- **Что сделано:
  - Переписан `telemetry/server.py` с использованием lifespan (вместо устаревшего on_event)
  - Добавлен WS endpoint `/ws` с аутентификацией (X-API-Key в query или JSON)
  - Добавлена фоновая задача `_broadcast_loop()` — подписка на Event Bus VPS и трансляция событий Desktop'у
  - Добавлен REST endpoint `GET /api/candles` для исторических данных
  - Добавлена функция `set_event_bus()` для подключения Event Bus из main.py
  - Добавлена функция `_serialise()` для JSON-сериализации данных
  - Добавлен `BROADCAST_EVENTS` — набор событий, транслируемых Desktop'у
  - WS поддерживает: auth, ping/pong, get_state, авто-реконнект
- **Файлы:** `telemetry/server.py`, `telemetry/server.tmp.py` (удалён)
- **Тесты:** 203/203 пройдены
- **Статус:** Готово

## [Шаг 5] Создать data/vps_client.py
- **Время:** 17:43
- **Что сделано:
  - Создан `VPSClient` — клиент Desktop для подключения к VPS
  - WS подключение к VPS :8800/ws с авто-реконнектом (экспоненциальная задержка)
  - Публикация событий VPS в локальный Event Bus Desktop'а
  - REST методы: get_candles(), get_status(), get_data_status(), get_health(), get_symbols(), start_backfill()
  - Ping-задача для поддержания WS соединения
  - Поддержка raw-подписчиков (on_raw_event)
- **Файлы:** `data/vps_client.py` (новый)
- **Тесты:** 203/203 пройдены
- **Статус:** Готово

## [Шаг 6] Рефакторинг main.py — два режима (collector/terminal)
- **Время:** 17:43-17:44
- **Что сделано:
  - `main.py` разделён на две функции: `_run_collector()` и `_run_terminal()`
  - **collector (VPS):** Data Layer + Telemetry API (FastAPI через uvicorn внутри asyncio)
  - **terminal (Desktop):** VPSClient + Analytics + Signals + Execution + UI
  - Используется `get_config()` из `core/config.py` для всех настроек
  - Импорты модулей — локальные (внутри функций) для избежания лишних зависимостей
- **Файлы:** `main.py`, `main.tmp.py` (удалён)
- **Тесты:** 203/203 пройдены
- **Статус:** Готово

## [Шаг 7] Обновить ui/ws_server.py
- **Время:** 17:44
- **Что сделано:
  - Проверено: WSServer уже корректно обрабатывает None для rest_client, watchdog, basis_calculator, data_verifier, ws_client, futures_ws
  - Изменений не потребовалось
- **Файлы:** `ui/ws_server.py` (без изменений)
- **Тесты:** 203/203 пройдены
- **Статус:** Готово

## [Шаг 8] Обновить фронтенд
- **Время:** 17:44-17:59
- **Что сделано:
  - `useVpsTelemetry.ts` — добавлена функция `fetchVpsCandles()` для прямого получения свечей с VPS REST API
  - Добавлен интерфейс `OHLCVBar` для типизации свечей
  - ChartView.tsx продолжает использовать локальный `localhost:8765` (данные в локальной БД Desktop)
- **Файлы:** `ui/react-app/src/hooks/useVpsTelemetry.ts`
- **Тесты:** 203/203 пройдены
- **Статус:** Готово

## [Шаг 9] Обновить deploy/ файлы
- **Время:** 17:59
- **Что сделано:
  - `crypto-telemetry.service` обновлён для запуска `main.py` в режиме collector
  - Добавлена переменная `RUN_MODE=collector` в Environment сервиса
  - Watchdog и Validator сервисы остались без изменений
- **Файлы:** `deploy/crypto-telemetry.service`
- **Тесты:** 203/203 пройдены
- **Статус:** Готово

## [Шаг 10] Проверить тесты
- **Время:** 17:59-18:01
- **Что сделано:** Запущены все 203 unit-теста
- **Результат:** 203 passed, 0 failed
- **Статус:** Готово

## [Финальная проверка] 2026-04-30 06:30 MSK
- **Что сделано:
  - Проверена архитектура: все 10 шагов миграции выполнены
  - `core/config.py` — AppConfig с RUN_MODE, VPS_HOST/PORT/API_KEY, is_collector/is_terminal, vps_url/vps_ws_url
  - `telemetry/server.py` — WS /ws (auth, ping/pong, get_state, broadcast loop) + REST /api/candles + set_event_bus()
  - `data/vps_client.py` — VPSClient: WS connect с авто-реконнектом, REST методы, публикация в Event Bus
  - `main.py` — _run_collector() (Data Layer + uvicorn) и _run_terminal() (VPSClient + Analytics + Execution + UI)
  - `ui/ws_server.py` — список соединений обновлён (vps_ws, vps_server, vps_db, bingx_private)
  - `PulseView.tsx` — fallback connections: ws_ui, vps_ws⚡, vps_server⚡, vps_db⚡, local_db, bingx_private⚡, fear_greed, news_feed
  - `useVpsTelemetry.ts` — добавлена fetchVpsCandles() для прямого REST к VPS
  - `deploy/crypto-telemetry.service` — RUN_MODE=collector
- **Тесты:** 203/203 пройдены (100%)
- **Статус:** ✅ Миграция завершена

## [Fix] Синхронизация блока "Соединения" на вкладке "Пульс" — 2026-04-30
- **Время:** 06:41-06:47
- **Что сделано:
  - Исправлена рассинхронизация между pulseState.connections (с бэкенда) и vpsStatus (polling VPS)
  - В `ConnectionsBlock()` добавлен мерж: VPS-соединения (vps_ws, vps_server, vps_db) берут stage из vpsActive
  - `local_db` берёт stage из connected (WS UI)
  - В `ui/ws_server.py` stage для VPS-соединений изменён с "stopped" на "unknown" (определяется на фронтенде)
  - Добавлен stage "unknown" с цветом var(--text-muted) и label "Ожидание"
- **Результат визуальной проверки:**
  - WebSocket UI: `Норма` ✅
  - WebSocket VPS: `unknown` ✅ (VPS не запущен)
  - Сервер VPS: `unknown` ✅
  - БД VPS: `unknown` ✅
  - Локальная БД: `Норма` ✅
  - BingX Private API: `Остановлен` ✅
- **Файлы:** `ui/react-app/src/components/PulseView.tsx`, `ui/ws_server.py`
- **Тесты:** 203/203 пройдены
- **Статус:** ✅ Готово

## [Фаза 0] Проверка Desktop (браузер) — 2026-04-30
- **Время:** 10:50-10:55 MSK
- **Что сделано:
  - Проверен процесс `main.py` (PID 11980 → 12964 → 5944 → перезапущен)
  - Запущены тесты: 203/203 пройдены ✅
  - Добавлен статический файл-сервер для React в `WSServer.start()`:
    - `add_static("/assets", ...)` — CSS/JS бандлы
    - `_serve_index()` — отдача `index.html` для SPA
  - Проверена Pulse-вкладка в браузере через Playwright:
    - Все 8 соединений отображаются корректно
    - VPS-соединения в статусе `unknown` (VPS не запущен — ожидаемо)
    - `local_db` — `Норма`, `ws_ui` — `Норма`
    - Блоки "Состояние модулей", "Очередь задач", "Критические события", "Состояние данных", "Поток событий" — все отображаются
- **Результат:** Фронтенд работает корректно. Добавлен скриншот `pulse-view-phase0.png`
- **Файлы:** `ui/ws_server.py` (добавлена статика), `plans/full-execution-plan.md`, `plans/roadmap-next-steps.md`
- **Тесты:** 203/203 пройдены
- **Статус:** ✅ Готово

## [UI] VPS Settings — финальная проверка + коммит — 2026-04-30
- **Время:** 18:15 MSK
- **Что сделано:**
  - Проверены все файлы: VpsSettingsModal.tsx, PulseView.tsx, useVpsTelemetry.ts, useStore.ts
  - Запущены 203 unit-теста — все пройдены (0 failures)
  - Подготовлен коммит с изменениями
- **Файлы:** `ui/react-app/src/components/VpsSettingsModal.tsx` (новый), `ui/react-app/src/components/PulseView.tsx`, `ui/react-app/src/store/useStore.ts`, `ui/react-app/src/hooks/useVpsTelemetry.ts`, `data/bingx_futures_ws.py`, `plans/full-execution-plan.md`
- **Тесты:** 203/203 passed
- **Статус:** ✅ Готово к пушу

## [UI] VPS Settings — модалка + параметризация — 2026-04-30
- **Время:** 14:00-14:10 MSK
- **Что сделано:**
  - Исправлен `useVpsTelemetry.ts` — теперь читает `vpsConfig` из store и передаёт в `fetchVpsStatus(url, apiKey)`
  - `ChartView.tsx` — заменён жёстко закодированный `REST_BASE` на `fetchVpsCandles(vpsConfig, ...)` с преобразованием `OHLCVBar.open_time` (ms) → `Candle.time` (s)
  - Фронтенд пересобран: `npm run build` — 0 ошибок
- **Файлы:** `ui/react-app/src/hooks/useVpsTelemetry.ts`, `ui/react-app/src/components/ChartView.tsx`
- **Тесты:** сборка прошла успешно
- **Статус:** ✅ Готово

## [Cleanup] Удалена бесполезная подписка @forceOrder — 2026-04-30
- **Время:** 23:50 MSK
- **Что сделано:**
  - Удалена подписка `{symbol}@forceOrder` из `_subscribe()` — BingX не поддерживает WS-канал ликвидаций
  - Удалён мёртвый метод `_on_liquidation()` — никогда не вызывался
  - Удалена ветка `@forceOrder` из `_handle_message()`
  - Обновлён docstring: убрано упоминание forceOrder, добавлено примечание про REST API
- **Файлы:** `data/bingx_futures_ws.py`
- **Тесты:** 203/203 passed (53.35s)
- **Статус:** ✅ Готово

## [Cleanup] REST polling ликвидаций (forceOrders) — 2026-04-30
- **Время:** 00:14 MSK
- **Что сделано:**
  - В `BingXRestClient` добавлены:
    - `_sign()` — HMAC-SHA256 подпись для приватных запросов
    - `_signed_get()` — GET с подписью и X-BX-APIKEY
    - `fetch_force_orders(symbol, limit, start_time, auto_close_type)` — опрос `/openApi/swap/v2/trade/forceOrders`
  - В `_run_collector()` (main.py) добавлена фоновая задача `_poll_liquidations_loop()`:
    - Каждые 60с опрашивает forceOrders для всех symbols
    - Парсит ответ и публикует `futures.liquidation` в EventBus
    - Существующий обработчик `_on_liquidation` сохраняет в БД
  - API-ключи читаются из `AppConfig` (BINGX_API_KEY / BINGX_API_SECRET)
- **Файлы:** `data/bingx_rest.py`, `main.py`
- **Тесты:** 203/203 passed (52.31s)
- **Статус:** ✅ Готово

## [TG Bot] Telegram Bot Commands — 2026-05-01
- **Время:** 13:50 MSK
- **Что сделано:**
  - Создан `telemetry/tg_bot.py` — Telegram Bot с long polling
  - Команды: `/summary` (сводка БД), `/status` (статус сервисов), `/health` (CPU/RAM/диск), `/symbols` (пары с trust), `/help`
  - Интегрирован в `main.py` — запуск в collector mode, остановка при сигнале
  - Использует существующие функции `_datastats()`, `_dbstats()`, `_svc()`, `_sys()`
- **Файлы:** `telemetry/tg_bot.py` (новый), `main.py`
- **Тесты:** 203/203 passed (57s)
- **Статус:** ✅ Готово

## [Telegram Notifications 2.0] Компоненты 2-5 — 2026-05-01
- **Время:** 14:45 MSK
- **Что сделано:**
  - **Компонент 2 (Event-based Notifications):** Добавлены подписки в `main.py`:
    - `backfill.complete` / `backfill.error` — уведомления о бэкфилле
    - `validation.result` — уведомления об ошибках валидации
    - `futures.liquidation` — крупные ликвидации >$100k
    - `watchdog.degraded/lost/dead` — отключение WS
    - `watchdog.recovered` / `watchdog.reconnecting` — восстановление WS
  - **Компонент 3 (Улучшение дайджеста):** Расширен ежедневный дайджест в `telemetry/watchdog.py`:
    - Split spot/futures для свечей и стаканов
    - Ликвидации за последние 24 часа
    - Uptime сервера
    - Свободное место на диске в GB
  - **Компонент 4 (REST endpoint тестирования):** Добавлены в `telemetry/server.py`:
    - `POST /telegram/test/alert` — симуляция ALERT (5 типов)
    - `POST /telegram/test/resolve` — симуляция RESOLVE (3 типа)
    - Функции `_simulate_alert()` и `_simulate_resolve()`
  - **Компонент 5 (Скрипт тестирования):** Создан `scripts/test_alerts.py`:
    - Тестирует все типы ALERT/RESOLVE через REST API
    - Проверяет команды бота /summary, /status
    - Проверяет конфигурацию Telegram
    - Цветной вывод с эмодзи
- **Файлы:** `main.py`, `telemetry/watchdog.py`, `telemetry/server.py`, `scripts/test_alerts.py` (новый)
- **Тесты:** 203/203 passed (52s)
- **Статус:** ✅ Готово

## [Docs] BingX API Documentation — 2026-05-01
- **Время:** 18:45 MSK
- **Что сделано:
  - Создана структурированная документация BingX API в `plans/bingx-api-docs.md`
  - Документация включает:
    - Быстрый старт: базовые URL, rate limits
    - Авторизация (REST): HMAC-SHA256 подпись
    - Спот API: публичные и приватные эндпоинты
    - Фьючерсы API: v2/v3 клaйны, глубина данных (эмпирические тесты)
    - WebSocket API: спот и фьючерсы
    - Сводная таблица используемых эндпоинтов
    - Ограничения и особенности
    - Рекомендуемая стратегия получения данных
  - Документация основана на:
    - Эмпирических тестах `scripts/test_bingx_depth.py`
    - Текущей реализации `data/bingx_rest.py`, `data/bingx_futures_ws.py`, `data/bingx_ws.py`
    - Официальной документации BingX
- **Файлы:** `plans/bingx-api-docs.md` (новый)
- **Тесты:** не требуются (документация)
- **Статус:** ✅ Готово
