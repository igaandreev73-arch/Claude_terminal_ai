import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useStore } from '../store/useStore'
import type { ConnectionStatus, ModuleStatus, DataTrustRow, BasisRow } from '../store/useStore'

// ── Helpers ───────────────────────────────────────────────────────────────────

function ago(ts: number | null): string {
  if (!ts) return '—'
  const s = Math.floor((Date.now() / 1000) - ts)
  if (s < 60) return `${s}с назад`
  if (s < 3600) return `${Math.floor(s / 60)}м назад`
  return `${Math.floor(s / 3600)}ч назад`
}

function fmtMs(ts: number | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// ── Stage colours ─────────────────────────────────────────────────────────────

const STAGE_COLOR: Record<string, string> = {
  normal:   'var(--accent-green)',
  degraded: 'var(--accent-orange)',
  lost:     '#f87171',
  dead:     '#ef4444',
  stopped:  'var(--text-muted)',
  unknown:  'var(--text-muted)',
}

const STAGE_LABEL: Record<string, string> = {
  normal:   'Норма',
  degraded: 'Деградация',
  lost:     'Нет связи',
  dead:     'Мёртв',
  stopped:  'Остановлен',
  unknown:  'Ожидание',
}

const MODULE_STATUS_COLOR: Record<string, string> = {
  ok:       'var(--accent-green)',
  slow:     'var(--accent-orange)',
  degraded: '#f97316',
  frozen:   '#f87171',
  stopped:  'var(--text-muted)',
}

const MODULE_STATUS_LABEL: Record<string, string> = {
  ok:       'Норма',
  slow:     'Медленно',
  degraded: 'Деградирует',
  frozen:   'Завис',
  stopped:  'Остановлен',
}

// ── Block 1 — Connections ─────────────────────────────────────────────────────

function StatusDot({ stage }: { stage: string }) {
  const color = STAGE_COLOR[stage] ?? 'var(--text-muted)'
  const isAnim = stage === 'dead'
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: color, flexShrink: 0,
      animation: isAnim ? 'livePulse 0.8s ease infinite' : stage === 'normal' ? 'livePulse 2s ease infinite' : 'none',
    }} />
  )
}


// ── Connection descriptions ───────────────────────────────────────────────────

const CONNECTION_INFO: Record<string, { title: string; body: string }> = {
  ws_ui: {
    title: 'WebSocket UI — интерфейс терминала',
    body: 'Соединение между браузером и локальным Python-сервером (ws://localhost:8765). Через него UI получает тики цен, события, pulse_state. Если соединение потеряно — UI показывает устаревшие данные, новые события не приходят.',
  },
  vps_ws: {
    title: 'WebSocket VPS — канал реалтайм-данных',
    body: 'Постоянное WebSocket-соединение с VPS-сервером (ws://132.243.235.173:8800/ws). Через него Desktop получает все рыночные события: свечи, стакан, ликвидации, watchdog-статусы. Если соединение потеряно — реалтайм данные не поступают, но история доступна через REST.',
  },
  vps_server: {
    title: 'Сервер VPS — удалённый сборщик данных',
    body: 'Удалённый сервер (132.243.235.173) работает круглосуточно и собирает рыночные данные с BingX. Telemetry API доступен на порту 8800. Desktop получает от VPS данные через WS (реалтайм) и REST (история). Если VPS недоступен — терминал работает офлайн с последним кэшем.',
  },
  vps_db: {
    title: 'БД VPS — SQLite база данных на сервере',
    body: 'SQLite база данных на VPS-сервере. Хранит все исторические данные: свечи 1m, снимки стакана, ликвидации, метрики фьючерсов. Desktop запрашивает историю через REST API /api/candles. Если БД недоступна — исторические данные не загружаются.',
  },
  local_db: {
    title: 'Локальная БД — SQLite кэш на Desktop',
    body: 'SQLite база данных на локальной машине. Хранит кэш свечей, состояние стратегий, историю сигналов и сделок. Наполняется через VPS Client. Если БД недоступна — бэктест и аналитика не работают.',
  },
  bingx_private: {
    title: 'BingX Private API — торговый API',
    body: 'Прямое HTTP-соединение с BingX Private API (только с Desktop). Используется для: открытия/закрытия ордеров, проверки баланса, получения статуса позиций. API-ключ хранится только локально, на VPS его нет. Если недоступен — торговля невозможна.',
  },
  fear_greed: {
    title: 'Fear & Greed API — индекс страха и жадности',
    body: 'Внешний API (alternative.me) для получения индекса Fear & Greed криптовалютного рынка. Значение 0-25 — экстремальный страх (возможность для покупки), 75-100 — жадность (риск коррекции). Не реализован в текущей версии.',
  },
  news_feed: {
    title: 'Новостной фид — агрегатор новостей',
    body: 'Агрегатор крипто-новостей (CryptoPanic или аналог). Используется для: мониторинга новостей по торгуемым парам, фильтрации по тональности, алертов на важные события. Не реализован в текущей версии.',
  },
}

function ConnectionsBlock() {
  const pulseState = useStore(s => s.pulseState)
  const connected  = useStore(s => s.connected)
  const rl = pulseState?.rate_limit

  const vps = useStore((s: any) => s.vpsStatus)
  const vpsActive = vps?.service?.active === true

  const [activePopover, setActivePopover] = useState<string | null>(null)

  // Базовый список из pulseState (с бэкенда) или fallback
  const baseConnections: ConnectionStatus[] = pulseState?.connections ?? [
    { name: 'ws_ui',        label: 'WebSocket UI',       stage: connected ? 'normal' : 'lost',    last_ok_at: null, is_critical: false, market_type: 'internal' },
    { name: 'vps_ws',       label: 'WebSocket VPS',      stage: vpsActive ? 'normal' : 'lost',    last_ok_at: null, is_critical: true,  market_type: 'internal' },
    { name: 'vps_server',   label: 'Сервер VPS',         stage: vpsActive ? 'normal' : 'stopped', last_ok_at: null, is_critical: true,  market_type: 'internal' },
    { name: 'vps_db',       label: 'БД VPS',             stage: vpsActive ? 'normal' : 'stopped', last_ok_at: null, is_critical: true,  market_type: 'internal' },
    { name: 'local_db',     label: 'Локальная БД',        stage: connected ? 'normal' : 'stopped', last_ok_at: null, is_critical: false, market_type: 'internal' },
    { name: 'bingx_private',label: 'BingX Private API',  stage: 'stopped', last_ok_at: null, is_critical: true,  market_type: 'external' },
    { name: 'fear_greed',   label: 'Fear & Greed API',   stage: 'stopped', last_ok_at: null, is_critical: false, market_type: 'external' },
    { name: 'news_feed',    label: 'Новостной фид',       stage: 'stopped', last_ok_at: null, is_critical: false, market_type: 'external' },
  ]

  // Мерж: переопределяем stage для VPS-соединений из vpsStatus (локальный polling)
  // и для local_db из connected (WS UI)
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

  return (
    <div onClick={() => setActivePopover(null)} style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
          СОЕДИНЕНИЯ
        </span>
        {rl && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Rate Limit: <b style={{ color: rl.pct >= 95 ? '#f87171' : rl.pct >= 80 ? 'var(--accent-orange)' : 'var(--accent-green)' }}>
                {rl.used}/{rl.limit}
              </b>
            </span>
            <div style={{ width: 80, height: 5, background: 'var(--bg-surface)', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 3,
                width: `${Math.min(100, rl.pct)}%`,
                background: rl.pct >= 95 ? '#f87171' : rl.pct >= 80 ? 'var(--accent-orange)' : 'var(--accent-green)',
                transition: 'width 0.5s ease',
              }} />
            </div>
          </div>
        )}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
        {connections.map(c => (
          <div key={c.name} style={{
            position: 'relative', display: 'flex', alignItems: 'center', gap: 8,
            background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)',
            padding: '7px 10px', border: `1px solid ${STAGE_COLOR[c.stage] ?? 'var(--border-subtle)'}22`,
          }}>
            <StatusDot stage={c.stage} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {c.label}
                {c.is_critical && <span style={{ fontSize: 9, color: '#f87171', marginLeft: 4 }}>⚡</span>}
              </div>
              <div style={{ fontSize: 10, color: STAGE_COLOR[c.stage] ?? 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {STAGE_LABEL[c.stage] ?? c.stage}
                {c.last_ok_at ? <span style={{ color: 'var(--text-muted)', marginLeft: 4 }}>{ago(c.last_ok_at)}</span> : null}
              </div>
            </div>
            {CONNECTION_INFO[c.name] && (
              <button
                onClick={(e) => { e.stopPropagation(); setActivePopover(activePopover === c.name ? null : c.name) }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: 'var(--text-muted)', fontSize: 13, lineHeight: 1, borderRadius: 3, flexShrink: 0 }}
                title={CONNECTION_INFO[c.name].title}
              >ⓘ</button>
            )}
            {activePopover === c.name && CONNECTION_INFO[c.name] && (
              <div
                onClick={(e) => e.stopPropagation()}
                style={{
                  position: 'absolute', top: '100%', left: 0, zIndex: 100,
                  width: 280, marginTop: 4,
                  background: 'var(--bg-overlay)', border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)', padding: '12px 14px',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
                  {CONNECTION_INFO[c.name].title}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  {CONNECTION_INFO[c.name].body}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}


// ── Block VPS ─────────────────────────────────────────────────────────────────

function VpsServerBlock() {
  const vps = useStore((s: any) => s.vpsStatus)
  const pulseState = useStore((s: any) => s.pulseState)
  const hb = pulseState?.vps_heartbeat
  const connStatus = vps ? (vps.service?.active ? 'normal' : 'lost') : 'stopped'
  const connLabel  = vps ? (vps.service?.active ? 'Активен' : 'Не активен') : 'Нет связи'

  // Heartbeat индикатор
  const hbAge = hb?.seconds_since ?? Infinity
  const hbColor = hbAge < 15 ? 'var(--accent-green)' : hbAge < 30 ? 'var(--accent-orange)' : '#ef4444'
  const hbLabel = hbAge < 60 ? `${Math.round(hbAge)}с назад` : 'Нет сигнала'

  function Bar({ pct, warn = 70, crit = 85 }: { pct: number; warn?: number; crit?: number }) {
    const color = pct >= crit ? '#f87171' : pct >= warn ? 'var(--accent-orange)' : 'var(--accent-green)'
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{ width: 60, height: 5, background: 'var(--bg-surface)', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ width: `${Math.min(100, pct)}%`, height: '100%', background: color, borderRadius: 3 }} />
        </div>
        <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color }}>{pct.toFixed(0)}%</span>
      </div>
    )
  }

  return (
    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
          СЕРВЕР VPS · 132.243.235.173
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Heartbeat индикатор */}
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, fontFamily: 'var(--font-mono)', color: hbColor }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: hbColor }} />
            {hbLabel}
          </span>
          {vps?.telegram_ok != null && (
            <span style={{ fontSize: 10, color: vps.telegram_ok ? 'var(--accent-green)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {vps.telegram_ok ? '🔔 TG' : '🔕 TG'}
            </span>
          )}
          {vps?.timestamp && (
            <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {new Date(vps.timestamp).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          <StatusDot stage={connStatus} />
          <span style={{ fontSize: 10, color: STAGE_COLOR[connStatus] ?? 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {connLabel}
          </span>
        </div>
      </div>

      {!vps ? (
        <div style={{ textAlign: 'center', padding: '12px 0', color: 'var(--text-muted)', fontSize: 12 }}>
          Нет соединения с VPS телеметрией (порт 8800)
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          {/* System */}
          <div style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>СИСТЕМА</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>CPU</div>
                <Bar pct={vps.system.cpu_percent} warn={60} crit={85} />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>
                  RAM {vps.system.ram_used_mb}/{vps.system.ram_total_mb} MB
                </div>
                <Bar pct={vps.system.ram_percent} warn={75} crit={90} />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>
                  Диск (свободно {vps.system.disk_free_gb?.toFixed(1)} GB)
                </div>
                <Bar pct={vps.system.disk_percent} warn={70} crit={85} />
              </div>
            </div>
          </div>

          {/* Database */}
          <div style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>БАЗА ДАННЫХ</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {([
                ['Размер', `${vps.database.size_mb?.toFixed(1)} MB`],
                ['Свечи',  vps.database.candles?.toLocaleString()],
                ['Стаканы', vps.database.orderbook_snapshots?.toLocaleString()],
                ['Ликвидации', vps.database.liquidations?.toLocaleString()],
              ] as [string, string][]).map(([label, value]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{label}</span>
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Symbols */}
          <div style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>ПАРЫ VPS</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {(vps.data ?? []).map((d: any) => {
                // Реальный trust: давность последней свечи (ISO строка = UTC)
                const lastMs  = d.last_candle ? new Date(d.last_candle + 'Z').getTime() : null
                const ageMin  = lastMs ? (Date.now() - lastMs) / 60000 : null
                const fresh   = ageMin != null && ageMin < 3
                const stale   = ageMin != null && ageMin > 10
                const ageStr  = ageMin != null
                  ? (ageMin < 1 ? '<1м' : ageMin < 60 ? `${Math.floor(ageMin)}м` : `${Math.floor(ageMin/60)}ч`)
                  : '—'
                const tc = fresh ? 'var(--accent-green)' : stale ? '#f87171' : 'var(--accent-orange)'
                return (
                  <div key={d.symbol} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 10, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', minWidth: 32 }}>
                      {d.symbol.replace('/USDT', '')}
                    </span>
                    <span style={{ fontSize: 9, color: tc, fontFamily: 'var(--font-mono)' }}>{ageStr}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <div style={{ width: 28, height: 3, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(100, d.trust_score)}%`, height: '100%', background: tc, borderRadius: 2 }} />
                      </div>
                      <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: tc }}>{d.trust_score}%</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
// ── Module descriptions ───────────────────────────────────────────────────────

const MODULE_INFO: Record<string, { title: string; body: string }> = {
  event_bus: {
    title: 'Event Bus — шина событий',
    body: 'Центральный брокер сообщений системы. Все модули общаются только через него — никаких прямых вызовов друг друга. Работает по принципу publish/subscribe: модуль публикует событие (например candle.1m.closed), все подписчики получают его асинхронно. Это позволяет добавлять новые модули без изменения существующих. Если Event Bus завис — вся система перестаёт обмениваться данными.',
  },
  spot_ws: {
    title: 'Spot WebSocket — спотовый поток',
    body: 'Постоянное WebSocket-соединение с BingX Spot API. Подписан на потоки: свечи 1m (kline), стакан orderbook, поток сделок. Публикует события candle.1m.tick и candle.1m.closed для TF Aggregator. Поток сделок используется для расчёта CVD (Cumulative Volume Delta) — соотношения покупок и продаж. Частично невосстанавливаем: если соединение упало, пропущенный поток сделок восстановить нельзя.',
  },
  futures_ws: {
    title: 'Futures WebSocket — фьючерсный поток ⚡',
    body: 'WebSocket-соединение с BingX Futures API. Подписан на: свечи 1m, стакан, поток сделок и — критически важно — @forceOrder (принудительные ликвидации). Ликвидации полностью невосстанавливаемы: BingX не хранит их историю через REST. Если это соединение деградирует, система немедленно записывает data_gap в БД с пометкой recoverable=False. Обозначен ⚡ как критический поток.',
  },
  ta_engine: {
    title: 'TA Engine — технический анализ',
    body: 'Вычисляет индикаторы на каждой закрытой свече: EMA (9/21/55/200), RSI(14), MACD(12/26/9), Bollinger Bands(20), ATR(14), VWAP. Слушает события candle.1m.closed и timeframe-свечи. Публикует ta.* события с рассчитанными значениями. Результаты используются Signal Engine и MTF Confluence Engine для генерации торговых сигналов.',
  },
  signal_engine: {
    title: 'Signal Engine — генератор сигналов',
    body: 'Агрегирует сигналы от всех аналитических модулей (TA Engine, SMC Engine, MTF Confluence, Anomaly Detector). Присваивает сигналу оценку score от 0 до 100. Сигналы со score ≥ 60 попадают в очередь. TTL сигнала — 5 минут. Дедупликация по symbol+direction: два одинаковых сигнала за минуту не дублируются. Публикует signal.generated, signal.expired, signal.executed.',
  },
  basis_calc: {
    title: 'Basis Calculator — калькулятор базиса',
    body: 'Вычисляет базис (разницу цен спот и фьючерс) на каждой закрытой минутной свече. Базис = фьючерсная цена − спотовая цена. Базис % = базис / спотовая × 100. Положительный и растущий базис = контанго (рынок ожидает роста). Отрицательный = бэквордация (доминирует страх или шорт). Резкое изменение базиса часто предшествует сильному движению. Сохраняет в таблицу futures_metrics.',
  },
}

// ── Module info popover ───────────────────────────────────────────────────────

function ModuleInfoPopover({ moduleName }: { moduleName: string }) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const info = MODULE_INFO[moduleName]
  if (!info) return null

  const rect = btnRef.current?.getBoundingClientRect()

  return (
    <>
      <button
        ref={btnRef}
        onClick={e => { e.stopPropagation(); setOpen(v => !v) }}
        title="Подробнее о модуле"
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          padding: '0 3px', lineHeight: 1, verticalAlign: 'middle',
          color: open ? 'var(--accent-blue)' : 'var(--text-muted)',
          fontSize: 12, transition: 'color 0.15s',
        }}
      >
        ⓘ
      </button>

      {open && rect && createPortal(
        <>
          {/* backdrop */}
          <div
            onClick={() => setOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 998 }}
          />
          {/* popup */}
          <div style={{
            position: 'fixed',
            top: rect.bottom + 6,
            left: Math.min(rect.left, window.innerWidth - 340),
            width: 320,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            zIndex: 999,
            padding: '14px 16px',
          }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
              {info.title}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.65 }}>
              {info.body}
            </div>
            <button
              onClick={() => setOpen(false)}
              style={{
                marginTop: 10, background: 'none', border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)', color: 'var(--text-muted)',
                fontSize: 11, cursor: 'pointer', padding: '3px 10px',
              }}
            >
              Закрыть
            </button>
          </div>
        </>,
        document.body
      )}
    </>
  )
}

// ── Block 2 — Modules ─────────────────────────────────────────────────────────

function ModulesBlock() {
  const pulseState = useStore(s => s.pulseState)
  const modules: ModuleStatus[] = pulseState?.modules ?? []

  if (modules.length === 0) {
    return (
      <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', marginBottom: 12 }}>СОСТОЯНИЕ МОДУЛЕЙ</div>
        <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)', fontSize: 12 }}>Данные не получены</div>
      </div>
    )
  }

  return (
    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', marginBottom: 10 }}>СОСТОЯНИЕ МОДУЛЕЙ</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            {['Модуль', 'Статус', 'Последнее действие', 'Событий/мин', 'Задержка'].map(h => (
              <th key={h} style={{ padding: '4px 8px', textAlign: h === 'Модуль' ? 'left' : 'right', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 10 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {modules.map(m => (
            <tr key={m.name} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <td style={{ padding: '5px 8px', color: 'var(--text-primary)', fontWeight: 500 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                  {m.label}
                  <ModuleInfoPopover moduleName={m.name} />
                </span>
              </td>
              <td style={{ padding: '5px 8px', textAlign: 'right' }}>
                <span style={{ fontSize: 10, color: MODULE_STATUS_COLOR[m.status], fontFamily: 'var(--font-mono)' }}>
                  {MODULE_STATUS_LABEL[m.status] ?? m.status}
                </span>
              </td>
              <td style={{ padding: '5px 8px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {fmtMs(m.last_action_at ? m.last_action_at * 1000 : null)}
              </td>
              <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {m.events_per_min}
              </td>
              <td style={{ padding: '5px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: m.latency_ms && m.latency_ms > 500 ? 'var(--accent-orange)' : 'var(--text-secondary)' }}>
                {m.latency_ms != null ? `${m.latency_ms}мс` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Block 3 — Task Queue ──────────────────────────────────────────────────────

const PRIORITY_COLOR: Record<string, string> = {
  P0: '#f87171',
  P1: 'var(--accent-blue)',
  P2: 'var(--accent-orange)',
}

function TaskQueueBlock() {
  const tasks = useStore(s => s.tasks)
  const running   = tasks.filter(t => t.status === 'running').slice(0, 8)
  const completed = tasks.filter(t => t.status === 'completed' || t.status === 'error').slice(0, 5)

  return (
    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', marginBottom: 10 }}>ОЧЕРЕДЬ ЗАДАЧ</div>

      {running.length === 0 && completed.length === 0 && (
        <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: 12 }}>Нет активных задач</div>
      )}

      {running.map(t => (
        <div key={t.task_id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
          <span style={{ fontSize: 9, color: PRIORITY_COLOR.P1, background: 'rgba(59,130,246,0.1)', padding: '1px 5px', borderRadius: 3, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>P1</span>
          <span style={{ fontSize: 11, color: 'var(--text-primary)', flex: 1 }}>{t.symbol} — {t.type}</span>
          <div style={{ width: 60, height: 3, background: 'var(--bg-surface)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${t.percent}%`, background: 'var(--accent-blue)', borderRadius: 2 }} />
          </div>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{t.percent}%</span>
        </div>
      ))}

      {completed.slice(0, 3).map(t => (
        <div key={t.task_id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0' }}>
          <span style={{ fontSize: 9, color: t.status === 'error' ? '#f87171' : 'var(--accent-green)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
            {t.status === 'error' ? '✗' : '✓'}
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.symbol} — {t.type}</span>
        </div>
      ))}
    </div>
  )
}

// ── Block 4 — Critical events ─────────────────────────────────────────────────

const CRITICAL_LEVEL_COLOR: Record<string, string> = {
  warning:  'var(--accent-orange)',
  error:    '#f87171',
  critical: '#ef4444',
}

function CriticalEventsBlock() {
  const events = useStore(s => s.criticalEvents)
  const markSeen = useStore(s => s.markCriticalEventSeen)
  const unseen = events.filter(e => !e.seen)

  return (
    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
          КРИТИЧЕСКИЕ СОБЫТИЯ
        </span>
        {unseen.length > 0 && (
          <span style={{ fontSize: 10, color: '#f87171', fontFamily: 'var(--font-mono)' }}>
            {unseen.length} новых
          </span>
        )}
      </div>
      {events.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--accent-green)', fontSize: 12 }}>
          ✓ Нет критических событий
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 200, overflowY: 'auto' }}>
          {events.slice(0, 30).map(e => (
            <div
              key={e.id}
              onClick={() => markSeen(e.id)}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                padding: '6px 8px', borderRadius: 'var(--radius-sm)',
                background: e.seen ? 'transparent' : `${CRITICAL_LEVEL_COLOR[e.level]}08`,
                border: `1px solid ${e.seen ? 'transparent' : CRITICAL_LEVEL_COLOR[e.level] + '22'}`,
                cursor: 'pointer',
              }}
            >
              <span style={{ fontSize: 10, color: CRITICAL_LEVEL_COLOR[e.level], fontFamily: 'var(--font-mono)', flexShrink: 0, marginTop: 1 }}>
                {e.level.toUpperCase()}
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'var(--text-primary)', fontWeight: e.seen ? 400 : 600 }}>{e.message}</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {e.module} · {new Date(e.started_at).toLocaleTimeString('ru')}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Block 5 — Data Status ─────────────────────────────────────────────────────

const TRUST_COLOR = (score: number) =>
  score >= 90 ? 'var(--accent-green)' : score >= 70 ? 'var(--accent-orange)' : '#f87171'

function DataStatusBlock() {
  const pulseState = useStore(s => s.pulseState)
  const vps        = useStore((s: any) => s.vpsStatus)
  const rows: DataTrustRow[] = pulseState?.data_rows ?? []
  const basis: BasisRow[] = pulseState?.basis ?? []

  // Если нет локальных данных — строим из VPS
  const vpsRows = (!rows.length && vps?.data) ? vps.data.map((d: any) => ({
    symbol: d.symbol,
    timeframe: '1m',
    market_type: 'spot',
    last_candle_at: d.last_candle ? new Date(d.last_candle + 'Z').getTime() : null,
    gaps_24h: 0,
    verification_status: d.trust_score >= 80 ? 'ok' : 'warning',
    trust_score: d.trust_score,
    size_mb: 0,
    candles: d.candles,
    ob_snapshots: d.ob_snapshots,
    liquidations: d.liquidations,
  })) : []

  const displayRows = rows.length ? rows : vpsRows

  return (
    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em', marginBottom: 10 }}>СОСТОЯНИЕ ДАННЫХ</div>

      {/* DB storage stats */}
      {pulseState && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
          {[
            { label: 'Размер БД', value: `${pulseState.db_size_mb.toFixed(1)} МБ` },
            { label: 'Прирост 7д', value: `+${pulseState.db_growth_mb_7d.toFixed(1)} МБ` },
            { label: 'Прогноз заполн.', value: pulseState.db_forecast_days != null ? `${pulseState.db_forecast_days} дней` : '∞' },
          ].map(({ label, value }) => (
            <div key={label} style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', padding: '6px 12px', textAlign: 'center' }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{label}</div>
              <div style={{ fontSize: 13, fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Basis table */}
      {basis.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 5 }}>БАЗИС СПОТ/ФЬЮЧЕРС</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {basis.map(b => (
              <div key={b.symbol} style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', padding: '5px 10px' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{b.symbol}</div>
                <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', fontWeight: 700, color: b.basis_pct >= 0 ? 'var(--accent-green)' : '#f87171' }}>
                  {b.basis_pct >= 0 ? '+' : ''}{b.basis_pct.toFixed(3)}%
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Data rows */}
      {displayRows.length > 0 ? (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              {['Пара', 'ТФ', 'Рынок', 'Посл. свеча', 'Дыр 24ч', 'Верификация', 'Рейтинг'].map(h => (
                <th key={h} style={{ padding: '4px 6px', textAlign: h === 'Пара' ? 'left' : 'right', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 10 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((r: any, i: number) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '5px 6px', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{r.symbol}</td>
                <td style={{ padding: '5px 6px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{r.timeframe}</td>
                <td style={{ padding: '5px 6px', textAlign: 'right', color: r.market_type === 'futures' ? 'var(--accent-orange)' : 'var(--accent-blue)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>{r.market_type}</td>
                <td style={{ padding: '5px 6px', textAlign: 'right', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                  {r.last_candle_at ? new Date(r.last_candle_at).toLocaleTimeString('ru') : '—'}
                </td>
                <td style={{ padding: '5px 6px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: r.gaps_24h > 0 ? '#f87171' : 'var(--accent-green)' }}>
                  {r.gaps_24h}
                </td>
                <td style={{ padding: '5px 6px', textAlign: 'right', fontSize: 10, fontFamily: 'var(--font-mono)', color: r.verification_status === 'verified' ? 'var(--accent-green)' : 'var(--accent-orange)' }}>
                  {r.verification_status}
                </td>
                <td style={{ padding: '5px 6px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 700, color: TRUST_COLOR(r.trust_score) }}>
                  {r.trust_score}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: 12 }}>
          {vps ? `VPS: ${vps.database?.candles?.toLocaleString()} свечей, ${vps.database?.orderbook_snapshots?.toLocaleString()} стаканов` : 'Данные не получены'}
        </div>
      )}
    </div>
  )
}

// ── Block 6 — Event stream ────────────────────────────────────────────────────

function EventStreamBlock() {
  const events = useStore(s => s.busEvents)
  const [filter, setFilter] = useState('')
  const [hideMundane, setHideMundane] = useState(true)

  const MUNDANE = ['candle.1m', 'candle.1m.closed', 'candle.1m.tick', 'ob.state_updated', 'mtf.score.updated', 'volume.cvd.updated']

  const visible = events
    .filter(e => !filter || e.event_type.includes(filter))
    .filter(e => !hideMundane || !MUNDANE.some(m => e.event_type.startsWith(m)))
    .slice(0, 80)

  return (
    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}>
          ПОТОК СОБЫТИЙ
        </span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer' }}>
            <input type="checkbox" checked={hideMundane} onChange={e => setHideMundane(e.target.checked)} style={{ accentColor: 'var(--accent-blue)' }} />
            Скрыть рутину
          </label>
          <input
            value={filter} onChange={e => setFilter(e.target.value)}
            placeholder="Фильтр…"
            style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)',
              padding: '3px 8px', fontSize: 11, fontFamily: 'var(--font-mono)', outline: 'none', width: 130,
            }}
          />
        </div>
      </div>
      <div style={{ maxHeight: 280, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {visible.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: 12 }}>Нет событий</div>
        ) : (
          visible.map(e => {
            const isError = e.event_type.includes('error') || e.event_type.includes('anomaly')
            return (
              <div key={e.id} style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                padding: '3px 0', borderBottom: '1px solid var(--border-subtle)',
                background: isError ? 'rgba(239,68,68,0.04)' : 'transparent',
              }}>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', flexShrink: 0, marginTop: 1 }}>
                  {e.ts ? new Date(e.ts).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                </span>
                <span style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)',
                  color: isError ? '#f87171' : 'var(--text-secondary)',
                  wordBreak: 'break-all',
                }}>
                  {e.event_type}
                </span>
                {typeof (e.data as Record<string, unknown>)?.symbol === 'string' && (
                  <span style={{ fontSize: 10, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                    {(e.data as Record<string, string>).symbol}
                  </span>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

// ── Main PulseView ────────────────────────────────────────────────────────────

interface PulseViewProps {
  onRequestPulse: () => void
}

export default function PulseView({ onRequestPulse }: PulseViewProps) {
  const pulseState = useStore(s => s.pulseState)
  const connected  = useStore(s => s.connected)
  const criticalEvents = useStore(s => s.criticalEvents)
  const unseenCount = criticalEvents.filter(e => !e.seen).length

  // Запрашиваем при монтировании и при восстановлении соединения
  useEffect(() => {
    if (connected) onRequestPulse()
  }, [connected])

  // VPS stale banner
  const isStale = pulseState?.vps_data_stale ?? true

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 16, overflow: 'hidden' }}>

      {/* Stale data banner */}
      {isStale && (
        <div style={{
          background: '#7f1d1d', color: '#fca5a5',
          padding: '8px 16px', borderRadius: 8,
          fontSize: 13, fontWeight: 500, flexShrink: 0,
        }}>
          ⚠️ Данные устарели: VPS недоступен. Сигналы отключены.
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20, color: 'var(--text-primary)', margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            Пульс
            {unseenCount > 0 && (
              <span style={{ fontSize: 12, background: '#ef4444', color: '#fff', borderRadius: 10, padding: '1px 8px', fontFamily: 'var(--font-mono)' }}>
                {unseenCount}
              </span>
            )}
          </h2>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '3px 0 0' }}>
            Состояние системы сбора данных в реальном времени
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {pulseState?.updated_at && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Обновлено: {new Date(pulseState.updated_at * 1000).toLocaleTimeString('ru')}
            </span>
          )}
          <button
            onClick={onRequestPulse}
            disabled={!connected}
            style={{
              padding: '7px 14px', border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)', background: 'var(--bg-elevated)',
              color: connected ? 'var(--text-primary)' : 'var(--text-muted)',
              cursor: connected ? 'pointer' : 'not-allowed', fontSize: 12,
            }}
          >
            ↺ Обновить
          </button>
        </div>
      </div>

      {/* Blocks — scrollable area */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14, paddingRight: 2 }}>

        {/* Block 1: Connections — always visible, sticky */}
        <ConnectionsBlock />

        {/* VPS Server block */}
        <VpsServerBlock />

        {/* Row: Modules + Task Queue */}
        <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 14 }}>
          <ModulesBlock />
          <TaskQueueBlock />
        </div>

        {/* Row: Critical Events + Data Status */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: 14 }}>
          <CriticalEventsBlock />
          <DataStatusBlock />
        </div>

        {/* Block 6: Event stream */}
        <EventStreamBlock />
      </div>
    </div>
  )
}
