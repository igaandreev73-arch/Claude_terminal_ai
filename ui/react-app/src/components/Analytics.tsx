import { useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { useStore } from '../store/useStore'
import type { Signal } from '../types'
import { X } from 'lucide-react'

// ── Signal Detail Modal ───────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--accent-green)'
  if (score >= 60) return 'var(--accent-orange)'
  return 'var(--text-muted)'
}

function SignalDetailModal({ sig, onClose }: { sig: Signal; onClose: () => void }) {
  const now = Date.now()
  const createdAt  = new Date(sig.created_at).getTime()
  const expiresAt  = new Date(sig.expires_at).getTime()
  const ageMs  = now - createdAt
  const ttlMs  = expiresAt - now
  const ageStr = ageMs < 60_000 ? `${Math.round(ageMs / 1000)}с назад` : `${Math.round(ageMs / 60_000)}м назад`
  const ttlStr = ttlMs > 0
    ? (ttlMs < 60_000 ? `${Math.round(ttlMs / 1000)}с` : `${Math.round(ttlMs / 60_000)}м`)
    : 'Истёк'
  const isLong = sig.direction === 'bull'
  const dirColor = isLong ? 'var(--accent-green)' : '#f87171'
  const dirLabel = isLong ? '▲ LONG' : '▼ SHORT'

  // Разбираем source: может содержать таймфрейм в формате "MTF:1h" или просто "mtf_confluence"
  const sourceParts = sig.source?.split(':') ?? [sig.source ?? '']
  const sourceName = sourceParts[0]
  const sourceTf   = sourceParts[1]

  return createPortal(
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 500, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        style={{ background: 'var(--bg-surface)', border: `1px solid ${dirColor}44`, borderRadius: 'var(--radius-xl)', padding: '28px 32px', maxWidth: 520, width: '90%', boxShadow: '0 12px 48px rgba(0,0,0,0.7)', display: 'flex', flexDirection: 'column', gap: 20 }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 48, height: 48, borderRadius: 'var(--radius-md)', background: dirColor + '15', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: dirColor }}>
              {isLong ? '▲' : '▼'}
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 20, color: 'var(--text-primary)' }}>{sig.symbol}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: dirColor }}>{dirLabel}</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}><X size={18} /></button>
        </div>

        <div style={{ height: 1, background: `linear-gradient(90deg, ${dirColor}55, transparent)` }} />

        {/* Score */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ flex: 1, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '14px 18px', textAlign: 'center' }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>SCORE</div>
            <div style={{ fontSize: 32, fontWeight: 800, fontFamily: 'var(--font-mono)', color: scoreColor(sig.score) }}>{sig.score.toFixed(1)}</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>из 100</div>
          </div>
          <div style={{ flex: 1, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '14px 18px', textAlign: 'center' }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>РЕЖИМ</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: sig.auto_eligible ? 'var(--accent-green)' : 'var(--accent-orange)' }}>
              {sig.auto_eligible ? '⚡ Авто' : '👤 Ручной'}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
              {sig.auto_eligible ? 'score ≥ 80' : 'score < 80'}
            </div>
          </div>
        </div>

        {/* Details */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[
            { label: 'Источник сигнала', value: sourceName || '—' },
            { label: 'Таймфрейм',        value: sourceTf || 'Все TF' },
            { label: 'Создан',           value: `${new Date(sig.created_at).toLocaleString('ru')} (${ageStr})` },
            { label: 'Истекает',         value: `${new Date(sig.expires_at).toLocaleString('ru')} (${ttlStr})` },
            { label: 'ID сигнала',       value: sig.id, mono: true },
          ].map(({ label, value, mono }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
              <span style={{ fontSize: 12, fontFamily: mono ? 'var(--font-mono)' : undefined, color: 'var(--text-secondary)', textAlign: 'right', wordBreak: 'break-all' }}>{value}</span>
            </div>
          ))}
        </div>

        {/* Score interpretation */}
        <div style={{ background: scoreColor(sig.score) + '10', border: `1px solid ${scoreColor(sig.score)}33`, borderRadius: 'var(--radius-md)', padding: '12px 14px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: scoreColor(sig.score), marginBottom: 5, fontFamily: 'var(--font-mono)' }}>
            ИНТЕРПРЕТАЦИЯ СИГНАЛА
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {sig.score >= 80
              ? `Сильный сигнал (≥80). Большинство индикаторов MTF подтверждают ${isLong ? 'бычье' : 'медвежье'} направление. Доступно авто-исполнение.`
              : sig.score >= 60
                ? `Умеренный сигнал (60–79). Часть индикаторов подтверждает направление. Рекомендуется ручная проверка перед входом.`
                : `Слабый сигнал (<60). Мало подтверждений из MTF-анализа. Высокий риск ложного сигнала.`}
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Signals list ──────────────────────────────────────────────────────────────

function SignalsList() {
  const signals = useStore(s => s.signals)
  const [selected, setSelected] = useState<Signal | null>(null)

  if (signals.length === 0) return null

  return (
    <div style={{ marginBottom: 24 }}>
      <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12, fontFamily: 'var(--font-display)' }}>
        Активные сигналы <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', background: 'rgba(34,211,165,0.12)', color: 'var(--accent-green)', padding: '1px 8px', borderRadius: 10, marginLeft: 6 }}>{signals.length}</span>
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {signals.map(sig => {
          const isLong = sig.direction === 'bull'
          const dirColor = isLong ? 'var(--accent-green)' : '#f87171'
          return (
            <div
              key={sig.id}
              onClick={() => setSelected(sig)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 14px', borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface)', border: `1px solid ${dirColor}33`,
                cursor: 'pointer', transition: 'background 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = dirColor + '08')}
              onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-surface)')}
            >
              <span style={{ fontSize: 16, color: dirColor }}>{isLong ? '▲' : '▼'}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13, color: 'var(--text-primary)', minWidth: 90 }}>{sig.symbol}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', flex: 1 }}>{sig.source}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 14, color: scoreColor(sig.score) }}>
                {sig.score.toFixed(0)}
              </span>
              {sig.auto_eligible && (
                <span style={{ fontSize: 10, color: 'var(--accent-green)', background: 'rgba(34,211,165,0.1)', padding: '2px 6px', borderRadius: 4 }}>⚡ Авто</span>
              )}
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>›</span>
            </div>
          )
        })}
      </div>
      {selected && <SignalDetailModal sig={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

// ── Main Analytics ────────────────────────────────────────────────────────────

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
      <h2>Аналитика &amp; журнал сделок</h2>

      {/* Signals */}
      <SignalsList />

      {stats && (
        <div className="analytics-stats">
          <StatCard label="Всего сделок" value={stats.total} />
          <StatCard label="Процент побед" value={`${stats.winRate.toFixed(1)}%`}
            color={stats.winRate >= 50 ? '#00ff88' : '#ff4444'} />
          <StatCard label="Общий PnL" value={`$${stats.totalPnl.toFixed(2)}`}
            color={stats.totalPnl >= 0 ? '#00ff88' : '#ff4444'} />
          <StatCard label="Профит-фактор"
            value={stats.profitFactor != null ? stats.profitFactor.toFixed(2) : '∞'}
            color={stats.profitFactor == null || stats.profitFactor >= 1.5 ? '#00ff88' : '#ffa500'} />
          <StatCard label="Средний выигрыш" value={`$${stats.avgWin.toFixed(2)}`} color="#00ff88" />
          <StatCard label="Средний убыток" value={`$${stats.avgLoss.toFixed(2)}`} color="#ff4444" />
        </div>
      )}

      {/* Trade Journal */}
      <div className="journal-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th><th>Пара</th><th>Направление</th><th>Цена входа</th>
              <th>Цена выхода</th><th>Объём</th><th>PnL</th><th>PnL %</th><th>Закрыта по</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr><td colSpan={9} style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>Нет сделок</td></tr>
            ) : (
              trades.map((t, i) => (
                <tr key={t.trade_id + i}>
                  <td>{trades.length - i}</td>
                  <td>{t.symbol ?? '—'}</td>
                  <td><span className={`direction ${t.direction}`}>{t.direction === 'bull' ? '▲ Лонг' : '▼ Шорт'}</span></td>
                  <td>{t.entry_price.toFixed(4)}</td>
                  <td>{t.exit_price.toFixed(4)}</td>
                  <td>${t.size_usd.toFixed(0)}</td>
                  <td style={{ color: t.pnl >= 0 ? '#00ff88' : '#ff4444' }}>{t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}</td>
                  <td style={{ color: t.pnl_pct >= 0 ? '#00ff88' : '#ff4444' }}>{t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%</td>
                  <td><span className={`close-reason ${t.closed_by}`}>{t.closed_by}</span></td>
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
