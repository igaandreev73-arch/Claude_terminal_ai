import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { RefreshCw, CheckCircle, AlertTriangle, Database, ChevronRight, Info, X, Wifi, Calculator, ShieldCheck } from 'lucide-react'
import { useStore } from '../store/useStore'
import type { DbTableStat, ObStat } from '../store/useStore'

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
}

function SectionHeader({ title, count, statusItems, onInfo }: SectionHeaderProps) {
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
      <button
        onClick={onInfo}
        style={{ background:'none', border:'none', cursor:'pointer', padding:2, color:'var(--text-muted)', display:'flex', marginLeft:2 }}
        title="Информация"
      >
        <Info size={14} />
      </button>
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
}

export default function DataView({ onRequestStats }: Props) {
  const { dbStats, connected } = useStore()
  const [modal, setModal] = useState<'candles' | 'orderbook' | null>(null)

  useEffect(() => { onRequestStats() }, [])

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
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
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
        <div style={{ display:'flex', gap:16 }}>
          <div style={{ display:'flex', flexDirection:'column', gap:8, flex:'0 0 480px' }}>
            {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height:44, borderRadius:'var(--radius-md)' }} />)}
          </div>
          <div className="skeleton" style={{ height:200, flex:'0 0 600px', borderRadius:'var(--radius-lg)' }} />
        </div>
      ) : (
        <div style={{ display:'flex', gap:20, alignItems:'flex-start' }}>
          {/* Candles */}
          <div style={{ flex:'0 0 480px' }}>
            <SectionHeader
              title="Свечи (Candles)"
              count={totalCandles}
              statusItems={candleStatus}
              onInfo={() => setModal('candles')}
            />
            <CandlesTable rows={dbStats.candles} />
          </div>

          {/* Order Book */}
          <div style={{ flex:'0 0 600px' }}>
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
    </div>
  )
}
