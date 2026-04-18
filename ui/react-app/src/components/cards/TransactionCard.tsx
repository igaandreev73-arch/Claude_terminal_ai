import { ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import { CoinAvatar } from '../ui/CoinAvatar'
import { useStore } from '../../store/useStore'
import { mockTransactions } from '../../mock/marketData'

export function TransactionCard() {
  const { trades } = useStore()

  // Use real trades if available, else mock
  const items = trades.length > 0
    ? trades.slice(0, 5).map((t) => ({
        id: t.trade_id,
        symbol: t.symbol ?? '—',
        type: (t.pnl >= 0 ? 'receive' : 'send') as 'receive' | 'send',
        amount: t.size_usd,
        usd: t.pnl,
        time: new Date(t.exit_time * 1000).toLocaleTimeString(),
      }))
    : mockTransactions

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Транзакции
        </span>
        <button className="btn-pill active">All</button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {items.map((tx, i) => (
          <div key={tx.id} style={{
            display: 'grid',
            gridTemplateColumns: '28px 1fr auto',
            alignItems: 'center',
            gap: 10,
            padding: '10px 0',
            borderBottom: i < items.length - 1 ? '1px solid var(--border-subtle)' : 'none',
            transition: 'background 0.15s',
          }}>
            <CoinAvatar symbol={tx.symbol} size="sm" />
            <div>
              <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
                {tx.symbol.replace('/USDT', '')}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                {tx.type === 'receive'
                  ? <><ArrowDownLeft size={10} color="var(--accent-green)" /> Получение</>
                  : <><ArrowUpRight size={10} color="var(--accent-red)" /> Отправка</>
                }
                <span style={{ marginLeft: 4 }}>{tx.time}</span>
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className={`price ${tx.type === 'receive' ? 'positive' : 'negative'}`}
                style={{ fontSize: 13, fontWeight: 600 }}>
                {tx.type === 'receive' ? '+' : '-'}${Math.abs(tx.usd).toFixed(2)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                {tx.amount.toFixed(4)} {tx.symbol.replace('/USDT', '')}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
