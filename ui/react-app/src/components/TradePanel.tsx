import React, { useState } from 'react'

const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']

interface Props {
  onOpenPosition: (params: {
    symbol: string
    direction: 'bull' | 'bear'
    size_usd: number
    leverage: number
    sl_pct: number
    tp_pct: number
  }) => void
}

export default function TradePanel({ onOpenPosition }: Props) {
  const [symbol, setSymbol] = useState('BTC/USDT')
  const [direction, setDirection] = useState<'bull' | 'bear'>('bull')
  const [capital, setCapital] = useState(10000)
  const [riskPct, setRiskPct] = useState(1)
  const [leverage, setLeverage] = useState(3)
  const [slPct, setSlPct] = useState(2)
  const [tpPct, setTpPct] = useState(4)

  const slDecimal = slPct / 100
  const sizeUsd = slDecimal > 0
    ? (capital * (riskPct / 100)) / (slDecimal / leverage)
    : 0

  const rr = tpPct / slPct

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onOpenPosition({ symbol, direction, size_usd: sizeUsd, leverage, sl_pct: slDecimal, tp_pct: tpPct / 100 })
  }

  return (
    <div className="trade-panel">
      <h2>Trade Panel</h2>
      <form className="trade-form" onSubmit={handleSubmit}>
        {/* Symbol */}
        <div className="form-row">
          <label>Пара</label>
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {SYMBOLS.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>

        {/* Direction */}
        <div className="form-row">
          <label>Направление</label>
          <div className="direction-toggle">
            <button
              type="button"
              className={`dir-btn bull ${direction === 'bull' ? 'active' : ''}`}
              onClick={() => setDirection('bull')}
            >▲ LONG</button>
            <button
              type="button"
              className={`dir-btn bear ${direction === 'bear' ? 'active' : ''}`}
              onClick={() => setDirection('bear')}
            >▼ SHORT</button>
          </div>
        </div>

        {/* Capital */}
        <div className="form-row">
          <label>Капитал ($)</label>
          <input type="number" value={capital} min={100}
            onChange={(e) => setCapital(Number(e.target.value))} />
        </div>

        {/* Risk */}
        <div className="form-row">
          <label>Риск (%)</label>
          <input type="number" value={riskPct} min={0.1} max={10} step={0.1}
            onChange={(e) => setRiskPct(Number(e.target.value))} />
        </div>

        {/* Leverage */}
        <div className="form-row">
          <label>Плечо (x)</label>
          <input type="number" value={leverage} min={1} max={20}
            onChange={(e) => setLeverage(Number(e.target.value))} />
        </div>

        {/* SL / TP */}
        <div className="form-row">
          <label>Stop Loss (%)</label>
          <input type="number" value={slPct} min={0.1} max={20} step={0.1}
            onChange={(e) => setSlPct(Number(e.target.value))} />
        </div>
        <div className="form-row">
          <label>Take Profit (%)</label>
          <input type="number" value={tpPct} min={0.1} max={50} step={0.1}
            onChange={(e) => setTpPct(Number(e.target.value))} />
        </div>

        {/* Calculator result */}
        <div className="calc-result">
          <div className="calc-row">
            <span>Размер позиции</span>
            <strong>${sizeUsd.toFixed(2)}</strong>
          </div>
          <div className="calc-row">
            <span>Risk/Reward</span>
            <strong style={{ color: rr >= 1.5 ? '#00ff88' : '#ffa500' }}>
              1 : {rr.toFixed(2)}
            </strong>
          </div>
          <div className="calc-row">
            <span>Макс. убыток</span>
            <strong style={{ color: '#ff4444' }}>
              ${(capital * riskPct / 100).toFixed(2)}
            </strong>
          </div>
          <div className="calc-row">
            <span>Потенциал</span>
            <strong style={{ color: '#00ff88' }}>
              ${(capital * riskPct / 100 * rr).toFixed(2)}
            </strong>
          </div>
        </div>

        <button
          type="submit"
          className={`submit-btn ${direction}`}
          disabled={sizeUsd <= 0}
        >
          {direction === 'bull' ? '▲ Открыть LONG' : '▼ Открыть SHORT'}
        </button>
      </form>
    </div>
  )
}
