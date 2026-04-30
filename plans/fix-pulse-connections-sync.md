# План исправления: синхронизация блока "Соединения" на вкладке "Пульс"

**Основание:** При визуальном осмотре страницы PulseView обнаружена рассинхронизация между двумя источниками данных о статусе соединений.

**Дата:** 2026-04-30

---

## Текущая проблема

### Как работает сейчас

В [`ConnectionsBlock()`](ui/react-app/src/components/PulseView.tsx:107) есть **два источника** данных о соединениях:

```typescript
// Источник 1 — с бэкенда через WS (pulse_state)
const pulseState = useStore(s => s.pulseState)

// Источник 2 — polling VPS REST /status
const vps = useStore((s: any) => s.vpsStatus)
const vpsActive = vps?.service?.active === true

// Выбор источника:
const connections: ConnectionStatus[] = pulseState?.connections ?? [
  // fallback — использует vpsActive
  { name: 'vps_ws',    stage: vpsActive ? 'normal' : 'lost', ... },
  { name: 'vps_server', stage: vpsActive ? 'normal' : 'stopped', ... },
  ...
]
```

**Проблема:** Когда `pulseState.connections` существует (WS UI подключён), VPS-соединения берутся из бэкенда, где они **всегда `stopped`** ([`ui/ws_server.py:683-685`](ui/ws_server.py:683-685)). Реальный статус VPS (`vpsActive`) игнорируется.

### Конкретные симптомы

| Соединение | Что показывает | Что должно показывать |
|---|---|---|
| WebSocket VPS ⚡ | `stopped` (из бэкенда) | Зависит от `vpsStatus` |
| Сервер VPS ⚡ | `stopped` (из бэкенда) | Зависит от `vpsStatus` |
| БД VPS ⚡ | `stopped` (из бэкенда) | Зависит от `vpsStatus` |
| Локальная БД | `stopped` (fallback, WS не подключён) | `normal` (БД доступна) |

---

## Предлагаемое решение

### Принцип: мерж двух источников на фронтенде

Вместо того чтобы выбирать **либо** `pulseState.connections` **либо** fallback, нужно **мержить** их:

1. Берём список соединений из `pulseState.connections` (структура, порядок, метаданные)
2. Для VPS-соединений (`vps_ws`, `vps_server`, `vps_db`) переопределяем `stage` из `vpsStatus`
3. Для `local_db` переопределяем `stage` из `connected` (WS UI)
4. Для `bingx_private` — оставляем как есть (заглушка)

### Изменения

#### Файл: [`ui/react-app/src/components/PulseView.tsx`](ui/react-app/src/components/PulseView.tsx)

**Где:** функция `ConnectionsBlock()`, строки 107-126

**Что изменить:**

```typescript
function ConnectionsBlock() {
  const pulseState = useStore(s => s.pulseState)
  const connected  = useStore(s => s.connected)
  const vps = useStore((s: any) => s.vpsStatus)
  const vpsActive = vps?.service?.active === true

  const [activePopover, setActivePopover] = useState<string | null>(null)

  // Берём базовый список из pulseState или fallback
  const baseConnections: ConnectionStatus[] = pulseState?.connections ?? [
    { name: 'ws_ui',        label: 'WebSocket UI',       stage: connected ? 'normal' : 'lost',    ... },
    { name: 'vps_ws',       label: 'WebSocket VPS',      stage: vpsActive ? 'normal' : 'lost',    ... },
    { name: 'vps_server',   label: 'Сервер VPS',         stage: vpsActive ? 'normal' : 'stopped', ... },
    { name: 'vps_db',       label: 'БД VPS',             stage: vpsActive ? 'normal' : 'stopped', ... },
    { name: 'local_db',     label: 'Локальная БД',       stage: connected ? 'normal' : 'stopped', ... },
    { name: 'bingx_private',label: 'BingX Private API',  stage: 'stopped', ... },
    { name: 'fear_greed',   label: 'Fear & Greed API',   stage: 'stopped', ... },
    { name: 'news_feed',    label: 'Новостной фид',      stage: 'stopped', ... },
  ]

  // Мержим: переопределяем stage для VPS-соединений из vpsStatus
  const connections = baseConnections.map(c => {
    if (c.name === 'vps_ws') {
      return { ...c, stage: vpsActive ? 'normal' : 'lost' }
    }
    if (c.name === 'vps_server' || c.name === 'vps_db') {
      return { ...c, stage: vpsActive ? 'normal' : 'stopped' }
    }
    if (c.name === 'local_db') {
      return { ...c, stage: connected ? 'normal' : 'stopped' }
    }
    return c
  })
```

**Логика мержа:**

| Соединение | Источник stage | Приоритет |
|---|---|---|
| `ws_ui` | `pulseState.connections[0].stage` ИЛИ `connected` | pulseState (бэкенд знает лучше) |
| `vps_ws` | **Всегда из `vpsActive`** (локальный polling) | Локальный — бэкенд не знает статус VPS |
| `vps_server` | **Всегда из `vpsActive`** | Локальный |
| `vps_db` | **Всегда из `vpsActive`** | Локальный |
| `local_db` | **Всегда из `connected`** | Локальный |
| `bingx_private` | `pulseState.connections[5].stage` | pulseState (когда Execution Engine начнёт отправлять) |
| `fear_greed` | `pulseState.connections[6].stage` | pulseState |
| `news_feed` | `pulseState.connections[7].stage` | pulseState |

#### Файл: [`ui/ws_server.py`](ui/ws_server.py)

**Где:** функция `_handle_get_pulse_state()`, строки 681-690

**Что изменить:** VPS-соединения можно оставить как есть (`stopped`), т.к. фронтенд теперь переопределяет их из `vpsStatus`. Но для чистоты можно явно указать, что статус VPS-соединений определяется на фронтенде:

```python
connections = [
    {"name": "ws_ui",        "label": "WebSocket UI",       "stage": ws_ui_stage, ...},
    {"name": "vps_ws",       "label": "WebSocket VPS",      "stage": "unknown", ...},  # определяется на фронтенде
    {"name": "vps_server",   "label": "Сервер VPS",         "stage": "unknown", ...},  # определяется на фронтенде
    {"name": "vps_db",       "label": "БД VPS",             "stage": "unknown", ...},  # определяется на фронтенде
    {"name": "local_db",     "label": "Локальная БД",       "stage": db_stage, ...},
    ...
]
```

Это опционально — фронтенд всё равно перезаписывает stage для этих соединений.

---

## Что НЕ меняется

- **Бэкенд** (`ui/ws_server.py`) — минимальные изменения (только если решили поменять `stopped` на `unknown`)
- **Store** (`useStore.ts`) — без изменений
- **useVpsTelemetry** — без изменений (polling продолжает работать как есть)
- **useWebSocket** — без изменений
- **VpsServerBlock** — без изменений (уже использует `vpsStatus` напрямую)
- **Другие блоки** (Modules, Tasks, Events, Data Status) — без изменений

---

## Риски

| Риск | Вероятность | Mitigation |
|---|---|---|
| `vpsStatus` ещё не загрузился при первом рендере → VPS покажет `lost` | Высокая | Это нормально — через 5 секунд polling обновится |
| `vpsStatus` устарел (VPS был жив, но умер) | Средняя | `useVpsTelemetry` обновляется каждые 5 секунд — задержка не более 5с |
| Конфликт при мерже, если pulseState изменит структуру соединений | Низкая | Мерж по `name`, а не по индексу — устойчиво к перестановкам |

---

## Порядок реализации

| № | Шаг | Файл | Описание |
|---|---|---|---|
| 1 | Изменить `ConnectionsBlock()` | `PulseView.tsx` | Добавить мерж: baseConnections → connections с переопределением stage |
| 2 | (Опционально) Обновить stage в бэкенде | `ui/ws_server.py` | Поменять `stopped` на `unknown` для VPS-соединений |
| 3 | Проверить визуально | Браузер | Убедиться что статусы корректны при: VPS онлайн, VPS офлайн, WS UI подключён/отключён |
| 4 | Проверить тесты | `pytest tests/` | 203 теста не должны сломаться (изменения только в React) |
