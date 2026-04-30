# План: Настройки VPS-сервера через UI

**Задача:** Добавить иконку настроек в блок "Сервер VPS" на вкладке "Пульс", через которую можно менять адрес VPS-сервера, API-ключ и проверять соединение.

---

## Текущее состояние

Сейчас VPS-сервер жёстко зашит в коде:

| Файл | Что захардкожено |
|------|-----------------|
| `core/config.py` | `VPS_HOST = "132.243.235.173"`, `VPS_PORT = 8800` |
| `useVpsTelemetry.ts` | `VPS_URL = 'http://132.243.235.173:8800'`, `VPS_KEY = 'vps_telemetry_key_2026'` |
| `PulseView.tsx` | Заголовок `СЕРВЕР VPS · 132.243.235.173` |
| `ui/ws_server.py` | `vps_heartbeat` — данные с VPS |

---

## Требования

### Функциональные

1. **Иконка настроек (⚙️)** в блоке "Сервер VPS" рядом с заголовком
2. **Модальное окно** с полями:
   - Адрес сервера (host:port)
   - API-ключ
   - Кнопка "Проверить соединение" — делает запрос к VPS `/health` и показывает результат
   - Кнопка "Сохранить" — сохраняет в localStorage + обновляет VPSClient
   - Кнопка "Отмена" — закрывает модалку
3. **Автосохранение** — при изменении настроек, все компоненты, использующие VPS, должны подхватить новый адрес
4. **Валидация** — host не пустой, port число 1-65535, ключ не пустой

### Нефункциональные

- Настройки сохраняются в `localStorage` (чтобы переживали перезагрузку)
- При смене адреса — VPSClient переподключается к новому серверу
- Без перезагрузки страницы

---

## Архитектура решения

```
┌─────────────────────────────────────────────────────────────┐
│  localStorage (vpsConfig)                                    │
│  { host: "132.243.235.173", port: 8800, apiKey: "..." }      │
└──────────────────────────────┬──────────────────────────────┘
                               │ read on init
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  useStore (zustand)                                          │
│  - vpsConfig: VpsConfig | null                               │
│  - setVpsConfig(config) — сохраняет в store + localStorage   │
└──────────────────────────┬───────────────────────────────────┘
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │ useVpsTelemetry│ │ VpsServerBlock│ │ VPSClient    │
  │ (polling)     │ │ (UI)         │ │ (Python)     │
  │ читает        │ │ читает       │ │ читает       │
  │ vpsConfig     │ │ vpsConfig    │ │ AppConfig    │
  └──────────────┘ └──────────────┘ └──────────────┘
```

---

## Пошаговый план реализации

### Шаг 1: VpsConfig в useStore.ts

**Файл:** `ui/react-app/src/store/useStore.ts`

**Что сделать:**
- Добавить интерфейс `VpsConfig`
- Добавить в Store: `vpsConfig`, `setVpsConfig`
- `setVpsConfig` сохраняет в `localStorage` + обновляет store
- При инициализации читает из `localStorage` (или дефолтные `132.243.235.173:8800`)

```typescript
export interface VpsConfig {
  host: string
  port: number
  apiKey: string
}

// В Store:
vpsConfig: VpsConfig
setVpsConfig: (config: VpsConfig) => void
```

**Критерий:** Настройки VPS сохраняются между перезагрузками страницы.

---

### Шаг 2: VpsSettingsModal.tsx (новый компонент)

**Файл:** `ui/react-app/src/components/VpsSettingsModal.tsx` (новый)

**Что сделать:**
- Модальное окно с полями:
  - Host (text input)
  - Port (number input)
  - API Key (password input)
- Кнопка "Проверить соединение":
  - GET `http://{host}:{port}/health?api_key={apiKey}`
  - Показать статус: ✅ Успешно / ❌ Ошибка: ...
- Кнопка "Сохранить" — вызывает `setVpsConfig()` + закрывает модалку
- Кнопка "Отмена" — закрывает без сохранения
- Валидация на клиенте

```tsx
interface Props {
  open: boolean
  onClose: () => void
}

export default function VpsSettingsModal({ open, onClose }: Props) {
  const config = useStore(s => s.vpsConfig)
  const setVpsConfig = useStore(s => s.setVpsConfig)
  const [host, setHost] = useState(config.host)
  const [port, setPort] = useState(config.port)
  const [apiKey, setApiKey] = useState(config.apiKey)
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle')
  const [testMsg, setTestMsg] = useState('')

  async function testConnection() {
    setTestStatus('testing')
    try {
      const res = await fetch(`http://${host}:${port}/health?api_key=${apiKey}`, { signal: AbortSignal.timeout(5000) })
      if (res.ok) { setTestStatus('ok'); setTestMsg('Соединение установлено') }
      else { setTestStatus('error'); setTestMsg(`HTTP ${res.status}`) }
    } catch (e: any) {
      setTestStatus('error'); setTestMsg(e.message)
    }
  }

  function save() {
    setVpsConfig({ host, port, apiKey })
    onClose()
  }

  // ... render modal
}
```

**Критерий:** Модалка открывается, поля редактируются, проверка соединения работает.

---

### Шаг 3: Иконка ⚙️ в VpsServerBlock

**Файл:** `ui/react-app/src/components/PulseView.tsx`

**Что сделать:**
- Добавить кнопку ⚙️ рядом с заголовком "СЕРВЕР VPS"
- При клике — открывать `VpsSettingsModal`
- Заменить хардкод `132.243.235.173` на `vpsConfig.host`

```tsx
// В VpsServerBlock():
const vpsConfig = useStore(s => s.vpsConfig)
const [settingsOpen, setSettingsOpen] = useState(false)

// В return:
<span style={{ ... }}>
  СЕРВЕР VPS · {vpsConfig.host}:{vpsConfig.port}
  <button onClick={() => setSettingsOpen(true)} style={{ ... }}>⚙️</button>
</span>

<VpsSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
```

**Критерий:** Иконка ⚙️ отображается, модалка открывается.

---

### Шаг 4: useVpsTelemetry.ts — читать vpsConfig из store

**Файл:** `ui/react-app/src/hooks/useVpsTelemetry.ts`

**Что сделать:**
- Убрать хардкод `VPS_URL` и `VPS_KEY`
- Читать `vpsConfig` из `useStore`
- При изменении config — перезапускать polling с новым URL

```typescript
export function useVpsTelemetry() {
  const setVpsStatus = useStore((s: any) => s.setVpsStatus)
  const vpsConfig = useStore((s: any) => s.vpsConfig)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const url = `http://${vpsConfig.host}:${vpsConfig.port}`
    const key = vpsConfig.apiKey

    async function poll() {
      const data = await fetchVpsStatus(url, key)
      if (data) setVpsStatus(data)
    }

    poll()
    timerRef.current = setInterval(poll, INTERVAL)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [vpsConfig.host, vpsConfig.port, vpsConfig.apiKey])
}
```

**Критерий:** При смене адреса в настройках — polling переключается на новый сервер.

---

### Шаг 5: fetchVpsCandles — принимать параметры

**Файл:** `ui/react-app/src/hooks/useVpsTelemetry.ts`

**Что сделать:**
- `fetchVpsCandles()` должна принимать `vpsConfig` или читать из store
- Либо передавать host/port/apiKey как параметры

```typescript
export async function fetchVpsCandles(
  config: VpsConfig,
  symbol: string,
  tf: string,
  limit: number = 500,
  marketType: string = 'spot',
): Promise<OHLCVBar[] | null> {
  const url = `http://${config.host}:${config.port}`
  // ...
}
```

**Критерий:** ChartView может подключаться к любому VPS-серверу.

---

### Шаг 6: Python-сторона — AppConfig читает из .env (оставить как fallback)

**Файл:** `core/config.py`

**Что сделать:**
- Оставить `VPS_HOST`/`VPS_PORT`/`VPS_API_KEY` как fallback из `.env`
- На фронтенде настройки из localStorage имеют приоритет

**Критерий:** Если настройки не сохранены в localStorage — используются дефолтные из `.env`.

---

### Шаг 7: ChartView.tsx — использовать vpsConfig

**Файл:** `ui/react-app/src/components/ChartView.tsx`

**Что сделать:**
- В `fetchCandles()` передавать `vpsConfig` в `fetchVpsCandles()`

**Критерий:** График подключается к настроенному VPS.

---

## Сводка изменений

| Файл | Статус | Что меняем |
|------|--------|------------|
| `useStore.ts` | 🆕 | `VpsConfig` + `vpsConfig`/`setVpsConfig` в store |
| `VpsSettingsModal.tsx` | 🆕 | Новый компонент — модалка настроек |
| `PulseView.tsx` | ✏️ | Иконка ⚙️, замена хардкода на `vpsConfig` |
| `useVpsTelemetry.ts` | ✏️ | Чтение `vpsConfig` из store, параметризация |
| `ChartView.tsx` | ✏️ | Передача `vpsConfig` в `fetchVpsCandles` |
| `core/config.py` | — | Без изменений (fallback) |

---

## Оценка трудозатрат

| Шаг | Описание | Часы |
|-----|----------|------|
| 1 | VpsConfig в useStore.ts | 0.5 |
| 2 | VpsSettingsModal.tsx | 2 |
| 3 | Иконка ⚙️ в PulseView.tsx | 0.5 |
| 4 | useVpsTelemetry.ts — параметризация | 1 |
| 5 | fetchVpsCandles — параметризация | 0.5 |
| 6 | Проверка Python-стороны | 0.5 |
| 7 | ChartView.tsx — адаптация | 0.5 |
| **Итого** | | **~5.5ч** |

---

## Риски

| Риск | Mitigation |
|------|------------|
| При смене адреса старый VPSClient в Python не переподключается | VPSClient пересоздаётся при старте `_run_terminal()` — нужно перезапустить main.py |
| localStorage может быть очищен | Дефолтные значения из `.env` как fallback |
| CORS при проверке соединения с другого хоста | VPS уже имеет `CORSMiddleware(allow_origins=["*"])` |
