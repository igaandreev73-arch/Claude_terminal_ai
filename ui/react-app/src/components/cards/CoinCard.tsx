import { CoinAvatar } from '../ui/CoinAvatar'
import { Badge } from '../ui/Badge'
import { mockPrices, mockChanges, mockSparklines } from '../../mock/marketData'

function Sparkline({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const W = 80, H = 36
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W
    const y = H - ((v - min) / range) * H
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={W} height={H} style={{ flexShrink: 0 }}>
      <polyline
        points={pts}
        fill="none"
        stroke={up ? 'var(--accent-green)' : 'var(--accent-red)'}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

interface Props {
  symbol: string
}

export function CoinCard({ symbol }: Props) {
  const price  = mockPrices[symbol] ?? 0
  const change = mockChanges[symbol] ?? 0
  const spark  = mockSparklines[symbol] ?? []
  const ticker = symbol.replace('/USDT', '')
  const up     = change >= 0

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <CoinAvatar symbol={symbol} size="md" />
        <Sparkline data={spark} up={up} />
      </div>
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-display)' }}>
            {ticker}
          </span>
          <Badge value={change} />
        </div>
        <div className="price" style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginTop: 2 }}>
          ${price.toLocaleString('en-US', { minimumFractionDigits: price < 1 ? 4 : 2, maximumFractionDigits: price < 1 ? 4 : 2 })}
        </div>
      </div>
    </div>
  )
}
