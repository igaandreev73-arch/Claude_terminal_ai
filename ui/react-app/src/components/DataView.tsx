import { useEffect } from 'react'
import { RefreshCw, CheckCircle, AlertTriangle, Database } from 'lucide-react'
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

function SectionHeader({ title, count }: { title: string; count: number }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12, marginTop:8 }}>
      <Database size={14} color="var(--accent-blue)" />
      <span style={{ fontSize:13, fontWeight:600, color:'var(--text-primary)' }}>{title}</span>
      <span style={{
        background:'var(--bg-elevated)',
        border:'1px solid var(--border-subtle)',
        borderRadius:'var(--radius-pill)',
        padding:'1px 8px',
        fontSize:11,
        color:'var(--text-secondary)',
      }}>{count} записей</span>
    </div>
  )
}

function CandlesTable({ rows }: { rows: DbTableStat[] }) {
  if (rows.length === 0) return (
    <div style={{ color:'var(--text-muted)', fontSize:12, padding:'16px 0' }}>Данных нет</div>
  )
  const sorted = sortCandles(rows)
  // Group by symbol
  const bySymbol: Record<string, DbTableStat[]> = {}
  for (const r of sorted) {
    if (!bySymbol[r.symbol]) bySymbol[r.symbol] = []
    bySymbol[r.symbol].push(r)
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      {Object.entries(bySymbol).map(([symbol, tfs]) => (
        <div key={symbol} className="card" style={{ padding:16 }}>
          <div style={{ fontSize:13, fontWeight:600, color:'var(--text-primary)', marginBottom:10, fontFamily:'var(--font-display)' }}>
            {symbol}
          </div>
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
            <thead>
              <tr style={{ color:'var(--text-muted)', borderBottom:'1px solid var(--border-subtle)' }}>
                <th style={{ textAlign:'left', padding:'4px 8px', fontWeight:500 }}>ТФ</th>
                <th style={{ textAlign:'right', padding:'4px 8px', fontWeight:500 }}>Свечей</th>
                <th style={{ textAlign:'center', padding:'4px 8px', fontWeight:500 }}>С</th>
                <th style={{ textAlign:'center', padding:'4px 8px', fontWeight:500 }}>По</th>
                <th style={{ textAlign:'center', padding:'4px 8px', fontWeight:500 }}>Валидация</th>
              </tr>
            </thead>
            <tbody>
              {tfs.map((r) => (
                <tr key={r.timeframe} style={{ borderBottom:'1px solid var(--border-subtle)' }}>
                  <td style={{ padding:'6px 8px' }}>
                    <span style={{
                      background:'var(--bg-elevated)',
                      borderRadius:'var(--radius-sm)',
                      padding:'1px 6px',
                      fontFamily:'var(--font-mono)',
                      fontSize:11,
                      color:'var(--accent-blue)',
                    }}>{r.timeframe}</span>
                  </td>
                  <td style={{ textAlign:'right', padding:'6px 8px', fontFamily:'var(--font-mono)', color:'var(--text-primary)', fontWeight:600 }}>
                    {r.count.toLocaleString()}
                  </td>
                  <td style={{ textAlign:'center', padding:'6px 8px', color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:11 }}>
                    {r.from ?? '—'}
                  </td>
                  <td style={{ textAlign:'center', padding:'6px 8px', color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:11 }}>
                    {r.to ?? '—'}
                  </td>
                  <td style={{ textAlign:'center', padding:'6px 8px' }}>
                    <ValidationBadge invalid={r.invalid} total={r.count} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

function OrderBookTable({ rows }: { rows: ObStat[] }) {
  if (rows.length === 0) return (
    <div style={{ color:'var(--text-muted)', fontSize:12, padding:'16px 0' }}>Данных нет</div>
  )
  return (
    <div className="card" style={{ padding:16 }}>
      <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
        <thead>
          <tr style={{ color:'var(--text-muted)', borderBottom:'1px solid var(--border-subtle)' }}>
            <th style={{ textAlign:'left', padding:'4px 8px', fontWeight:500 }}>Пара</th>
            <th style={{ textAlign:'right', padding:'4px 8px', fontWeight:500 }}>Снимков</th>
            <th style={{ textAlign:'center', padding:'4px 8px', fontWeight:500 }}>С</th>
            <th style={{ textAlign:'center', padding:'4px 8px', fontWeight:500 }}>По</th>
            <th style={{ textAlign:'right', padding:'4px 8px', fontWeight:500 }}>Сред. дисбаланс</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} style={{ borderBottom:'1px solid var(--border-subtle)' }}>
              <td style={{ padding:'6px 8px', fontFamily:'var(--font-display)', fontWeight:600, color:'var(--text-primary)' }}>
                {r.symbol}
              </td>
              <td style={{ textAlign:'right', padding:'6px 8px', fontFamily:'var(--font-mono)', color:'var(--text-primary)', fontWeight:600 }}>
                {r.count.toLocaleString()}
              </td>
              <td style={{ textAlign:'center', padding:'6px 8px', color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:11 }}>
                {r.from ?? '—'}
              </td>
              <td style={{ textAlign:'center', padding:'6px 8px', color:'var(--text-secondary)', fontFamily:'var(--font-mono)', fontSize:11 }}>
                {r.to ?? '—'}
              </td>
              <td style={{ textAlign:'right', padding:'6px 8px' }}>
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

interface Props {
  onRequestStats: () => void
}

export default function DataView({ onRequestStats }: Props) {
  const { dbStats } = useStore()

  useEffect(() => {
    onRequestStats()
  }, [])

  const totalCandles = dbStats?.candles.reduce((s, r) => s + r.count, 0) ?? 0
  const totalOb      = dbStats?.orderbook.reduce((s, r) => s + r.count, 0) ?? 0

  return (
    <div style={{ height:'100%', overflow:'auto', display:'flex', flexDirection:'column', gap:24 }}>
      {/* Header */}
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
            background:'var(--bg-elevated)',
            border:'1px solid var(--border-default)',
            borderRadius:'var(--radius-md)',
            padding:'8px 16px',
            color:'var(--text-secondary)',
            fontSize:12,
            cursor:'pointer',
            fontFamily:'var(--font-body)',
            transition:'color 0.15s',
          }}
        >
          <RefreshCw size={13} /> Обновить
        </button>
      </div>

      {!dbStats ? (
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height:80, borderRadius:'var(--radius-lg)' }} />)}
        </div>
      ) : (
        <>
          {/* Candles */}
          <section>
            <SectionHeader title="Свечи (Candles)" count={totalCandles} />
            <CandlesTable rows={dbStats.candles} />
          </section>

          {/* Order Book */}
          <section>
            <SectionHeader title="Стакан (Order Book)" count={totalOb} />
            <OrderBookTable rows={dbStats.orderbook} />
          </section>
        </>
      )}
    </div>
  )
}
