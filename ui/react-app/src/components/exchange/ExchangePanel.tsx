import { useState } from 'react'
import { ArrowLeftRight } from 'lucide-react'
import { mockPrices } from '../../mock/marketData'

const COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']

export function ExchangePanel() {
  const [from, setFrom] = useState('BTC')
  const [to, setTo]     = useState('USDT')
  const [amount, setAmount] = useState('1')

  const fromPrice = mockPrices[`${from}/USDT`] ?? 1
  const toPrice   = to === 'USDT' ? 1 : (mockPrices[`${to}/USDT`] ?? 1)
  const result    = (parseFloat(amount) || 0) * fromPrice / toPrice

  function swap() {
    if (to !== 'USDT') {
      setFrom(to)
      setTo(from)
    }
  }

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Обмен
        </span>
        <button
          onClick={swap}
          style={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 8,
            padding: '5px 8px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ArrowLeftRight size={13} color="var(--text-secondary)" />
        </button>
      </div>

      {/* Rate */}
      <div style={{ textAlign: 'center', padding: '8px 0' }}>
        <div className="price" style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
          1 {from} = {fromPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
        </div>
      </div>

      {/* From */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label style={{ fontSize: 11, color: 'var(--text-muted)' }}>Вы отправляете</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            className="input-field"
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            min="0"
            style={{ flex: 1 }}
          />
          <select
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              padding: '0 10px',
              fontSize: 13,
              fontFamily: 'var(--font-display)',
              cursor: 'pointer',
              outline: 'none',
              width: 72,
            }}
          >
            {COINS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* To */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label style={{ fontSize: 11, color: 'var(--text-muted)' }}>Вы получаете</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <div className="input-field" style={{ flex: 1, display: 'flex', alignItems: 'center', color: 'var(--text-secondary)' }}>
            <span className="price">
              {result.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
            </span>
          </div>
          <select
            value={to}
            onChange={(e) => setTo(e.target.value)}
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              padding: '0 10px',
              fontSize: 13,
              fontFamily: 'var(--font-display)',
              cursor: 'pointer',
              outline: 'none',
              width: 72,
            }}
          >
            <option value="USDT">USDT</option>
            {COINS.filter((c) => c !== from).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      <div style={{ marginTop: 'auto' }}>
        <button className="btn-primary">Обменять</button>
      </div>
    </div>
  )
}
