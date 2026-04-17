import { useMemo } from 'react'
import { useStore } from '../store/useStore'

export default function Analytics() {
  const { trades } = useStore()

  const stats = useMemo(() => {
    if (trades.length === 0) return null
    const pnls = trades.map((t) => t.pnl)
    const wins = pnls.filter((p) => p > 0)
    const losses = pnls.filter((p) => p <= 0)
    return {
      total: trades.length,
      winRate: (wins.length / trades.length) * 100,
      totalPnl: pnls.reduce((a, b) => a + b, 0),
      grossProfit: wins.reduce((a, b) => a + b, 0),
      grossLoss: Math.abs(losses.reduce((a, b) => a + b, 0)),
      profitFactor: losses.length === 0 ? null : wins.reduce((a, b) => a + b, 0) / Math.abs(losses.reduce((a, b) => a + b, 0)),
      avgWin: wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0,
      avgLoss: losses.length ? Math.abs(losses.reduce((a, b) => a + b, 0)) / losses.length : 0,
    }
  }, [trades])

  return (
    <div className="analytics">
      <h2>Аналитика &amp; Журнал сделок</h2>

      {stats && (
        <div className="analytics-stats">
          <StatCard label="Всего сделок" value={stats.total} />
          <StatCard label="Win Rate" value={`${stats.winRate.toFixed(1)}%`}
            color={stats.winRate >= 50 ? '#00ff88' : '#ff4444'} />
          <StatCard label="Total PnL" value={`$${stats.totalPnl.toFixed(2)}`}
            color={stats.totalPnl >= 0 ? '#00ff88' : '#ff4444'} />
          <StatCard label="Profit Factor"
            value={stats.profitFactor != null ? stats.profitFactor.toFixed(2) : '∞'}
            color={stats.profitFactor == null || stats.profitFactor >= 1.5 ? '#00ff88' : '#ffa500'} />
          <StatCard label="Avg Win" value={`$${stats.avgWin.toFixed(2)}`} color="#00ff88" />
          <StatCard label="Avg Loss" value={`$${stats.avgLoss.toFixed(2)}`} color="#ff4444" />
        </div>
      )}

      {/* Trade Journal */}
      <div className="journal-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Пара</th>
              <th>Направление</th>
              <th>Вход</th>
              <th>Выход</th>
              <th>Размер</th>
              <th>PnL</th>
              <th>PnL %</th>
              <th>Закрыта</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr><td colSpan={9} className="empty">Нет сделок</td></tr>
            ) : (
              trades.map((t, i) => (
                <tr key={t.trade_id + i}>
                  <td>{trades.length - i}</td>
                  <td>{t.symbol ?? '—'}</td>
                  <td>
                    <span className={`direction ${t.direction}`}>
                      {t.direction === 'bull' ? '▲ L' : '▼ S'}
                    </span>
                  </td>
                  <td>{t.entry_price.toFixed(4)}</td>
                  <td>{t.exit_price.toFixed(4)}</td>
                  <td>${t.size_usd.toFixed(0)}</td>
                  <td style={{ color: t.pnl >= 0 ? '#00ff88' : '#ff4444' }}>
                    {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
                  </td>
                  <td style={{ color: t.pnl_pct >= 0 ? '#00ff88' : '#ff4444' }}>
                    {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                  </td>
                  <td>
                    <span className={`close-reason ${t.closed_by}`}>{t.closed_by}</span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="stat-box">
      <div className="stat-value" style={{ color: color ?? 'var(--text-primary)' }}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}
