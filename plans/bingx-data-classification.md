# Классификация данных BingX: исторические vs реального времени

**Дата:** 2026-05-01  
**Цель:** Определить, какие данные можно получить задним числом (backfill), а какие — только в реальном времени через WebSocket.  
**Разделение:** Spot (спот) vs Futures (фьючерсы/swap) — у BingX это **разные WebSocket-соединения**, но **единые REST endpoint'ы**.

---

## Архитектура проекта

```
BingXWebSocket (data/bingx_ws.py)         → спотовые данные
  - {symbol}@kline_1min  → candle.1m.tick / candle.1m.closed
  - {symbol}@depth20     → orderbook.update
  - {symbol}@trade       → trade.raw

BingXFuturesWebSocket (data/bingx_futures_ws.py) → фьючерсные данные
  - {symbol}@kline_1min  → futures.candle.1m.tick / futures.candle.1m.closed
  - {symbol}@depth20     → futures.orderbook.update
  - {symbol}@trade       → futures.trade.raw

BingXRestClient (data/bingx_rest.py) → общий REST-клиент
  - /openApi/swap/v3/quote/klines       → свечи (и spot, и futures — единый endpoint)
  - /openApi/swap/v2/quote/openInterest → OI (только futures)
  - /openApi/swap/v2/quote/fundingRate  → funding rate (только futures)
  - /openApi/swap/v2/trade/forceOrders  → ликвидации (только futures, приватный)
```

**Важно:** BingX использует единый REST endpoint `/openApi/swap/*` для ВСЕХ данных — спот и фьючерсы не разделены на уровне REST API. Разделение идёт только на уровне WebSocket (разные подключения).

---

## Легенда

| Символ | Значение |
|--------|----------|
| ✅ Backfill | Можно получить за любой период в прошлом (в пределах глубины API) |
| ⚠️ Частично | Можно получить, но с ограничениями по глубине |
| ❌ Только онлайн | Нельзя получить задним числом — только streaming |
| 🔄 Агрегация | Можно вычислить из других данных |
| ❓ Не проверено | Нужно дополнительное исследование |

---

## 1. СВЕЧИ (Candles / Klines)

### 1.1 Спотовые свечи (Spot)

**REST:** `GET /openApi/swap/v3/quote/klines` (общий endpoint)  
**WebSocket:** `{symbol}@kline_1min` (через `BingXWebSocket`)  
**Событие:** `candle.1m.tick` / `candle.1m.closed`

| Таймфрейм | Статус | Глубина backfill | Endpoint | Примечание |
|-----------|--------|------------------|----------|------------|
| **1m** | ✅ Backfill | ~424 дня (с 2025-03-03) | v3 Swap | |
| **5m** | ⚠️ Частично | ~45 дней | v3 Swap | Лучше агрегировать из 1m |
| **15m** | ⚠️ Частично | ~14 дней | v3 Swap | Лучше агрегировать из 1m |
| **1h** | ⚠️ Частично | ~43 дня | v3 Swap | Лучше агрегировать из 1m |
| **1d** | ✅ Backfill | ~345 дней (с 2025-05-21) | v3 Swap | |
| **1W** | ❌ Нет данных | N/A | v3 Swap | Агрегировать из 1d |

**Дополнительно:** `GET /openApi/market/his/v1/kline` — Spot Historical K-line  
- Формат ответа: массив (не объект с `data`)  
- Глубина: ~та же, что у v3 Swap  
- **Не даёт преимущества** перед Swap endpoint'ом

### 1.2 Фьючерсные свечи (Futures / Swap)

**REST:** `GET /openApi/swap/v3/quote/klines` (тот же endpoint)  
**WebSocket:** `{symbol}@kline_1min` (через `BingXFuturesWebSocket`)  
**Событие:** `futures.candle.1m.tick` / `futures.candle.1m.closed`

| Таймфрейм | Статус | Глубина backfill | Endpoint | Примечание |
|-----------|--------|------------------|----------|------------|
| **1m** | ✅ Backfill | ~424 дня (v3) / **~501 день (v2)** | v3/v2 Swap | **v2 даёт больше** |
| **5m** | ⚠️ Частично | ~45 дней | v3 Swap | |
| **15m** | ⚠️ Частично | ~14 дней | v3 Swap | |
| **1h** | ⚠️ Частично | ~43 дня | v3 Swap | |
| **1d** | ✅ Backfill | ~345 дней | v3 Swap | |
| **1W** | ❌ Нет данных | N/A | v3 Swap | |

**Важное открытие:** v2 API (`/openApi/swap/v2/quote/klines`) даёт **на 77 дней больше** исторических данных для 1m, чем v3.

### 1.3 Рекомендация по свечам

```
Для backfill 1m ИСПОЛЬЗОВАТЬ: v2 API (больше глубина)
Для backfill 1d ИСПОЛЬЗОВАТЬ: v3 API
Для 5m/15m/1h: агрегировать из 1m (собственная реализация tf_aggregator)
Для 1W: агрегировать из 1d
```

---

## 2. СТАКАН (Order Book / Depth)

### 2.1 Спотовый стакан (Spot)

**REST:** `GET /openApi/swap/v2/quote/depth` (текущий снапшот)  
**WebSocket:** `{symbol}@depth20` (через `BingXWebSocket`)  
**Событие:** `orderbook.update`

| Тип | Статус | Примечание |
|-----|--------|------------|
| **Текущий снапшот** | ✅ Backfill (только сейчас) | Можно получить в любой момент, но **только текущее состояние** |
| **Исторический стакан** | ❌ Только онлайн | BingX НЕ хранит историю стакана |
| **Инкрементальные обновления** | ❌ Только онлайн | Только через WebSocket в реальном времени |

### 2.2 Фьючерсный стакан (Futures)

**REST:** `GET /openApi/swap/v2/quote/depth` (тот же endpoint)  
**WebSocket:** `{symbol}@depth20` (через `BingXFuturesWebSocket`)  
**Событие:** `futures.orderbook.update`

| Тип | Статус | Примечание |
|-----|--------|------------|
| **Текущий снапшот** | ✅ Backfill (только сейчас) | |
| **Исторический стакан** | ❌ Только онлайн | Аналогично spot |

**Вывод:** Order book — **только онлайн**. Для backtest'ов недоступен.  
Нужно запустить сбор заранее и накопить историю в БД.

---

## 3. СДЕЛКИ (Trades)

### 3.1 Спотовые сделки (Spot)

**WebSocket:** `{symbol}@trade` (через `BingXWebSocket`)  
**Событие:** `trade.raw`

| Тип | Статус | Примечание |
|-----|--------|------------|
| **Сделки реального времени** | ❌ Только онлайн | Каждая сделка приходит в реальном времени |
| **Исторические сделки** | ❌ Только онлайн | Нет REST endpoint'а для истории рыночных сделок |

### 3.2 Фьючерсные сделки (Futures)

**WebSocket:** `{symbol}@trade` (через `BingXFuturesWebSocket`)  
**Событие:** `futures.trade.raw`

| Тип | Статус | Примечание |
|-----|--------|------------|
| **Сделки реального времени** | ❌ Только онлайн | |
| **Исторические сделки** | ❌ Только онлайн | |

**Вывод:** CVD (Cumulative Volume Delta) — **только онлайн**, накапливается с момента запуска.  
Для backtest'ов CVD недоступен.

---

## 4. ЛИКВИДАЦИИ (Force Orders / Liquidations)

### Futures только

**REST:** `GET /openApi/swap/v2/trade/forceOrders` (приватный, HMAC-SHA256)  
**WebSocket:** Нет `@forceOrder` канала у BingX Futures

| Тип | Статус | Примечание |
|-----|--------|------------|
| **История ликвидаций** | ✅ Backfill | Есть параметр `startTime`. **Глубина неизвестна** — нужно проверить |
| **Текущие ликвидации** | ✅ Polling REST | Можно опрашивать каждые N секунд |

**Вывод:** Ликвидации можно получать как за прошлые периоды (backfill), так и в реальном времени через polling.  
Спотовых ликвидаций не существует (только futures).

---

## 5. ОТКРЫТЫЙ ИНТЕРЕС (Open Interest)

### Futures только

**REST:** `GET /openApi/swap/v2/quote/openInterest`

| Тип | Статус | Примечание |
|-----|--------|------------|
| **Текущий OI** | ✅ Backfill (только сейчас) | Возвращает текущее значение + timestamp. Параметр `startTime` **игнорируется** — всегда возвращает текущий OI |
| **Исторический OI** | ❌ Только онлайн | History endpoint'ы НЕ СУЩЕСТВУЮТ (проверены: `/v2/quote/openInterest/history`, `/v2/quote/openInterestHistory`, `/v3/quote/openInterest/history` — все вернули `"this api is not exist"`) |

**Вывод:** OI — **только текущее значение**. Исторического OI через REST API нет. Единственный способ — накапливать в реальном времени через polling.

---

## 6. СТАВКА ФИНАНСИРОВАНИЯ (Funding Rate)

### Futures только

**REST:** `GET /openApi/swap/v2/quote/fundingRate`

| Тип | Статус | Примечание |
|-----|--------|------------|
| **Текущая ставка** | ✅ Backfill | **Возвращает ПОСЛЕДНИЕ 4 ставки** (история!), а не только текущую. Есть `fundingTime` для каждой |
| **Историческая ставка** | ❌ Только онлайн | History endpoint'ы НЕ СУЩЕСТВУЮТ (проверены: `/v2/quote/fundingRateHistory`, `/v2/quote/fundingRate/history`, `/v3/quote/fundingRateHistory`) |

**Важно:** `GET /openApi/swap/v2/quote/fundingRate` возвращает **массив из 4 последних значений** (не одно). Это позволяет получить историю funding rate за ~32 часа (4 ставки × 8 часов). Но более старых данных через REST нет.

**Premium Index:** `GET /openApi/swap/v2/quote/premiumIndex` — работает, возвращает markPrice, indexPrice, lastFundingRate, nextFundingTime.

**Вывод:** Funding rate — можно получить 4 последних значения через REST. Для полной истории — только онлайн-сбор.

---

## 7. БАЗИС (Basis)

**Формула:** `Basis = Futures Price − Spot Price`

| Тип | Статус | Примечание |
|-----|--------|------------|
| **Исторический базис** | 🔄 Агрегация | Вычисляется из spot + futures свечей |
| **Базис реального времени** | 🔄 Агрегация | Вычисляется из spot + futures цен |

**Вывод:** Базис не требует отдельного хранения — вычисляется из свечей обоих рынков.

---

## 8. ДОПОЛНИТЕЛЬНЫЕ МЕТРИКИ

| Endpoint | Рынок | Тип | Статус |
|----------|-------|-----|--------|
| `GET /openApi/swap/v2/quote/ticker` | Оба | 24h тикер | ✅ Backfill (текущий) |
| `GET /openApi/swap/v2/quote/premiumIndex` | Futures | Premium index | ❓ Не проверено |
| `GET /openApi/swap/v2/quote/fundingRateHistory` | Futures | История funding rate | ❓ Не проверено |
| `GET /openApi/swap/v2/trade/fullTradeList` | Оба | Свои сделки (приватный) | ✅ Backfill |

---

## ИТОГОВАЯ ТАБЛИЦА

### Spot

| Данные | Backfill (история) | Онлайн (streaming) | Приоритет |
|--------|-------------------|--------------------|-----------|
| **Свечи 1m** | ✅ ~424 дня (v3) | ✅ WebSocket @kline_1min | 🔴 High |
| **Свечи 5m** | ⚠️ ~45 дней | 🔄 Агрегация из 1m | 🟢 Low |
| **Свечи 15m** | ⚠️ ~14 дней | 🔄 Агрегация из 1m | 🟢 Low |
| **Свечи 1h** | ⚠️ ~43 дня | 🔄 Агрегация из 1m | 🟢 Low |
| **Свечи 1d** | ✅ ~345 дней | 🔄 Агрегация из 1m | 🟡 Medium |
| **Свечи 1W** | ❌ Нет данных | 🔄 Агрегация из 1d | 🟢 Low |
| **Order book** | ❌ Только онлайн | ✅ WebSocket @depth20 | 🔴 High |
| **Сделки (trades)** | ❌ Только онлайн | ✅ WebSocket @trade | 🔴 High |

### Futures

| Данные | Backfill (история) | Онлайн (streaming) | Приоритет |
|--------|-------------------|--------------------|-----------|
| **Свечи 1m** | ✅ **~501 день (v2)** / ~424 дня (v3) | ✅ WebSocket @kline_1min | 🔴 High |
| **Свечи 5m** | ⚠️ ~45 дней | 🔄 Агрегация из 1m | 🟢 Low |
| **Свечи 15m** | ⚠️ ~14 дней | 🔄 Агрегация из 1m | 🟢 Low |
| **Свечи 1h** | ⚠️ ~43 дня | 🔄 Агрегация из 1m | 🟢 Low |
| **Свечи 1d** | ✅ ~345 дней | 🔄 Агрегация из 1m | 🟡 Medium |
| **Свечи 1W** | ❌ Нет данных | 🔄 Агрегация из 1d | 🟢 Low |
| **Order book** | ❌ Только онлайн | ✅ WebSocket @depth20 | 🔴 High |
| **Сделки (trades)** | ❌ Только онлайн | ✅ WebSocket @trade | 🔴 High |
| **Ликвидации** | ✅ Backfill (REST) | ✅ Polling REST | 🟡 Medium |
| **Open Interest** | ❓ Нужно проверить | ✅ REST (текущий) | 🟡 Medium |
| **Funding Rate** | ⚠️ 4 последних значения (32ч) | ✅ REST (текущий + история 4шт) | 🟡 Medium |
| **Базис** | 🔄 Из свечей | 🔄 Из свечей | 🟢 Low |

---

## РЕКОМЕНДАЦИИ

### Для backfill (в порядке приоритета)

1. **🔴 Свечи 1m futures через v2 API** — ~501 день, лучший вариант
2. **🟡 Свечи 1d через v3 API** — ~345 дней, для долгосрочного анализа
3. **🟡 Ликвидации через REST** — проверить глубину `startTime`
4. **🟡 Open Interest history** — найти endpoint, если существует
5. **🟢 Остальные таймфреймы** — агрегировать из 1m через `tf_aggregator`

### Для онлайн-сбора (уже реализовано)

| Компонент | Спот | Фьючерсы |
|-----------|------|----------|
| Свечи 1m | ✅ `BingXWebSocket` → `candle.1m.*` | ✅ `BingXFuturesWebSocket` → `futures.candle.1m.*` |
| Order book | ✅ `BingXWebSocket` → `orderbook.update` | ✅ `BingXFuturesWebSocket` → `futures.orderbook.update` |
| Сделки | ✅ `BingXWebSocket` → `trade.raw` | ✅ `BingXFuturesWebSocket` → `futures.trade.raw` |
| Ликвидации | ❌ Не применимо | ✅ `BingXRestClient` polling |
| Open Interest | ❌ Не применимо | ✅ `BingXRestClient` polling |
| Funding Rate | ❌ Не применимо | ✅ `BingXRestClient` polling |
| Базис | 🔄 `BasisCalculator` | 🔄 `BasisCalculator` |

### Что нужно доработать

- [ ] Переключить backfill 1m с v3 на v2 API для большей глубины
- [ ] Проверить глубину v2 API для 5m, 15m, 1h, 1d
- [x] Проверено: Open Interest history endpoint'ов НЕТ
- [x] Проверено: Funding Rate history endpoint'ов НЕТ
- [ ] Накапливать OI в real-time через polling (единственный способ)
- [ ] Накапливать Funding Rate в real-time через polling (единственный способ для полной истории)
- [ ] Проверить Spot Historical K-line на данных за 2020-2023
