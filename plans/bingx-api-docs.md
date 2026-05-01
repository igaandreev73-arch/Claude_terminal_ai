# 📘 BingX API Документация

**Дата:** 2026-05-01  
**Источники:** Официальная документация BingX, эмпирические тесты (`scripts/test_bingx_depth.py`, `scripts/test_bingx_klines.py`)  
**Версия API:** v2 / v3 Swap (фьючерсы), v1 Spot  
**Базовый URL:** `https://open-api.bingx.com`

---

## 1. 🚀 Быстрый старт

### Базовые URL

| Среда | Base URL | Назначение |
|-------|----------|------------|
| **Production** | `https://open-api.bingx.com` | Реальная торговля |
| **Demo** | `https://open-api-vst.bingx.com` | Тестовая среда (симуляция) |

### Rate Limits

| Лимит | Значение | Описание |
|-------|----------|----------|
| **IP (публичные)** | 2,000 запросов / 10 сек | Общий лимит на рыночные данные |
| **UID (приватные)** | 5–10 запросов / сек | Зависит от эндпоинта |
| **Торговля спот** | 5 ордеров / сек | |
| **Торговля фьючерсы** | 10 ордеров / сек | |

---

## 2. 🔑 Авторизация (REST)

Для **приватных** запросов (баланс, ордера, история) необходимы:

| Параметр | Описание |
|----------|----------|
| `X-BX-APIKEY` | API Key в заголовке запроса |
| `timestamp` | Unix timestamp в миллисекундах. Сервер отклоняет запросы старше 5000 мс |
| `signature` | HMAC-SHA256 от отсортированной строки параметров + секретный ключ |

**Реализация в проекте:** [`data/bingx_rest.py`](../data/bingx_rest.py) — метод `_sign()` (строка 150) и `_signed_get()` (строка 159).

---

## 3. 📊 Спот (Spot) API

### 3.1 Публичные эндпоинты

Лимит: **500 запросов / 10 сек** (общий IP-лимит).

| Эндпоинт | Метод | Описание | Используется в проекте |
|----------|-------|----------|----------------------|
| `/openApi/spot/v1/market/symbols` | GET | Список торговых пар | ❌ Нет |
| `/openApi/spot/v1/market/ticker/24hr` | GET | 24hr статистика | ❌ Нет |
| `/openApi/spot/v1/market/depth` | GET | Стакан (книга ордеров) | ❌ Нет (только WS) |
| `/openApi/spot/v1/market/trades` | GET | Последние сделки | ❌ Нет (только WS) |
| `/openApi/spot/v1/market/kline` | GET | **Свечные данные (история)** | ❌ Не используется |
| `/openApi/market/his/v1/kline` | GET | **Spot Historical K-line** | ⚠️ Протестирован, не даёт преимущества |

**Spot Historical K-line (`/openApi/market/his/v1/kline`):**
- Формат ответа: **массив массивов** (не объект с `data`) — отличается от Swap endpoint'ов
- Глубина: ~та же, что у v3 Swap (~424 дня для 1m)
- **Не даёт преимущества** перед Swap endpoint'ом — используем единый `/openApi/swap/v3/quote/klines`

### 3.2 Приватные эндпоинты

| Эндпоинт | Лимит | Описание |
|----------|-------|----------|
| `/openApi/spot/v1/account/balance` | 5/сек | Баланс аккаунта |
| `/openApi/spot/v1/trade/order` | 5/сек | Создание ордера |
| `/openApi/spot/v1/trade/cancel` | 5/сек | Отмена ордера |
| `/openApi/spot/v1/trade/openOrders` | 10/сек | Текущие открытые ордера |
| `/openApi/spot/v1/trade/historyOrders` | 10/сек | История ордеров (макс 7 дней) |
| `/openApi/spot/v1/trade/myTrades` | 5/сек | История сделок (макс 7 дней) |

---

## 4. 📈 Фьючерсы / Swap API

### 4.1 Публичные эндпоинты — рыночные данные

Лимит: **500 запросов / 10 сек** (общий IP-лимит).

#### Свечи (Klines / Candlestick)

| Эндпоинт | Версия | Глубина 1m | Глубина 1h | Глубина 1d | Используется |
|----------|--------|-----------|-----------|-----------|-------------|
| `/openApi/swap/v3/quote/klines` | **v3** | **~516 дней** (с 2024-11-30) | ~669 дней | ~668 дней | ✅ **Да** (`fetch_klines()`) |
| `/openApi/swap/v2/quote/klines` | **v2** | **~501 день** (с 2024-12-15) | ~668 дней | ~668 дней | ❌ Нет (v2 даёт меньше для 1m) |
| `/openApi/swap/v3/markPriceKlines` | v3 | **~30 дней** | ❌ | ❌ | ❌ Нет (мало данных) |

**Детали запроса:**
```
GET /openApi/swap/v3/quote/klines?symbol=BTC-USDT&interval=1m&startTime=1732982400000&endTime=1746057600000&limit=1440
```

**Параметры:**
| Параметр | Обязательный | Описание |
|----------|-------------|----------|
| `symbol` | Да | Торговая пара в формате `BTC-USDT` (дефис) |
| `interval` | Да | Таймфрейм: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1W` |
| `startTime` | Нет | Начало диапазона (Unix ms) |
| `endTime` | Нет | Конец диапазона (Unix ms) |
| `limit` | Нет | Макс. количество свечей (макс 1440) |

**Формат ответа:**
```json
{
  "code": 0,
  "msg": "",
  "data": [
    {
      "open": "45000.0",
      "high": "45200.0",
      "low": "44900.0",
      "close": "45100.0",
      "volume": "1234.5",
      "time": 1732982400000
    }
  ]
}
```

**Формат ответа v3 (объекты):**
```json
{
  "code": 0,
  "data": [
    { "open": "45000.0", "high": "45200.0", "low": "44900.0",
      "close": "45100.0", "volume": "1234.5", "time": 1732982400000 }
  ]
}
```

**Формат ответа v2 (массивы):**
```json
{
  "code": 0,
  "data": [
    [1732982400000, "45000.0", "45200.0", "44900.0", "45100.0", "1234.5", ...]
  ]
}
```

**Важно:** v3 API **НЕ** возвращает `openTime` как отдельное поле — только `time` (Unix ms).
v2 API возвращает массив массивов: `[time, open, high, low, close, volume, ...]` — порядок полей фиксированный.

#### Другие публичные эндпоинты

| Эндпоинт | Описание | Используется |
|----------|----------|-------------|
| `/openApi/swap/v2/quote/contracts` | Информация о контрактах | ❌ Нет |
| `/openApi/swap/v2/quote/price` | Последняя цена | ❌ Нет (только WS) |
| `/openApi/swap/v2/quote/fundingRate` | **Ставка финансирования** (возвращает **массив из 4 последних значений**, а не одно) | ✅ `fetch_funding_rate()` |
| `/openApi/swap/v2/quote/openInterest` | **Открытый интерес** (⚠️ **параметр `startTime` игнорируется** — всегда возвращает текущее значение) | ✅ `fetch_open_interest()` |
| `/openApi/swap/v2/quote/premiumIndex` | Premium Index (markPrice, indexPrice) | ❌ Нет |
| `/openApi/swap/v2/quote/ticker` | 24h тикер | ❌ Нет |

### 4.2 Приватные эндпоинты — фьючерсы

| Эндпоинт | Лимит | Описание | Используется |
|----------|-------|----------|-------------|
| `/openApi/swap/v2/user/balance` | 5/сек | Баланс фьючерсного счёта | ❌ Нет |
| `/openApi/swap/v2/user/positions` | 5/сек | Текущие позиции | ❌ Нет |
| `/openApi/swap/v2/trade/order` | 10/сек | Создание ордера | ✅ `BingXPrivateClient.place_order()` |
| `/openApi/swap/v2/trade/cancel` | 10/сек | Отмена ордера | ✅ `BingXPrivateClient.cancel_order()` |
| `/openApi/swap/v2/trade/forceOrders` | ? | **Ликвидации** (force orders) | ✅ `fetch_force_orders()` |
| `/openApi/swap/v2/user/income` | 5/сек | История PnL (макс 3 мес.) | ❌ Нет |
| `/openApi/swap/v2/trade/fullTradeList` | ? | Свои сделки (приватный) | ❌ Нет |

### 4.3 Глубина исторических данных (эмпирические тесты)

Результаты тестирования [`scripts/test_bingx_depth.py`](../scripts/test_bingx_depth.py):

| Таймфрейм | v3 Swap | v2 Swap | Mark Price Klines |
|-----------|---------|---------|-------------------|
| **1m** | **~516 дней** (с 2024-11-30) | ~501 день | ~30 дней |
| **5m** | ~669 дней | ~669 дней | ❌ |
| **15m** | ~669 дней | ~669 дней | ❌ |
| **1h** | **~669 дней** | ~668 дней | ❌ |
| **4h** | ~668 дней | ~668 дней | ❌ |
| **1d** | **~668 дней** | ~668 дней | ❌ |
| **1W** | ❌ **Нет данных** | ❌ Нет данных | ❌ |

**Ключевые выводы:**
- v3 1m даёт **516 дней** — достаточно для backfill
- Старшие таймфреймы (5m+) хранятся **глубже** (669 дней), чем 1m (516 дней)
- **1W данных нет нигде** — нужно агрегировать из 1d
- Mark Price Klines даёт только ~30 дней — бесполезно

---

## 5. 🛠️ Управление кошельком и аккаунтом

| Эндпоинт | Описание | Лимит |
|----------|----------|-------|
| `/openApi/wallets/v1/capital/withdraw/apply` | Вывод средств | 2/сек |
| `/openApi/api/v3/capital/deposit/hisrec` | История депозитов | 10/сек |
| `/openApi/subAccount/v1/list` | Список суб-аккаунтов | 1/сек |
| `/openApi/api/v3/post/asset/transfer` | Внутренний перевод (Спот ↔ Фьючерс) | 2/сек |

---

## 6. 🔌 WebSocket API

### 6.1 Спот (Spot)

Подключение: `wss://ws-api.bingx.com/market`

| Канал | Формат | Событие в проекте | Описание |
|-------|--------|-------------------|----------|
| Kline 1m | `{symbol}@kline_1min` | `candle.1m.tick` / `candle.1m.closed` | Свечи 1m в реальном времени |
| Depth 20 | `{symbol}@depth20` | `orderbook.update` | Стакан 20 уровней |
| Trade | `{symbol}@trade` | `trade.raw` | Сделки в реальном времени |

Реализация: [`data/bingx_ws.py`](../data/bingx_ws.py)

### 6.2 Фьючерсы (Futures / Swap)

Подключение: `wss://ws-api.bingx.com/swap/market`

| Канал | Формат | Событие в проекте | Описание |
|-------|--------|-------------------|----------|
| Kline 1m | `{symbol}@kline_1min` | `futures.candle.1m.tick` / `futures.candle.1m.closed` | Свечи 1m в реальном времени |
| Depth 20 | `{symbol}@depth20` | `futures.orderbook.update` | Стакан 20 уровней |
| Trade | `{symbol}@trade` | `futures.trade.raw` | Сделки в реальном времени |

**Важно:** Канал `@forceOrder` (ликвидации) **НЕ СУЩЕСТВУЕТ** у BingX Futures WebSocket.  
Ликвидации доступны только через REST polling: `GET /openApi/swap/v2/trade/forceOrders`.

Реализация: [`data/bingx_futures_ws.py`](../data/bingx_futures_ws.py)

---

## 7. 📋 Сводная таблица: какие эндпоинты используются в проекте

| Эндпоинт | Модуль | Метод | Тип |
|----------|--------|-------|-----|
| `/openApi/swap/v3/quote/klines` | `BingXRestClient` | `fetch_klines()` | Публичный |
| `/openApi/swap/v2/quote/openInterest` | `BingXRestClient` | `fetch_open_interest()` | Публичный |
| `/openApi/swap/v2/quote/fundingRate` | `BingXRestClient` | `fetch_funding_rate()` | Публичный |
| `/openApi/swap/v2/trade/forceOrders` | `BingXRestClient` | `fetch_force_orders()` | Приватный |
| `/openApi/swap/v2/trade/order` | `BingXPrivateClient` | `place_order()` | Приватный |
| `/openApi/swap/v2/trade/cancel` | `BingXPrivateClient` | `cancel_order()` | Приватный |

---

## 8. ⚠️ Ограничения и особенности

### 8.1 Ограничения по глубине данных

| Данные | Доступно для backfill | Причина |
|--------|----------------------|---------|
| Свечи 1m futures | ✅ ~516 дней (v3) | Ограничение API |
| Свечи 1m spot | ✅ ~424 дня (v3) | Ограничение API |
| Order book (история) | ❌ **Только онлайн** | BingX не хранит историю стакана |
| Сделки (trades, история) | ❌ **Только онлайн** | Нет REST endpoint'а |
| Open Interest (история) | ❌ **Только онлайн** | History endpoint'ы не существуют |
| Funding Rate (история) | ⚠️ **4 последних значения** | REST возвращает только 4 |
| Ликвидации (история) | ✅ **Есть** | `startTime` работает |
| 1W свечи | ❌ **Нет данных** | Агрегировать из 1d |

### 8.2 Особенности реализации

1. **Единый REST endpoint для spot и futures** — `/openApi/swap/*` используется для обоих рынков. Разделение идёт только на уровне WebSocket.
2. **v3 vs v2 API** — v3 возвращает объекты `{open, high, low, close, volume, time}`, v2 возвращает массивы `[time, open, high, low, close, volume, ...]`. v3 имеет чуть больше глубины для 1m.
3. **Формат symbol** — в REST используется дефис (`BTC-USDT`), в WebSocket — слэш (`BTC/USDT`).
4. **`limit=1440`** — максимальное количество свечей за один запрос (ровно 1 день для 1m).
5. **Force orders (ликвидации)** — `startTime` работает, но количество записей в одном ответе ограничено. Нужно пагинировать по `startTime`.
6. **Funding Rate (`/openApi/swap/v2/quote/fundingRate`)** — возвращает **массив из 4 последних значений** (не одно). Каждое значение содержит `fundingTime`. Это даёт историю за ~32 часа (4 ставки × 8 часов). History endpoint'ы (`fundingRateHistory`, `fundingRate/history`) **НЕ СУЩЕСТВУЮТ** — проверено эмпирически.
7. **Open Interest (`/openApi/swap/v2/quote/openInterest`)** — параметр `startTime` **игнорируется**. Всегда возвращает текущее значение OI + timestamp. History endpoint'ы (`openInterest/history`, `openInterestHistory`) **НЕ СУЩЕСТВУЮТ** — проверено эмпирически.
8. **Spot Historical K-line (`/openApi/market/his/v1/kline`)** — формат ответа: **массив массивов** (не объект с `data`). Глубина ~та же, что у v3 Swap. Не даёт преимущества — используем единый Swap endpoint.

---

## 9. 🔄 Стратегия получения данных (рекомендуемая)

```
Для backfill 1m ИСПОЛЬЗОВАТЬ: v3 API (516 дней)
Для backfill 1d ИСПОЛЬЗОВАТЬ: v3 API (668 дней)
Для 5m/15m/1h/4h: агрегировать из 1m локально (через tf_aggregator)
Для 1W: агрегировать из 1d
Для order book: ТОЛЬКО онлайн (WebSocket)
Для trades: ТОЛЬКО онлайн (WebSocket)
Для OI: ТОЛЬКО онлайн (REST polling)
Для funding rate: REST polling (4 последних) + онлайн
Для ликвидаций: REST backfill + REST polling
```
