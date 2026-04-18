import { useState } from 'react'
import {
  ResponsiveContainer, ComposedChart, Line, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import { mockGrowthData } from '../../mock/marketData'

const TF_TABS = ['1 мин', '3 мин', '30 мин', '1 час', '24 часа', '1 день', '1 неделя']

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border-default)',
      borderRadius: 10,
      padding: 12,
      fontSize: 12,
      fontFamily: 'var(--font-mono)',
      boxShadow: 'var(--shadow-elevated)',
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 8 }}>Время: {label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: p.color, display: 'inline-block' }} />
          <span style={{ color: 'var(--text-secondary)' }}>{p.name.toUpperCase()}</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600, marginLeft: 'auto' }}>
            ${Number(p.value).toLocaleString('en-US', { maximumFractionDigits: 0 })}
          </span>
        </div>
      ))}
    </div>
  )
}

export function GrowthChart() {
  const [activeTf, setActiveTf] = useState('24 hour')

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16, height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Общий рост
        </span>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {TF_TABS.map((tf) => (
            <button
              key={tf}
              className={`btn-pill ${activeTf === tf ? 'active' : ''}`}
              onClick={() => setActiveTf(tf)}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={mockGrowthData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
            <XAxis
              dataKey="time"
              tick={{ fill: '#55555f', fontSize: 11, fontFamily: 'JetBrains Mono' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="price"
              tick={{ fill: '#55555f', fontSize: 11, fontFamily: 'JetBrains Mono' }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              width={44}
            />
            <YAxis
              yAxisId="vol"
              orientation="right"
              hide
            />
            <Tooltip content={<CustomTooltip />} />
            <Bar yAxisId="vol" dataKey="btc" name="volume" fill="rgba(59,130,246,0.12)" radius={[2, 2, 0, 0]} />
            <Line yAxisId="price" type="monotone" dataKey="btc" name="btc"
              stroke="#f59e0b" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: '#f59e0b' }} />
            <Line yAxisId="price" type="monotone" dataKey="eth" name="eth"
              stroke="#a78bfa" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: '#a78bfa' }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
