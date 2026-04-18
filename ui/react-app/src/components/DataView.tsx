import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { RefreshCw, CheckCircle, AlertTriangle, Database, ChevronRight, Info, X, Wifi, Calculator, ShieldCheck, MoreHorizontal, Download, Loader } from 'lucide-react'
import { useStore } from '../store/useStore'
import type { DbTableStat, ObStat } from '../store/useStore'

const SYMBOLS  = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
const PERIODS  = [
  { id: '1w',  label: '1 неделя'  },
  { id: '1mo', label: '1 месяц'   },
  { id: '1y',  label: '1 год'     },
  { id: 'all', label: 'За всё время' },
]

// ── Backfill modal ────────────────────────────────────────────────────────────

interface BackfillModalProps {
  onClose:        () => void
  startBackfill:  (symbol: string, period: string) => void
}

function BackfillModal({ onClose, startBackfill }: BackfillModalProps) {
  const [selected, setSelected] = useState<string[]>(SYMBOLS)
  const [period,   setPeriod]   = useState('1w')
  const [loading,  setLoading]  = useState(false)
  const notifications = useStore(s => s.notifications)

  const activeTasks = notifications.filter(n => n.type === 'progress' && n.taskId)
  const allSelected = selected.length === SYMBOLS.length

  const toggleSymbol = (s: string) =>
    setSelected(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s])

  const toggleAll = () => setSelected(allSelected ? [] : [...SYMBOLS])

  const handleStart = () => {
    if (selected.length === 0) return
    setLoading(true)
    selected.forEach(sym => startBackfill(sym, period))
    setTimeout(() => setLoading(false), 500)
  }

  const warningText =
    period === 'all' ? `⚠ Займёт ~${selected.length * 15} мин. Загрузка продолжится в фоне.` :
    period === '1y'  ? `~${selected.length * 4} мин · загрузка продолжится в фоне` :
    period === '1mo' ? `~${selected.length} мин · загрузка продолжится в фоне` : null

  return createPortal(
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 400,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backdropFilter: 'blur(4px)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-xl)',
          padding: '28px 32px',
          maxWidth: 500,
          width: '90%',
          boxShadow: '0 12px 48px rgba(0,0,0,0.6)',
          display: 'flex', flexDirection: 'column', gap: 20,
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              width: 36, height: 36, borderRadius: 'var(--radius-md)',
              background: 'rgba(59,130,246,0.12)', color: 'var(--accent-blue)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Download size={18} />
            </span>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>
                Загрузка исторических данных
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                BingX REST API · только 1m, остальные TF агрегируются
              </div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ height: 1, background: 'var(--border-subtle)' }} />

        {/* Symbols */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.08em', fontFamily: 'var(--font-mono)' }}>
              ТОРГОВЫЕ ПАРЫ
            </div>
            <button
              onClick={toggleAll}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 11, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)',
                padding: '2px 6px',
              }}
            >
              {allSelected ? 'Снять все' : 'Все пары'}
            </button>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {SYMBOLS.map(s => {
              const active = selected.includes(s)
              return (
                <button
                  key={s}
                  onClick={() => toggleSymbol(s)}
                  style={{
                    padding: '6px 12px', borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer', fontSize: 12, fontFamily: 'var(--font-mono)', fontWeight: 600,
                    border: active ? '1px solid var(--accent-blue)' : '1px solid var(--border-subtle)',
                    background: active ? 'rgba(59,130,246,0.15)' : 'var(--bg-elevated)',
                    color: active ? 'var(--accent-blue)' : 'var(--text-secondary)',
                    transition: 'all 0.15s',
                  }}
                >
                  {s.replace('/USDT', '')}
                </button>
              )
            })}
          </div>
          {selected.length === 0 && (
            <div style={{ fontSize: 11, color: 'var(--accent-red)', marginTop: 6 }}>Выберите хотя бы одну пару</div>
          )}
          {selected.length > 0 && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
              Выбрано: {selected.length} из {SYMBOLS.length} пар
            </div>
          )}
        </div>

        {/* Period */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>
            ПЕРИОД
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {PERIODS.map(p => (
              <button
                key={p.id}
                onClick={() => setPeriod(p.id)}
                style={{
                  padding: '10px 14px', border: `1px solid ${period === p.id ? 'var(--accent-blue)' : 'var(--border-subtle)'}`,
                  borderRadius: 'var(--radius-md)', cursor: 'pointer', fontSize: 13,
                  background: period === p.id ? 'rgba(59,130,246,0.08)' : 'var(--bg-elevated)',
                  color: period === p.id ? 'var(--accent-blue)' : 'var(--text-secondary)',
                  textAlign: 'left', transition: 'all 0.15s', fontFamily: 'var(--font-body)',
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
          {warningText && (
            <div style={{ fontSize: 11, color: period === 'all' ? 'var(--accent-orange)' : 'var(--text-muted)', marginTop: 8 }}>
              {warningText}
            </div>
          )}
        </div>

        {/* Active tasks */}
        {activeTasks.length > 0 && (
          <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              АКТИВНЫЕ ЗАГРУЗКИ · {activeTasks.length}
            </div>
            {activeTasks.map(n => (
              <div key={n.id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{n.title}</span>
                  <span style={{ color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)' }}>{n.progress ?? 0}%</span>
                </div>
                <div style={{ height: 3, background: 'var(--bg-surface)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${n.progress ?? 0}%`, background: 'var(--accent-blue)', borderRadius: 2, transition: 'width 0.4s' }} />
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{n.message}</div>
              </div>
            ))}
          </div>
        )}

        {/* Start button */}
        <button
          onClick={handleStart}
          disabled={loading || selected.length === 0}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            background: selected.length === 0 ? 'var(--bg-elevated)' : 'var(--accent-blue)',
            color: selected.length === 0 ? 'var(--text-muted)' : '#fff',
            border: 'none', borderRadius: 'var(--radius-md)',
            padding: '12px', fontSize: 13, fontWeight: 600,
            cursor: (loading || selected.length === 0) ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.7 : 1,
            transition: 'all 0.15s',
          }}
        >
          {loading
            ? <><Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> Запускается…</>
            : <><Download size={14} /> {selected.length > 1 ? `Загрузить ${selected.length} пары` : 'Начать загрузку'}</>
          }
        </button>

        <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0, textAlign: 'center', lineHeight: 1.5 }}>
          Загрузка продолжается даже после закрытия окна.<br />
          Прогресс отображается в уведомлениях (колокольчик).
        </p>
      </div>
    </div>,
    document.body
  )
}

const TF_ORDER = ['1m','3m','5m','15m','30m','1h','2h','4h','6h','12h','1d','1W','1M']

function sortCandles(rows: DbTableStat[]): DbTableStat[] {
  return [...rows].sort((a, b) => {
    if (a.symbol !== b.symbol) return a.symbol.localeCompare(b.symbol)
    return TF_ORDER.indexOf(a.timeframe) - TF_ORDER.indexOf(b.timeframe)
  })
}

function ValidationBadge({ invalid, total }: { invalid: number; total: number }) {
  if (total === 0) return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>
  if (invalid === 0) return (
    <span style={{ display:'flex', alignItems:'center', gap:4, color:'var(--accent-green)', fontSize:11 }}>
      <CheckCircle size={11} /> ОК
    </span>
  )
  return (
    <span style={{ display:'flex', alignItems:'center', gap:4, color:'var(--accent-red)', fontSize:11 }}>
      <AlertTriangle size={11} /> {invalid} невалидных
    </span>
  )
}

// ── Status indicator with hover tooltip ──────────────────────────────────────

interface StatusItem { icon: React.ReactNode; label: string; ok: boolean }

function StatusIndicator({ items }: { items: StatusItem[] }) {
  const [pos, setPos]   = useState<{ x: number; y: number } | null>(null)
  const dotRef          = useRef<HTMLSpanElement>(null)
  const hideTimer       = useRef<ReturnType<typeof setTimeout> | null>(null)
  const allOk           = items.every(i => i.ok)

  const show = () => {
    if (hideTimer.current) clearTimeout(hideTimer.current)
    const r = dotRef.current?.getBoundingClientRect()
    if (r) setPos({ x: r.left, y: r.bottom + 8 })
  }
  const hide = () => {
    hideTimer.current = setTimeout(() => setPos(null), 250)
  }

  return (
    <>
      <span
        ref={dotRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        className={allOk ? 'status-dot-ok' : 'status-dot-err'}
        style={{
          width: 8, height: 8, borderRadius: '50%',
          background: allOk ? 'var(--accent-green)' : 'var(--accent-orange)',
          display: 'inline-block',
          cursor: 'pointer',
          flexShrink: 0,
        }}
      />

      {pos && createPortal(
        <div
          onMouseEnter={show}
          onMouseLeave={hide}
          style={{
            position: 'fixed',
            left: pos.x,
            top: pos.y,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            padding: '10px 12px',
            display: 'flex',
            flexDirection: 'column',
            gap: 7,
            zIndex: 9999,
            minWidth: 220,
            boxShadow: '0 4px 24px rgba(0,0,0,0.6)',
            pointerEvents: 'auto',
          }}
        >
          {items.map((item, i) => (
            <div key={i} style={{ display:'flex', alignItems:'center', gap:8, fontSize:12 }}>
              <span style={{ color: item.ok ? 'var(--accent-green)' : 'var(--accent-orange)', display:'flex' }}>
                {item.icon}
              </span>
              <span style={{ color:'var(--text-secondary)', flex:1 }}>{item.label}</span>
              <span style={{ color: item.ok ? 'var(--accent-green)' : 'var(--accent-orange)', fontSize:11, fontWeight:600 }}>
                {item.ok ? 'OK' : 'Проблема'}
              </span>
            </div>
          ))}
        </div>,
        document.body
      )}
    </>
  )
}

// ── Info modal ────────────────────────────────────────────────────────────────

function InfoModal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 300,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: '24px 28px',
          maxWidth: 520,
          width: '90%',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
          <span style={{ fontFamily:'var(--font-display)', fontWeight:700, fontSize:15, color:'var(--text-primary)' }}>
            {title}
          </span>
          <button onClick={onClose} style={{ background:'none', border:'none', cursor:'pointer', padding:4, color:'var(--text-muted)' }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ display:'flex', flexDirection:'column', gap:12, fontSize:12, color:'var(--text-secondary)', lineHeight:1.6 }}>
          {children}
        </div>
      </div>
    </div>
  )
}

function InfoBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <div style={{ fontWeight:600, color:'var(--text-primary)', marginBottom:3, fontSize:12 }}>{label}</div>
      <div style={{ color:'var(--text-secondary)' }}>{text}</div>
    </div>
  )
}

// ── Section header ────────────────────────────────────────────────────────────

interface SectionHeaderProps {
  title: string
  count: number
  statusItems: StatusItem[]
  onInfo: () => void
  onBackfill?: () => void
}

function SectionHeader({ title, count, statusItems, onInfo, onBackfill }: SectionHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    const h = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [menuOpen])

  return (
    <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:12, marginTop:8 }}>
      <StatusIndicator items={statusItems} />
      <Database size={14} color="var(--accent-blue)" />
      <span style={{ fontSize:13, fontWeight:600, color:'var(--text-primary)' }}>{title}</span>
      <span style={{
        background:'var(--bg-elevated)',
        border:'1px solid var(--border-subtle)',
        borderRadius:'var(--radius-pill)',
        padding:'1px 8px',
        fontSize:11,
        color:'var(--text-secondary)',
      }}>{count.toLocaleString()} записей</span>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4 }}>
        {/* Info button — ярче */}
        <button
          onClick={onInfo}
          style={{
            background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.25)',
            borderRadius: 'var(--radius-sm)', cursor: 'pointer', padding: '3px 6px',
            color: 'var(--accent-blue)', display: 'flex', alignItems: 'center',
            transition: 'background 0.15s',
          }}
          title="Информация"
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(59,130,246,0.2)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'rgba(59,130,246,0.1)')}
        >
          <Info size={13} />
        </button>

        {/* Action menu */}
        {onBackfill && (
          <div ref={menuRef} style={{ position: 'relative' }}>
            <button
              onClick={() => setMenuOpen(v => !v)}
              style={{
                background: menuOpen ? 'var(--bg-elevated)' : 'none',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                padding: '3px 6px', color: 'var(--text-secondary)', display: 'flex',
                transition: 'all 0.15s',
              }}
              title="Действия"
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-elevated)')}
              onMouseLeave={e => { if (!menuOpen) e.currentTarget.style.background = 'none' }}
            >
              <MoreHorizontal size={13} />
            </button>
            {menuOpen && createPortal(
              (() => {
                const r = menuRef.current?.getBoundingClientRect()
                if (!r) return null
                return (
                  <div style={{
                    position: 'fixed', top: r.bottom + 4, right: window.innerWidth - r.right,
                    background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
                    borderRadius: 'var(--radius-md)', boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                    zIndex: 300, minWidth: 200, overflow: 'hidden',
                  }}>
                    <button
                      onClick={() => { setMenuOpen(false); onBackfill() }}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                        padding: '10px 14px', background: 'none', border: 'none',
                        cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)',
                        textAlign: 'left', transition: 'background 0.1s',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-elevated)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                    >
                      <Download size={13} color="var(--accent-blue)" />
                      Загрузка исторических данных
                    </button>
                  </div>
                )
              })(),
              document.body
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Candles table ─────────────────────────────────────────────────────────────

function CandlesTable({ rows }: { rows: DbTableStat[] }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  if (rows.length === 0) return (
    <div style={{ color:'var(--text-muted)', fontSize:12, padding:'16px 0' }}>Данных нет</div>
  )
  const sorted = sortCandles(rows)

  const bySymbol: Record<string, DbTableStat[]> = {}
  for (const r of sorted) {
    if (!bySymbol[r.symbol]) bySymbol[r.symbol] = []
    bySymbol[r.symbol].push(r)
  }

  const toggle = (symbol: string) =>
    setExpanded(prev => ({ ...prev, [symbol]: !prev[symbol] }))

  return (
    <div className="card" style={{ overflow:'hidden' }}>
      {/* Column header */}
      <div style={{
        display:'grid',
        gridTemplateColumns:'20px 1fr auto auto auto',
        gap:12,
        padding:'7px 14px',
        background:'var(--bg-elevated)',
        borderBottom:'1px solid var(--border-subtle)',
        fontSize:12,
        color:'var(--text-muted)',
        fontWeight:500,
      }}>
        <span />
        <span>Пара</span>
        <span style={{ whiteSpace:'nowrap' }}>Период</span>
        <span style={{ whiteSpace:'nowrap' }}>Свечей</span>
        <span style={{ whiteSpace:'nowrap' }}>Валидация</span>
      </div>

      {Object.entries(bySymbol).map(([symbol, tfs], i, arr) => {
        const isOpen = !!expanded[symbol]
        const totalCount   = tfs.reduce((s, r) => s + r.count, 0)
        const totalInvalid = tfs.reduce((s, r) => s + r.invalid, 0)
        const from = tfs.map(r => r.from).filter(Boolean).sort()[0] ?? null
        const to   = tfs.map(r => r.to).filter(Boolean).sort().at(-1) ?? null
        const isLast = i === arr.length - 1

        return (
          <div key={symbol}>
            <div
              onClick={() => toggle(symbol)}
              style={{
                display:'grid',
                gridTemplateColumns:'20px 1fr auto auto auto',
                alignItems:'center',
                gap:12,
                padding:'7px 14px',
                borderBottom: (isOpen || !isLast) ? '1px solid var(--border-subtle)' : 'none',
                cursor:'pointer',
                userSelect:'none',
              }}
            >
              <ChevronRight
                size={13}
                color="var(--text-muted)"
                style={{ transition:'transform 0.15s', transform: isOpen ? 'rotate(90deg)' : 'none' }}
              />
              <span style={{ fontFamily:'var(--font-display)', fontWeight:700, fontSize:13, color:'var(--text-primary)' }}>
                {symbol}
              </span>
              <span style={{ fontSize:11, color:'var(--text-muted)', fontFamily:'var(--font-mono)', whiteSpace:'nowrap' }}>
                {from ?? '—'} → {to ?? '—'}
              </span>
              <span style={{ fontSize:11, fontFamily:'var(--font-mono)', color:'var(--text-secondary)', whiteSpace:'nowrap' }}>
                {totalCount.toLocaleString()} св.
              </span>
              <ValidationBadge invalid={totalInvalid} total={totalCount} />
            </div>

            {isOpen && (
              <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                <tbody>
                  {tfs.map((r, ri) => (
                    <tr key={r.timeframe} style={{ borderBottom: (ri < tfs.length - 1 || !isLast) ? '1px solid var(--border-subtle)' : 'none', background:'var(--bg-input)' }}>
                      <td style={{ padding:'7px 14px', width:52 }}>
                        <span style={{
                          background:'var(--bg-elevated)', borderRadius:'var(--radius-sm)',
                          padding:'1px 6px', fontFamily:'var(--font-mono)', fontSize:11, color:'var(--accent-blue)',
                        }}>{r.timeframe}</span>
                      </td>
                      <td style={{ padding:'7px 8px', fontFamily:'var(--font-mono)', color:'var(--text-primary)', fontWeight:600, textAlign:'right' }}>
                        {r.count.toLocaleString()}
                      </td>
                      <td style={{ padding:'7px 8px', color:'var(--text-muted)', fontFamily:'var(--font-mono)', fontSize:11, textAlign:'center' }}>
                        {r.from ?? '—'}
                      </td>
                      <td style={{ padding:'7px 8px', color:'var(--text-muted)', fontFamily:'var(--font-mono)', fontSize:11, textAlign:'center' }}>
                        {r.to ?? '—'}
                      </td>
                      <td style={{ padding:'7px 14px', textAlign:'right' }}>
                        <ValidationBadge invalid={r.invalid} total={r.count} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Order book table ──────────────────────────────────────────────────────────

function OrderBookTable({ rows }: { rows: ObStat[] }) {
  if (rows.length === 0) return (
    <div style={{ color:'var(--text-muted)', fontSize:12, padding:'16px 0' }}>Данных нет</div>
  )
  return (
    <div className="card" style={{ overflow:'hidden' }}>
      <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
        <thead>
          <tr style={{ color:'var(--text-muted)', borderBottom:'1px solid var(--border-subtle)', background:'var(--bg-elevated)' }}>
            <th style={{ textAlign:'left', padding:'7px 14px', fontWeight:500 }}>Пара</th>
            <th style={{ textAlign:'right', padding:'7px 8px', fontWeight:500 }}>Снимков</th>
            <th style={{ textAlign:'center', padding:'7px 8px', fontWeight:500 }}>С</th>
            <th style={{ textAlign:'center', padding:'7px 8px', fontWeight:500 }}>По</th>
            <th style={{ textAlign:'right', padding:'7px 14px', fontWeight:500 }}>Сред. дисбаланс</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} style={{ borderBottom:'1px solid var(--border-subtle)' }}>
              <td style={{ padding:'7px 14px', fontFamily:'var(--font-display)', fontWeight:600, color:'var(--text-primary)' }}>
                {r.symbol}
              </td>
              <td style={{ textAlign:'right', padding:'7px 8px', fontFamily:'var(--font-mono)', color:'var(--text-primary)', fontWeight:600 }}>
                {r.count.toLocaleString()}
              </td>
              <td style={{ textAlign:'center', padding:'7px 8px', color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:11 }}>
                {r.from ?? '—'}
              </td>
              <td style={{ textAlign:'center', padding:'7px 8px', color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:11 }}>
                {r.to ?? '—'}
              </td>
              <td style={{ textAlign:'right', padding:'7px 14px' }}>
                <span style={{ color: Math.abs(r.avg_imbalance) > 0.3 ? 'var(--accent-orange)' : 'var(--text-secondary)', fontFamily:'var(--font-mono)' }}>
                  {r.avg_imbalance > 0 ? '+' : ''}{r.avg_imbalance.toFixed(4)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

interface Props {
  onRequestStats: () => void
  startBackfill: (symbol: string, period: string) => void
}

export default function DataView({ onRequestStats, startBackfill }: Props) {
  const { dbStats, connected } = useStore()
  const [modal,    setModal]    = useState<'candles' | 'orderbook' | null>(null)
  const [backfill, setBackfill] = useState<'candles' | null>(null)

  useEffect(() => {
    if (connected) onRequestStats()
  }, [connected])

  const totalCandles  = dbStats?.candles.reduce((s, r) => s + r.count, 0) ?? 0
  const totalOb       = dbStats?.orderbook.reduce((s, r) => s + r.count, 0) ?? 0
  const anyInvalidC   = (dbStats?.candles.reduce((s, r) => s + r.invalid, 0) ?? 0) === 0
  const anyInvalidOb  = true // orderbook не имеет поля invalid

  const candleStatus: StatusItem[] = [
    { icon: <Wifi size={13} />,        label: 'Сбор данных (WebSocket)',    ok: connected },
    { icon: <Calculator size={13} />,  label: 'Агрегация таймфреймов',      ok: connected },
    { icon: <ShieldCheck size={13} />, label: 'Валидация при записи',        ok: anyInvalidC },
  ]
  const obStatus: StatusItem[] = [
    { icon: <Wifi size={13} />,        label: 'Сбор снимков (WebSocket)',   ok: connected },
    { icon: <Calculator size={13} />,  label: 'Расчёт дисбаланса',          ok: connected },
    { icon: <ShieldCheck size={13} />, label: 'Валидация структуры',         ok: anyInvalidOb },
  ]

  return (
    <div style={{ height:'100%', overflow:'auto', display:'flex', flexDirection:'column', gap:24 }}>
      {/* Page header */}
      <div style={{ width:'100%',display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div>
          <h2 style={{ fontSize:18, fontWeight:700, color:'var(--text-primary)', fontFamily:'var(--font-display)' }}>
            База данных
          </h2>
          <p style={{ fontSize:12, color:'var(--text-muted)', marginTop:4 }}>
            Сводка по накопленным рыночным данным
          </p>
        </div>
        <button
          onClick={onRequestStats}
          style={{
            display:'flex', alignItems:'center', gap:8,
            background:'var(--bg-elevated)', border:'1px solid var(--border-default)',
            borderRadius:'var(--radius-md)', padding:'8px 16px',
            color:'var(--text-secondary)', fontSize:12,
            cursor:'pointer', fontFamily:'var(--font-body)',
          }}
        >
          <RefreshCw size={13} /> Обновить
        </button>
      </div>

      {!dbStats ? (
        <div style={{ width:'100%',display:'flex', gap:16 }}>
          <div style={{ display:'flex', flexDirection:'column', gap:8, flex:1 }}>
            {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height:44, borderRadius:'var(--radius-md)' }} />)}
          </div>
          <div className="skeleton" style={{ height:200, flex:1, borderRadius:'var(--radius-lg)' }} />
        </div>
      ) : (
        <div style={{ width:'100%',display:'flex', gap:20, alignItems:'flex-start' }}>
          {/* Candles */}
          <div style={{ flex:1, minWidth:0 }}>
            <SectionHeader
              title="Свечи (Candles)"
              count={totalCandles}
              statusItems={candleStatus}
              onInfo={() => setModal('candles')}
              onBackfill={() => setBackfill('candles')}
            />
            <CandlesTable rows={dbStats.candles} />
          </div>

          {/* Order Book */}
          <div style={{ flex:1, minWidth:0 }}>
            <SectionHeader
              title="Стакан (Order Book)"
              count={totalOb}
              statusItems={obStatus}
              onInfo={() => setModal('orderbook')}
            />
            <OrderBookTable rows={dbStats.orderbook} />
          </div>
        </div>
      )}

      {/* Info modals */}
      {modal === 'candles' && (
        <InfoModal title="Свечи — как работает сбор данных" onClose={() => setModal(null)}>
          <InfoBlock
            label="Сбор в реальном времени"
            text="BingX WebSocket (wss://open-api-ws.bingx.com/market) подписывается на поток @kline_1min для каждой торговой пары. Каждый тик (~1 сек) upsert-ится в БД. Закрытие свечи определяется по смене open_time — когда начинается новая минута, предыдущая свеча публикуется как closed."
          />
          <InfoBlock
            label="Историческая загрузка (backfill)"
            text="При старте системы REST API BingX автоматически догружает недостающую историю: 1m → 1440 свечей (~1 день), 5m → 1440 (~5 дней), 15m → 1000 (~10 дней), 1h → 720 (~30 дней), 4h → 500 (~83 дня), 1d → 365 (~1 год)."
          />
          <InfoBlock
            label="Агрегация таймфреймов"
            text="TFAggregator агрегирует 1m-свечи в старшие таймфреймы (3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d) в реальном времени. Все таймфреймы также загружаются отдельно через backfill."
          />
          <InfoBlock
            label="Валидация данных"
            text="Pydantic проверяет каждую свечу при записи: цена > 0, объём ≥ 0, high ≥ low. Невалидные свечи отклоняются и публикуются как data.validation_error. Индикатор «невалидных» в таблице — постфактум-проверка open ≤ 0 в БД."
          />
          <InfoBlock
            label="Частота"
            text="Тики: каждую секунду. Закрытые свечи 1m: каждую минуту. Backfill: один раз при старте системы."
          />
        </InfoModal>
      )}

      {modal === 'orderbook' && (
        <InfoModal title="Стакан — как работает сбор данных" onClose={() => setModal(null)}>
          <InfoBlock
            label="Сбор снимков"
            text="BingX WebSocket подписывается на поток @depth20 для каждой пары — 20 лучших уровней bid и ask. Снимок сохраняется в БД каждые ~2 секунды (по событию от биржи)."
          />
          <InfoBlock
            label="Расчёт дисбаланса"
            text="Imbalance = (суммарный объём bid − суммарный объём ask) / общий объём. Значение от −1 до +1: положительное — давление покупателей, отрицательное — продавцов. В таблице отображается среднее за весь период сбора."
          />
          <InfoBlock
            label="Валидация"
            text="OBProcessor проверяет структуру каждого снимка: наличие bid/ask уровней, корректность цен и объёмов через Pydantic. Некорректные снимки не сохраняются."
          />
          <InfoBlock
            label="Частота"
            text="Снимки: каждые ~2 сек на пару (зависит от активности рынка). Исторический backfill стакана не выполняется — данные накапливаются только в реальном времени."
          />
        </InfoModal>
      )}

      {backfill === 'candles' && (
        <BackfillModal
          onClose={() => setBackfill(null)}
          startBackfill={startBackfill}
        />
      )}
    </div>
  )
}
