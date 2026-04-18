import { TrendingUp, TrendingDown } from 'lucide-react'
import { useStore } from '../../store/useStore'

export function BalanceCard() {
  const { demoStats } = useStore()
  const capital = (demoStats['capital'] as number) ?? 10000
  const pnl     = (demoStats['total_pnl'] as number) ?? 0
  const change  = capital > 0 ? (pnl / (capital - pnl)) * 100 : 0

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Общий баланс
        </span>
        <span className={`badge-${change >= 0 ? 'up' : 'down'}`}>
          {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(2)}%
        </span>
      </div>

      {/* Main number */}
      <div>
        <span className="balance price-flash" style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}>
          ${capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      </div>

      {/* Income / Expenses */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 12,
        paddingTop: 12,
        borderTop: '1px solid var(--border-subtle)',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <div style={{ width: 20, height: 20, borderRadius: 6, background: 'rgba(34,211,165,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <TrendingUp size={11} color="var(--accent-green)" />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Прибыль</span>
          </div>
          <span className="price positive" style={{ fontSize: 15, fontWeight: 600 }}>
            +${Math.max(0, pnl).toFixed(2)}
          </span>
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <div style={{ width: 20, height: 20, borderRadius: 6, background: 'rgba(244,63,94,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <TrendingDown size={11} color="var(--accent-red)" />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Убыток</span>
          </div>
          <span className="price negative" style={{ fontSize: 15, fontWeight: 600 }}>
            -${Math.abs(Math.min(0, pnl)).toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  )
}
