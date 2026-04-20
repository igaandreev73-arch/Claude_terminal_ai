import { useState } from 'react'
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
}

const STAGE_LABEL: Record<string, string> = {
  normal:   'Норма',
  degraded: 'Деградация',
  lost:     'Нет связи',
  dead:     'Мёртв',
  stopped:  'Остановлен',
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

function ConnectionsBlock() {
  const pulseState = useStore(s => s.pulseState)
  const connected  = useStore(s => s.connected)
  const rl = pulseState?.rate_limit

  const connections: ConnectionStatus[] = pulseState?.connections ?? [
    { name: 'ws_ui',         label: 'WebSocket UI',          stage: connected ? 'normal' : 'lost', last_ok_at: null, is_critical: false, market_type: 'internal' },
    { name: 'spot_ws',       label: 'WS Спот BingX',         stage: 'stopped', last_ok_at: null, is_critical: false, market_type: 'spot' },
    { name: 'futures_ws',    label: 'WS Фьючерсы BingX',     stage: 'stopped', last_ok_at: null, is_critical: true,  market_type: 'futures' },
    { name: 'spot_rest',     label: 'REST API Спот',          stage: 'stopped', last_ok_at: null, is_critical: false, market_type: 'spot' },
    { name: 'futures_rest',  label: 'REST API Фьючерсы',      stage: 'stopped', last_ok_at: null, is_critical: false, market_type: 'futures' },
    { name: 'local_db',      label: 'Локальная БД',           stage: connected ? 'normal' : 'stopped', last_ok_at: null, is_critical: false, market_type: 'internal' },
    { name: 'fear_greed',    label: 'Fear & Greed API',       stage: 'stopped', last_ok_at: null, is_critical: false, market_type: 'external' },
    { name: 'news_feed',     label: 'Новостной фид',          stage: 'stopped', last_ok_at: null, is_critical: false, market_type: 'external' },
  ]

  return (
    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' }}>
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
            display: 'flex', alignItems: 'center', gap: 8,
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
          </div>
        ))}
      </div>
    </div>
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
              <td style={{ padding: '5px 8px', color: 'var(--text-primary)', fontWeight: 500 }}>{m.label}</td>
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
  const dbStats    = useStore(s => s.dbStats)
  const rows: DataTrustRow[] = pulseState?.data_rows ?? []
  const basis: BasisRow[] = pulseState?.basis ?? []

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
      {rows.length > 0 ? (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              {['Пара', 'ТФ', 'Рынок', 'Посл. свеча', 'Дыр 24ч', 'Верификация', 'Рейтинг'].map(h => (
                <th key={h} style={{ padding: '4px 6px', textAlign: h === 'Пара' ? 'left' : 'right', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 10 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
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
          {dbStats
            ? `${dbStats.candles.length} пар в БД — запросите pulse_state для деталей`
            : 'Данные не получены'}
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

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 16, overflow: 'hidden' }}>

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
