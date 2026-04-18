import { useStore } from '../store/useStore'
import type { ExecutionMode } from '../types'

const MODE_LABELS: Record<ExecutionMode, string> = {
  auto: 'AUTO',
  semi_auto: 'SEMI-AUTO',
  alert_only: 'ALERT ONLY',
}
const MODE_COLORS: Record<ExecutionMode, string> = {
  auto: '#00ff88',
  semi_auto: '#ffa500',
  alert_only: '#888',
}

interface Props {
  onConfirm: (signalId: string) => void
  onReject: (signalId: string) => void
  onClose: (symbol: string) => void
  onModeChange: (mode: ExecutionMode) => void
}

export default function Dashboard({ onConfirm, onReject, onClose, onModeChange }: Props) {
  const { connected, mode, positions, signals, demoStats } = useStore()

  return (
    <div className="dashboard">
      {/* Status bar */}
      <div className="status-bar">
        <span className={`dot ${connected ? 'dot-green' : 'dot-red'}`} />
        <span>{connected ? 'Подключено' : 'Переподключение...'}</span>
        <span className="mode-badge" style={{ color: MODE_COLORS[mode] }}>
          Режим: {MODE_LABELS[mode]}
        </span>
        <div className="mode-buttons">
          {(['alert_only', 'semi_auto', 'auto'] as ExecutionMode[]).map((m) => (
            <button
              key={m}
              className={`mode-btn ${mode === m ? 'active' : ''}`}
              onClick={() => onModeChange(m)}
            >
              {MODE_LABELS[m]}
            </button>
          ))}
        </div>
      </div>

      <div className="dashboard-grid">
        {/* Open Positions */}
        <section className="card">
          <h2>Открытые позиции <span className="badge">{positions.length}</span></h2>
          {positions.length === 0 ? (
            <p className="empty">Нет открытых позиций</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Пара</th><th>Направление</th><th>Цена входа</th>
                  <th>Размер USD</th><th>Открыта</th><th></th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <tr key={pos.symbol}>
                    <td><strong>{pos.symbol}</strong></td>
                    <td>
                      <span className={`direction ${pos.direction}`}>
                        {pos.direction === 'bull' ? '▲ LONG' : '▼ SHORT'}
                      </span>
                    </td>
                    <td>{pos.entry_price.toFixed(4)}</td>
                    <td>{pos.size_usd.toFixed(2)}</td>
                    <td>{new Date(pos.opened_at).toLocaleTimeString('ru')}</td>
                    <td>
                      <button className="btn-danger btn-sm" onClick={() => onClose(pos.symbol)}>
                        Закрыть
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Active Signals */}
        <section className="card">
          <h2>Активные сигналы <span className="badge">{signals.length}</span></h2>
          {signals.length === 0 ? (
            <p className="empty">Нет активных сигналов</p>
          ) : (
            <div className="signals-list">
              {signals.map((sig) => (
                <div key={sig.id} className={`signal-card ${sig.direction}`}>
                  <div className="signal-header">
                    <strong>{sig.symbol}</strong>
                    <span className={`direction ${sig.direction}`}>
                      {sig.direction === 'bull' ? '▲ LONG' : '▼ SHORT'}
                    </span>
                    <span className="score-badge" style={{ background: scoreColor(sig.score) }}>
                      {sig.score.toFixed(1)}
                    </span>
                  </div>
                  <div className="signal-meta">
                    <span>{sig.source}</span>
                    <span>{sig.auto_eligible ? '⚡ Авто' : '👤 Ручной'}</span>
                  </div>
                  {mode === 'semi_auto' && (
                    <div className="signal-actions">
                      <button className="btn-green btn-sm" onClick={() => onConfirm(sig.id)}>
                        ✓ Подтвердить
                      </button>
                      <button className="btn-danger btn-sm" onClick={() => onReject(sig.id)}>
                        ✗ Отклонить
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Demo Stats */}
        <section className="card">
          <h2>Бумажная торговля</h2>
          <div className="stats-grid">
            <StatBox label="Сделок" value={demoStats.total_trades ?? 0} />
            <StatBox label="Процент побед" value={`${(demoStats.win_rate_pct ?? 0).toFixed(1)}%`} />
            <StatBox
              label="Общий PnL"
              value={`${(demoStats.total_pnl ?? 0).toFixed(2)}`}
              color={(demoStats.total_pnl ?? 0) >= 0 ? '#00ff88' : '#ff4444'}
            />
            <StatBox label="Макс. просадка" value={`${(demoStats.max_drawdown_pct ?? 0).toFixed(1)}%`} color="#ffa500" />
            <StatBox label="Шарп" value={(demoStats.sharpe_ratio ?? 0).toFixed(2)} />
            <StatBox label="Капитал" value={`$${(demoStats.capital ?? 0).toFixed(2)}`} />
          </div>
        </section>
      </div>
    </div>
  )
}

function StatBox({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="stat-box">
      <div className="stat-value" style={{ color: color ?? 'var(--text-primary)' }}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

function scoreColor(score: number): string {
  if (score >= 80) return '#00aa44'
  if (score >= 60) return '#887700'
  return '#555'
}
