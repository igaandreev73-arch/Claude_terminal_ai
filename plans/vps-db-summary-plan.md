# План: Сводка по БД в блоке VPS (PulseView)

## Мотивация
Текущий блок "БАЗА ДАННЫХ" показывает только 4 цифры (размер, свечи, стаканы, ликвидации). Нужна детальная сводка: spot vs futures, временной охват, активность ликвидаций.

---

## Шаг 1. Бэкенд — `/data/status` (telemetry/server.py)

### Изменить `_datastats()`
Добавить в возвращаемый словарь по каждому символу:
- `candles_spot` / `candles_futures` — раздельный подсчёт по `market_type`
- `ob_spot` / `ob_futures` — раздельный подсчёт снимков стакана по рынку
- `liq_last_hour` / `liq_last_day` — ликвидации за последний час/день
- `candles_per_day` — средняя скорость заполнения (candles / дни от первой свечи)

### Пример структуры ответа
```json
{
  "symbol": "BTC/USDT",
  "candles": 250000,
  "candles_spot": 150000,
  "candles_futures": 100000,
  "first_candle": "2026-03-01T00:00:00",
  "last_candle": "2026-04-30T23:59:00",
  "ob_snapshots": 50000,
  "ob_spot": 30000,
  "ob_futures": 20000,
  "liquidations": 150,
  "liq_last_hour": 2,
  "liq_last_day": 15,
  "candles_per_day": 2800,
  "trust_score": 95
}
```

### Файл
`telemetry/server.py` — функция `_datastats()`

---

## Шаг 2. Фронтенд — `useVpsTelemetry.ts`

### Добавить интерфейс `VpsSymbolDbStats`
```typescript
export interface VpsSymbolDbStats {
  symbol: string
  candles: number
  candles_spot: number
  candles_futures: number
  first_candle: string | null
  last_candle: string | null
  ob_snapshots: number
  ob_spot: number
  ob_futures: number
  liquidations: number
  liq_last_hour: number
  liq_last_day: number
  candles_per_day: number
  trust_score: number
}
```

### Файл
`ui/react-app/src/hooks/useVpsTelemetry.ts`

---

## Шаг 3. Фронтенд — `PulseView.tsx` (VpsServerBlock)

### Расширить блок "БАЗА ДАННЫХ"
Текущий блок (4 строки) заменить на детальную сводку:

```
┌──────────────────────────────────────────────────┐
│ БАЗА ДАННЫХ                                      │
│ ─── Сводка ───                                   │
│ Размер: 256.3 MB                                 │
│ Свечи: 1 250 000 (spot 750k / fut 500k)          │
│ Стаканы: 250 000 (spot 150k / fut 100k)          │
│ Ликвидации: 150 (за час: 2, за день: 15)         │
│                                                  │
│ ─── По символам ───                              │
│ BTC  │ свечи 250k  │ стаканы 50k  │ ликв 30  │95%│
│ ETH  │ свечи 240k  │ стаканы 48k  │ ликв 25  │94%│
│ SOL  │ свечи 230k  │ стаканы 45k  │ ликв 20  │93%│
└──────────────────────────────────────────────────┘
```

### Логика отображения
- **Сводка** — агрегированные цифры по всем символам
- **По символам** — таблица с колонками:
  - Символ (сокращённый, без /USDT)
  - Свечи всего (spot/futures split в скобках)
  - Снимки стакана всего (spot/futures split в скобках)
  - Ликвидации всего
  - Trust score с цветовой индикацией
- **Цветовая индикация** trust_score: зелёный > 90%, оранжевый > 70%, красный < 70%

### Файл
`ui/react-app/src/components/PulseView.tsx` — функция `VpsServerBlock()`

---

## Шаг 4. Тесты + коммит

1. Запустить 203 unit-теста (бэкенд)
2. Собрать фронтенд: `npm run build`
3. Коммит: `feat(ui): детальная сводка БД в блоке VPS PulseView`

---

## Файлы для изменения
| Файл | Изменения |
|------|-----------|
| `telemetry/server.py` | Расширить `_datastats()` — spot/futures split, liq за период |
| `ui/react-app/src/hooks/useVpsTelemetry.ts` | Добавить `VpsSymbolDbStats` |
| `ui/react-app/src/components/PulseView.tsx` | Расширить блок БАЗА ДАННЫХ |

## Что НЕ меняется
- Модули Analytics, Signals, Execution, Backtester, Storage
- Существующие тесты (только добавляются новые поля в ответ)
- Другие блоки PulseView
