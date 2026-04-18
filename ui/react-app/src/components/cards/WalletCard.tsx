import { mockWalletAlloc } from '../../mock/marketData'

const R = 54
const CIRC = 2 * Math.PI * R  // ~339

function DonutChart() {
  let offset = 0
  const segments = mockWalletAlloc.map((item) => {
    const dash = (item.pct / 100) * CIRC
    const gap  = CIRC - dash
    const seg  = { ...item, dash, gap, offset }
    offset += dash
    return seg
  })

  return (
    <svg width={130} height={130} viewBox="0 0 130 130" style={{ flexShrink: 0 }}>
      {/* BG ring */}
      <circle cx={65} cy={65} r={R} fill="none" stroke="var(--bg-elevated)" strokeWidth={12} />
      {segments.map((seg) => (
        <circle
          key={seg.symbol}
          cx={65} cy={65} r={R}
          fill="none"
          stroke={seg.color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${seg.dash - 2} ${seg.gap + 2}`}
          strokeDashoffset={-seg.offset + CIRC / 4}
          style={{ transition: 'stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)' }}
        />
      ))}
      {/* Center label */}
      <text x={65} y={60} textAnchor="middle" fill="var(--accent-green)"
        style={{ fontSize: 13, fontFamily: 'Space Grotesk', fontWeight: 700 }}>
        +2.31%
      </text>
      <text x={65} y={76} textAnchor="middle" fill="var(--text-muted)"
        style={{ fontSize: 10, fontFamily: 'DM Sans' }}>
        портфель
      </text>
    </svg>
  )
}

export function WalletCard() {
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Кошелёк
        </span>
        <button className="btn-ghost">Управление</button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <DonutChart />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, flex: 1 }}>
          {mockWalletAlloc.map((item) => (
            <div key={item.symbol} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: item.color, flexShrink: 0 }} />
              <span style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}>{item.symbol}</span>
              <span className="price" style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                {item.pct}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
