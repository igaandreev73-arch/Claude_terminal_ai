import React, { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useStore } from '../store/useStore'
import type { BacktestResultUI, OptimizerResultUI } from '../store/useStore'
import {
  Activity, BarChart2, BookOpen, Brain, Clock,
  Cpu, Lock, TrendingUp, X, Zap,
} from 'lucide-react'

// ── Constants ─────────────────────────────────────────────────────────────────

const SYMBOLS   = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d']

const TARGET_METRICS = [
  { value: 'sharpe_ratio',      label: 'Sharpe Ratio' },
  { value: 'total_pnl_pct',     label: 'PnL %' },
  { value: 'win_rate_pct',      label: 'Win Rate' },
  { value: 'profit_factor',     label: 'Profit Factor' },
]

// ── Types ─────────────────────────────────────────────────────────────────────

type Status = 'live' | 'backtest' | 'planned'

interface Param { key: string; label: string; value: string | number; unit?: string }

interface BacktestParam {
  key: string; label: string; defaultValue: number
  min?: number; max?: number; step?: number; unit?: string
}

interface StrategyDef {
  id: string; name: string; nameEn: string; status: Status
  icon: React.ReactNode; accent: string; description: string; how: string
  params: Param[]; tags: string[]; module?: string
  backtestParams?: BacktestParam[]
  defaultParamGrid?: Record<string, string>
}

// ── Strategy definitions ──────────────────────────────────────────────────────

const STRATEGIES: StrategyDef[] = [
  {
    id: 'mtf-confluence',
    name: 'MTF Confluence Signal',
    nameEn: 'MTF Confluence',
    status: 'live',
    icon: <Zap size={20} />,
    accent: 'var(--accent-green)',
    description: 'Живой генератор сигналов: взвешенная оценка по всем таймфреймам (0–100). Сигнал генерируется при score ≥ 60, авто-исполнение при score ≥ 80.',
    how: 'Собирает TA-направление (RSI, MACD, EMA-кросс, Bollinger Bands) на каждом таймфрейме от 1m до 1d. К базовому score добавляются множители за подтверждение SMC (BOS/CHoCH/FVG), нахождение цены в зоне Order Block, бычий/медвежий CVD, и срабатывание spoof-детектора.\n\nКорреляционный движок отслеживает поведение пары относительно BTC и ETH (скользящее окно 50 свечей). Дивергенция — когда пара обычно следует за BTC, но последние 3 свечи расходятся — публикует отдельное событие и повышает приоритет сигнала.',
    params: [
      { key: 'min_score',  label: 'Порог сигнала',   value: 60,  unit: '/100' },
      { key: 'auto_score', label: 'Авто-исполнение', value: 80,  unit: '/100' },
      { key: 'ttl',        label: 'TTL сигнала',      value: 300, unit: 'сек' },
      { key: 'timeframes', label: 'Таймфреймы',       value: '1m · 5m · 15m · 1h · 4h · 1d' },
      { key: 'symbols',    label: 'Символы',          value: 'BTC · ETH · SOL · BNB · XRP' },
    ],
    tags: ['multi-TF', 'SMC', 'Volume', 'live'],
    module: 'analytics/mtf_confluence.py\nsignals/signal_engine.py',
  },
  {
    id: 'ma-crossover',
    name: 'MA Crossover',
    nameEn: 'Simple MA Strategy',
    status: 'backtest',
    icon: <TrendingUp size={20} />,
    accent: 'var(--accent-blue)',
    description: 'Классическое пересечение скользящих средних. Лонг при пересечении быстрой MA выше медленной, шорт — ниже. Один вход одновременно.',
    how: 'Стратегия хранит скользящее окно close-цен длиной slow_period + 1. На каждой свече вычисляются fast_ma и slow_ma как простые средние по последним N значениям.\n\nСигнал генерируется только при смене знака разности (bull_cross: prev_fast ≤ prev_slow и fast > slow; bear_cross — наоборот). После открытия позиции повторный вход блокируется флагом _in_position до вызова on_close() движком (по SL или TP).\n\nОптимизируется через GridSearchOptimizer по параметрам fast_period и slow_period с walk-forward валидацией (70% обучение, 30% тест).',
    params: [
      { key: 'fast_period', label: 'Быстрая MA',   value: 5,     unit: 'свечей' },
      { key: 'slow_period', label: 'Медленная MA',  value: 20,    unit: 'свечей' },
      { key: 'sl_pct',      label: 'Stop-Loss',     value: '2.0', unit: '%' },
      { key: 'tp_pct',      label: 'Take-Profit',   value: '4.0', unit: '%' },
    ],
    tags: ['trend-following', 'backtester'],
    module: 'strategies/simple_ma_strategy.py',
    backtestParams: [
      { key: 'fast_period', label: 'Быстрая MA',   defaultValue: 5,    min: 2,     max: 50,  step: 1,     unit: 'свечей' },
      { key: 'slow_period', label: 'Медленная MA', defaultValue: 20,   min: 5,     max: 200, step: 1,     unit: 'свечей' },
      { key: 'sl_pct',      label: 'Stop-Loss',    defaultValue: 0.02, min: 0.005, max: 0.1, step: 0.005, unit: 'доля (0.02=2%)' },
      { key: 'tp_pct',      label: 'Take-Profit',  defaultValue: 0.04, min: 0.01,  max: 0.2, step: 0.01,  unit: 'доля (0.04=4%)' },
    ],
    defaultParamGrid: {
      fast_period: '3,5,7,10',
      slow_period: '14,20,30,50',
      sl_pct:      '0.01,0.02,0.03',
      tp_pct:      '0.02,0.04,0.06',
    },
  },
  {
    id: 'smc-breakout',
    name: 'SMC Breakout',
    nameEn: 'SMC Breakout',
    status: 'planned',
    icon: <BarChart2 size={20} />,
    accent: 'var(--accent-purple)',
    description: 'Торговля на пробоях структуры рынка: BOS (Break of Structure) и CHoCH (Change of Character) из SMC-движка с подтверждением через Order Block.',
    how: 'Детектирует BOS (пробой последнего swing high/low) → ждёт ретест ближайшего Order Block в диапазоне 50% глубины → входит в направлении структуры с SL за OB.\n\nCHoCH (смена характера тренда) используется для контртрендовых разворотных входов с уменьшенным размером позиции.\n\nФильтр: входит только если CVD подтверждает направление и нет активных FVG выше/ниже зоны входа.',
    params: [
      { key: 'min_bos_strength', label: 'Мин. сила BOS', value: 0.5 },
      { key: 'ob_retrace_pct',   label: 'Ретест OB',     value: '50', unit: '%' },
      { key: 'sl_pct',           label: 'Stop-Loss',      value: '1.5', unit: '%' },
      { key: 'tp_pct',           label: 'Take-Profit',    value: '3.0', unit: '%' },
    ],
    tags: ['SMC', 'breakout', 'planned'],
    module: 'strategies/smc_strategies/',
  },
  {
    id: 'ta-momentum',
    name: 'TA Momentum',
    nameEn: 'TA Momentum',
    status: 'planned',
    icon: <Activity size={20} />,
    accent: 'var(--accent-orange)',
    description: 'Моментум-стратегия на основе RSI, MACD и Stochastic. Входит когда три индикатора одновременно указывают в одном направлении.',
    how: 'Условия лонга: RSI(14) поднимается из зоны ≤ 30, MACD-гистограмма меняет знак с – на +, Stochastic %K пересекает %D снизу вверх. Дополнительный фильтр: CVD > 0 (покупки доминируют).\n\nУсловия шорта: симметричны. RSI ≥ 70 → падает, MACD гистограмма < 0, Stoch %K пересекает %D сверху вниз, CVD < 0.\n\nSL ставится за ATR(14) × 1.5 от входа. TP = ATR × 3 (R:R = 1:2).',
    params: [
      { key: 'rsi_ob',  label: 'RSI перекупл.', value: 70 },
      { key: 'rsi_os',  label: 'RSI перепрод.', value: 30 },
      { key: 'sl_pct',  label: 'Stop-Loss',      value: '1.5 × ATR' },
      { key: 'tp_pct',  label: 'Take-Profit',    value: '3.0 × ATR' },
    ],
    tags: ['momentum', 'RSI', 'MACD', 'planned'],
    module: 'strategies/ta_strategies/',
  },
  {
    id: 'ml-predictor',
    name: 'ML Predictor',
    nameEn: 'ML Predictor',
    status: 'planned',
    icon: <Brain size={20} />,
    accent: 'var(--accent-teal)',
    description: 'Предсказание направления следующей свечи на основе обученной модели (LightGBM / LSTM). Требует накопленный ML Dataset. Phase 2.',
    how: 'Входные фичи: 40+ признаков — TA-индикаторы (RSI, MACD, BB, ATR), SMC-события (BOS/CHoCH/FVG за последние N свечей), CVD, bid/ask imbalance, funding rate, корреляция с BTC/ETH.\n\nML Dataset накапливается с первого запуска (market_snapshots в БД). Порог для обучения — ≥ 50 000 закрытых свечей.\n\nМодель предсказывает направление через 3 свечи с вероятностью. Сигнал генерируется только при уверенности ≥ 0.65. Переобучение — раз в неделю на свежих данных.',
    params: [
      { key: 'model',     label: 'Модель',            value: 'LightGBM / LSTM' },
      { key: 'horizon',   label: 'Горизонт прогноза', value: '3', unit: 'свечи' },
      { key: 'threshold', label: 'Мин. уверенность',  value: '0.65' },
      { key: 'min_data',  label: 'Мин. датасет',      value: '50 000', unit: 'свечей' },
    ],
    tags: ['ML', 'LightGBM', 'LSTM', 'Phase 2'],
    module: 'ml/',
  },
]

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<Status, { label: string; bg: string; color: string }> = {
  live:     { label: 'LIVE',     bg: 'rgba(34,211,165,0.12)',  color: 'var(--accent-green)' },
  backtest: { label: 'BACKTEST', bg: 'rgba(59,130,246,0.12)',  color: 'var(--accent-blue)'  },
  planned:  { label: 'PLANNED',  bg: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)'   },
}

function StatusBadge({ status }: { status: Status }) {
  const c = STATUS_CONFIG[status]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '4px 10px', borderRadius: 'var(--radius-pill)',
      background: c.bg, color: c.color,
      fontSize: 10, fontWeight: 700, fontFamily: 'var(--font-mono)',
      letterSpacing: '0.07em', flexShrink: 0,
    }}>
      {status === 'live' && (
        <span style={{
          width: 5, height: 5, borderRadius: '50%',
          background: 'var(--accent-green)',
          animation: 'livePulse 2s ease infinite', flexShrink: 0,
        }} />
      )}
      {c.label}
    </span>
  )
}

// ── Param row (display only) ──────────────────────────────────────────────────

function ParamRow({ param }: { param: Param }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '7px 0', borderBottom: '1px solid var(--border-subtle)',
    }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{param.label}</span>
      <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 500 }}>
        {param.value}
        {param.unit && <span style={{ color: 'var(--text-muted)', marginLeft: 3, fontSize: 11 }}>{param.unit}</span>}
      </span>
    </div>
  )
}

// ── Equity curve SVG ──────────────────────────────────────────────────────────

function EquityCurve({ data }: { data: number[] }) {
  if (data.length < 2) return null
  const W = 400, H = 60
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W
    const y = H - 4 - ((v - min) / range) * (H - 8)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const isUp = data[data.length - 1] >= data[0]
  const col = isUp ? 'var(--accent-green)' : '#f87171'
  const baseY = H - 4 - ((data[0] - min) / range) * (H - 8)
  const fill = `0,${baseY.toFixed(1)} ${pts.join(' ')} ${W},${baseY.toFixed(1)}`

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" style={{ display: 'block' }}>
      <defs>
        <linearGradient id="eq-grad-u" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={col} stopOpacity="0.18" />
          <stop offset="100%" stopColor={col} stopOpacity="0.01" />
        </linearGradient>
      </defs>
      <polyline points={fill} fill="url(#eq-grad-u)" stroke="none" />
      <polyline points={pts.join(' ')} fill="none" stroke={col} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Metrics grid ──────────────────────────────────────────────────────────────

function MetricBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '10px 12px' }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 15, fontFamily: 'var(--font-mono)', fontWeight: 700, color: color ?? 'var(--text-primary)' }}>{value}</div>
    </div>
  )
}

function MetricsGrid({ m }: { m: Record<string, number | null> }) {
  const pnl = m.total_pnl_pct ?? 0
  const wr  = m.win_rate_pct  ?? 0
  const sh  = m.sharpe_ratio  ?? 0
  const dd  = m.max_drawdown_pct ?? 0
  const pf  = m.profit_factor
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 16 }}>
      <MetricBox label="Сделок"        value={String(m.total_trades ?? 0)} />
      <MetricBox label="Win Rate"      value={`${wr.toFixed(1)}%`}         color={wr >= 50 ? 'var(--accent-green)' : '#f87171'} />
      <MetricBox label="PnL"           value={`${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`} color={pnl >= 0 ? 'var(--accent-green)' : '#f87171'} />
      <MetricBox label="Sharpe"        value={sh.toFixed(2)}               color={sh >= 1 ? 'var(--accent-green)' : sh >= 0 ? 'var(--accent-orange)' : '#f87171'} />
      <MetricBox label="Max Drawdown"  value={`${dd.toFixed(1)}%`}         color={dd <= 10 ? 'var(--accent-green)' : dd <= 20 ? 'var(--accent-orange)' : '#f87171'} />
      <MetricBox label="Profit Factor" value={pf != null ? pf.toFixed(2) : '—'} color={pf != null && pf >= 1.5 ? 'var(--accent-green)' : 'var(--text-secondary)'} />
      <MetricBox label="Сделок/мес"   value={(m.trades_per_month ?? 0).toFixed(1)} />
      <MetricBox label="Лучшая"        value={`$${(m.best_trade_pnl ?? 0).toFixed(2)}`} color="var(--accent-green)" />
      <MetricBox label="Худшая"        value={`$${(m.worst_trade_pnl ?? 0).toFixed(2)}`} color="#f87171" />
    </div>
  )
}

// ── Modal container helper ────────────────────────────────────────────────────

function ModalWrap({ accent, onClose, children }: { accent: string; onClose: () => void; children: React.ReactNode }) {
  return createPortal(
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 400, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        style={{ background: 'var(--bg-surface)', border: `1px solid ${accent}44`, borderRadius: 'var(--radius-xl)', padding: '28px 32px', maxWidth: 740, width: '95%', maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 12px 48px rgba(0,0,0,0.7)', display: 'flex', flexDirection: 'column', gap: 0 }}
        onClick={e => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body
  )
}

// ── Backtest Modal ────────────────────────────────────────────────────────────

interface BacktestModalProps {
  def: StrategyDef
  initialParams?: Record<string, number>
  onClose: () => void
  onRun: (strategyId: string, symbol: string, tf: string, params: Record<string, number>) => void
  onGetResults: (strategyId: string) => void
  onOpenOptimizer: () => void
}

function BacktestModal({ def, initialParams, onClose, onRun, onGetResults, onOpenOptimizer }: BacktestModalProps) {
  const backtestRunning = useStore(s => s.backtestRunning)
  const backtestResults = useStore(s => s.backtestResults)

  const [selSymbol, setSelSymbol] = useState(SYMBOLS[0])
  const [selTf, setSelTf]         = useState('1h')
  const [paramValues, setParamValues] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {}
    for (const p of def.backtestParams ?? []) {
      init[p.key] = initialParams?.[p.key] ?? p.defaultValue
    }
    return init
  })

  useEffect(() => { onGetResults(def.id) }, [def.id])

  const isRunning = backtestRunning[def.id] ?? false
  const currentKey = `${def.id}:${selSymbol}:${selTf}`
  const currentResult: BacktestResultUI | undefined = backtestResults[currentKey]

  const allResults = Object.values(backtestResults)
    .filter(r => r.strategy_id === def.id)
    .sort((a, b) => b.created_at - a.created_at)

  const canBacktest = !!def.backtestParams?.length

  function handleRun() {
    if (!canBacktest) return
    onRun(def.id, selSymbol, selTf, paramValues)
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', background: 'var(--bg-elevated)',
    border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)',
    color: 'var(--text-primary)', padding: '8px 10px', fontSize: 13,
    fontFamily: 'var(--font-mono)', outline: 'none',
    boxSizing: 'border-box',
  }

  return (
    <ModalWrap accent={def.accent} onClose={onClose}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 36, height: 36, borderRadius: 'var(--radius-md)', background: def.accent + '18', color: def.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{def.icon}</span>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>{def.name}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>Бэктест на исторических данных из БД</div>
          </div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', padding: 4 }}><X size={18} /></button>
      </div>

      {/* Controls row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 6, fontWeight: 700, letterSpacing: '0.07em' }}>ТОРГОВАЯ ПАРА</div>
          <select value={selSymbol} onChange={e => setSelSymbol(e.target.value)} style={inputStyle}>
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 6, fontWeight: 700, letterSpacing: '0.07em' }}>ТАЙМФРЕЙМ</div>
          <select value={selTf} onChange={e => setSelTf(e.target.value)} style={inputStyle}>
            {TIMEFRAMES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {/* Editable params */}
      {canBacktest && (
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 10, fontWeight: 700, letterSpacing: '0.07em' }}>ПАРАМЕТРЫ СТРАТЕГИИ</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
            {def.backtestParams!.map(p => (
              <div key={p.key} style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '11px 14px' }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 5 }}>
                  {p.label}{p.unit && <span style={{ marginLeft: 5, opacity: 0.6, fontSize: 10 }}>({p.unit})</span>}
                </div>
                <input
                  type="number" value={paramValues[p.key] ?? p.defaultValue}
                  min={p.min} max={p.max} step={p.step}
                  onChange={e => {
                    const v = parseFloat(e.target.value)
                    if (!isNaN(v)) setParamValues(prev => ({ ...prev, [p.key]: v }))
                  }}
                  style={{ background: 'none', border: 'none', outline: 'none', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, width: '100%', padding: 0 }}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
        <button
          onClick={handleRun} disabled={isRunning || !canBacktest}
          style={{
            flex: 1, padding: '11px', border: 'none', borderRadius: 'var(--radius-md)',
            fontSize: 13, fontWeight: 700, cursor: isRunning || !canBacktest ? 'not-allowed' : 'pointer',
            background: isRunning || !canBacktest ? 'var(--bg-elevated)' : def.accent,
            color: isRunning || !canBacktest ? 'var(--text-muted)' : '#000',
            transition: 'opacity 0.15s',
          }}
        >
          {isRunning ? '⟳ Выполняется...' : !canBacktest ? 'Бэктест недоступен для этой стратегии' : '▶ Запустить бэктест'}
        </button>
        {def.defaultParamGrid && (
          <button
            onClick={onOpenOptimizer}
            style={{
              padding: '11px 18px', border: `1px solid ${def.accent}44`, borderRadius: 'var(--radius-md)',
              fontSize: 13, fontWeight: 600, cursor: 'pointer',
              background: 'none', color: def.accent, whiteSpace: 'nowrap',
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = def.accent + '12')}
            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
          >
            ⚙ Оптимизация
          </button>
        )}
      </div>

      {/* Results */}
      {currentResult && (
        <>
          <div style={{ height: 1, background: `linear-gradient(90deg, ${def.accent}55, transparent)`, marginBottom: 18 }} />
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 12, fontWeight: 700, letterSpacing: '0.07em' }}>
            РЕЗУЛЬТАТЫ: {currentResult.symbol} {currentResult.timeframe}
            {currentResult.period_start && (
              <span style={{ fontWeight: 400, marginLeft: 8 }}>
                {new Date(currentResult.period_start).toLocaleDateString('ru')} — {new Date(currentResult.period_end!).toLocaleDateString('ru')}
              </span>
            )}
            {currentResult.is_optimization && <span style={{ marginLeft: 8, color: def.accent }}>· OPTIMIZED</span>}
          </div>
          <MetricsGrid m={currentResult.metrics} />
          {currentResult.equity_curve.length >= 2 && (
            <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '12px 16px', marginBottom: 20 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>КРИВАЯ КАПИТАЛА</div>
              <EquityCurve data={currentResult.equity_curve} />
            </div>
          )}
        </>
      )}

      {/* Per-pair history */}
      {allResults.length > 0 && (
        <>
          <div style={{ height: 1, background: 'var(--border-subtle)', marginBottom: 14 }} />
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 10, fontWeight: 700, letterSpacing: '0.07em' }}>ИСТОРИЯ ПО ПАРАМ</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {allResults.map(r => {
              const key = `${r.strategy_id}:${r.symbol}:${r.timeframe}`
              const active = currentKey === key
              const pnl = r.metrics.total_pnl_pct ?? 0
              const wr  = r.metrics.win_rate_pct  ?? 0
              const sh  = r.metrics.sharpe_ratio  ?? 0
              return (
                <div
                  key={r.id}
                  onClick={() => { setSelSymbol(r.symbol); setSelTf(r.timeframe) }}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '8px 12px', cursor: 'pointer', borderRadius: 'var(--radius-sm)',
                    background: active ? `${def.accent}10` : 'var(--bg-elevated)',
                    border: `1px solid ${active ? def.accent + '44' : 'transparent'}`,
                    transition: 'background 0.15s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{r.symbol}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{r.timeframe}</span>
                    {r.is_optimization && <span style={{ fontSize: 10, color: def.accent, background: `${def.accent}15`, padding: '2px 6px', borderRadius: 4 }}>OPT</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 14 }}>
                    <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: pnl >= 0 ? 'var(--accent-green)' : '#f87171' }}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(1)}%</span>
                    <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>WR {wr.toFixed(0)}%</span>
                    <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>S {sh.toFixed(2)}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{r.trades_count} сд.</span>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </ModalWrap>
  )
}

// ── Optimizer Modal ───────────────────────────────────────────────────────────

interface OptimizerModalProps {
  def: StrategyDef
  onClose: () => void
  onRun: (strategyId: string, symbol: string, tf: string, paramGrid: Record<string, number[]>, targetMetric: string, walkForward: boolean) => void
  onApplyAndBacktest: (params: Record<string, number>) => void
  onGetResults: (strategyId: string) => void
}

function OptimizerModal({ def, onClose, onRun, onApplyAndBacktest, onGetResults }: OptimizerModalProps) {
  const optimizerRunning = useStore(s => s.optimizerRunning)
  const optimizerResults = useStore(s => s.optimizerResults)

  const [selSymbol, setSelSymbol]       = useState(SYMBOLS[0])
  const [selTf, setSelTf]               = useState('1h')
  const [targetMetric, setTargetMetric] = useState(TARGET_METRICS[0].value)
  const [walkForward, setWalkForward]   = useState(true)
  const [gridValues, setGridValues]     = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const p of def.backtestParams ?? []) {
      init[p.key] = def.defaultParamGrid?.[p.key] ?? String(p.defaultValue)
    }
    return init
  })

  useEffect(() => { onGetResults(def.id) }, [def.id])

  const isRunning = optimizerRunning[def.id] ?? false
  const optKey    = `${def.id}:${selSymbol}`
  const optResult: OptimizerResultUI | undefined = optimizerResults[optKey]

  function parseGrid(): Record<string, number[]> {
    const grid: Record<string, number[]> = {}
    for (const [k, v] of Object.entries(gridValues)) {
      const nums = v.split(',').map(x => parseFloat(x.trim())).filter(x => !isNaN(x))
      if (nums.length > 0) grid[k] = nums
    }
    return grid
  }

  function totalCombos(): number {
    const grid = parseGrid()
    return Object.values(grid).reduce((acc, arr) => acc * arr.length, 1)
  }

  function handleRun() {
    const grid = parseGrid()
    if (Object.keys(grid).length === 0) return
    onRun(def.id, selSymbol, selTf, grid, targetMetric, walkForward)
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', background: 'var(--bg-elevated)',
    border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)',
    color: 'var(--text-primary)', padding: '8px 10px', fontSize: 13,
    fontFamily: 'var(--font-mono)', outline: 'none', boxSizing: 'border-box',
  }

  const targetLabel = TARGET_METRICS.find(m => m.value === targetMetric)?.label ?? targetMetric

  return (
    <ModalWrap accent={def.accent} onClose={onClose}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 36, height: 36, borderRadius: 'var(--radius-md)', background: def.accent + '18', color: def.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{def.icon}</span>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>{def.name} — Оптимизация</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>Grid Search + Walk-Forward валидация</div>
          </div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', padding: 4 }}><X size={18} /></button>
      </div>

      {/* Controls row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 6, fontWeight: 700, letterSpacing: '0.07em' }}>ПАРА</div>
          <select value={selSymbol} onChange={e => setSelSymbol(e.target.value)} style={inputStyle}>
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 6, fontWeight: 700, letterSpacing: '0.07em' }}>ТАЙМФРЕЙМ</div>
          <select value={selTf} onChange={e => setSelTf(e.target.value)} style={inputStyle}>
            {TIMEFRAMES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 6, fontWeight: 700, letterSpacing: '0.07em' }}>МЕТРИКА</div>
          <select value={targetMetric} onChange={e => setTargetMetric(e.target.value)} style={inputStyle}>
            {TARGET_METRICS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>
      </div>

      {/* Param grid editor */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 10, fontWeight: 700, letterSpacing: '0.07em' }}>
          СЕТКА ПАРАМЕТРОВ <span style={{ fontWeight: 400, color: 'var(--text-muted)', opacity: 0.6 }}>(через запятую)</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
          {def.backtestParams!.map(p => (
            <div key={p.key} style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '11px 14px' }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>
                {p.label}{p.unit && <span style={{ marginLeft: 5, opacity: 0.6, fontSize: 10 }}>({p.unit})</span>}
              </div>
              <input
                type="text"
                value={gridValues[p.key] ?? ''}
                onChange={e => setGridValues(prev => ({ ...prev, [p.key]: e.target.value }))}
                placeholder="3,5,7,10"
                style={{ background: 'none', border: 'none', outline: 'none', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 13, width: '100%', padding: 0 }}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Walk-forward + combo count */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--text-secondary)' }}>
          <input
            type="checkbox" checked={walkForward} onChange={e => setWalkForward(e.target.checked)}
            style={{ accentColor: def.accent, width: 14, height: 14 }}
          />
          Walk-Forward валидация (70%/30%)
        </label>
        <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          <span style={{ color: def.accent, fontWeight: 700 }}>{totalCombos()}</span> комбинаций
        </div>
      </div>

      {/* Run button */}
      <button
        onClick={handleRun} disabled={isRunning}
        style={{
          width: '100%', padding: '11px', border: 'none', borderRadius: 'var(--radius-md)',
          fontSize: 13, fontWeight: 700, cursor: isRunning ? 'not-allowed' : 'pointer',
          background: isRunning ? 'var(--bg-elevated)' : def.accent,
          color: isRunning ? 'var(--text-muted)' : '#000',
          marginBottom: 22,
        }}
      >
        {isRunning ? `⟳ Оптимизация ${totalCombos()} комбинаций...` : `▶ Запустить оптимизацию · Метрика: ${targetLabel}`}
      </button>

      {/* Optimizer results */}
      {optResult && optResult.symbol === selSymbol && (
        <>
          <div style={{ height: 1, background: `linear-gradient(90deg, ${def.accent}55, transparent)`, marginBottom: 18 }} />

          {/* Best params */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 4, fontWeight: 700, letterSpacing: '0.07em' }}>ЛУЧШИЕ ПАРАМЕТРЫ</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {Object.entries(optResult.best_params).map(([k, v]) => (
                  <span key={k} style={{ background: `${def.accent}15`, color: def.accent, padding: '4px 10px', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    {k}: {typeof v === 'number' ? v : String(v)}
                  </span>
                ))}
                <span style={{ color: 'var(--text-muted)', fontSize: 12, alignSelf: 'center' }}>
                  {targetLabel}: <b style={{ color: def.accent }}>{(optResult.best_metric ?? 0).toFixed(3)}</b>
                </span>
              </div>
            </div>
            <button
              onClick={() => onApplyAndBacktest(optResult.best_params as Record<string, number>)}
              style={{
                padding: '8px 16px', border: `1px solid ${def.accent}55`,
                borderRadius: 'var(--radius-sm)', background: `${def.accent}10`,
                color: def.accent, fontSize: 12, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
              }}
            >
              ↗ Применить и бэктест
            </button>
          </div>

          {/* Best equity curve */}
          {optResult.best_equity_curve.length >= 2 && (
            <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '10px 14px', marginBottom: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>КРИВАЯ ЛУЧШЕГО РЕЗУЛЬТАТА</div>
              <EquityCurve data={optResult.best_equity_curve} />
            </div>
          )}

          {/* Results table */}
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8, fontWeight: 700, letterSpacing: '0.07em' }}>
            ТОП-{optResult.all_results.length} РЕЗУЛЬТАТОВ
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11 }}>#</th>
                  {def.backtestParams!.map(p => (
                    <th key={p.key} style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11 }}>{p.key}</th>
                  ))}
                  <th style={{ textAlign: 'right', padding: '6px 8px', color: def.accent, fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11 }}>{targetLabel}</th>
                  <th style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11 }}>WR%</th>
                  <th style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11 }}>PnL%</th>
                  <th style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11 }}>DD%</th>
                  <th style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11 }}>Сд.</th>
                </tr>
              </thead>
              <tbody>
                {optResult.all_results.map((row, i) => {
                  const pnl = row.metrics.total_pnl_pct ?? 0
                  const wr  = row.metrics.win_rate_pct  ?? 0
                  const dd  = row.metrics.max_drawdown_pct ?? 0
                  const mv  = row.metrics[optResult.target_metric] ?? 0
                  return (
                    <tr
                      key={i}
                      onClick={() => onApplyAndBacktest(row.params as Record<string, number>)}
                      style={{
                        borderBottom: '1px solid var(--border-subtle)',
                        cursor: 'pointer',
                        background: i === 0 ? `${def.accent}08` : 'transparent',
                        transition: 'background 0.1s',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = `${def.accent}10`)}
                      onMouseLeave={e => (e.currentTarget.style.background = i === 0 ? `${def.accent}08` : 'transparent')}
                    >
                      <td style={{ padding: '6px 8px', color: i === 0 ? def.accent : 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontWeight: i === 0 ? 700 : 400 }}>{i + 1}</td>
                      {def.backtestParams!.map(p => (
                        <td key={p.key} style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                          {typeof row.params[p.key] === 'number' ? (row.params[p.key] as number).toString() : String(row.params[p.key] ?? '—')}
                        </td>
                      ))}
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: def.accent, fontWeight: 700 }}>{(mv as number).toFixed(3)}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: wr >= 50 ? 'var(--accent-green)' : '#f87171' }}>{wr.toFixed(0)}%</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: pnl >= 0 ? 'var(--accent-green)' : '#f87171' }}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(1)}%</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: dd <= 10 ? 'var(--accent-green)' : '#f87171' }}>{dd.toFixed(1)}%</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{row.trades_count}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ModalWrap>
  )
}

// ── How-it-works modal ────────────────────────────────────────────────────────

function HowItWorksModal({ def, onClose }: { def: StrategyDef; onClose: () => void }) {
  return createPortal(
    <div style={{ position: 'fixed', inset: 0, zIndex: 400, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }} onClick={onClose}>
      <div style={{ background: 'var(--bg-surface)', border: `1px solid ${def.accent}44`, borderRadius: 'var(--radius-xl)', padding: '28px 32px', maxWidth: 560, width: '90%', boxShadow: '0 12px 48px rgba(0,0,0,0.6)', display: 'flex', flexDirection: 'column', gap: 16 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ width: 36, height: 36, borderRadius: 'var(--radius-md)', background: def.accent + '18', color: def.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{def.icon}</span>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>{def.name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 1 }}>Как работает</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4, display: 'flex' }}><X size={17} /></button>
        </div>
        <div style={{ height: 1, background: `linear-gradient(90deg, ${def.accent}66, transparent)` }} />
        <div style={{ borderLeft: `3px solid ${def.accent}`, paddingLeft: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {def.how.split('\n\n').map((para, i) => (
            <p key={i} style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, margin: 0 }}>{para}</p>
          ))}
        </div>
        {def.module && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
            {def.module.split('\n').map(m => (
              <span key={m} style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: def.accent, background: def.accent + '10', borderRadius: 'var(--radius-sm)', padding: '3px 8px' }}>{m}</span>
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body
  )
}

// ── Strategy card ─────────────────────────────────────────────────────────────

interface StrategyCardProps {
  def: StrategyDef
  signalCount?: number
  onBacktest?: () => void
  onOptimize?: () => void
}

function StrategyCard({ def, signalCount, onBacktest, onOptimize }: StrategyCardProps) {
  const [showHow, setShowHow] = useState(false)
  const backtestRunning  = useStore(s => s.backtestRunning)
  const optimizerRunning = useStore(s => s.optimizerRunning)
  const isPlanned   = def.status === 'planned'
  const isBtRunning = backtestRunning[def.id] ?? false
  const isOptRunning = optimizerRunning[def.id] ?? false

  const btnBase: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 5,
    border: 'none', borderRadius: 'var(--radius-sm)',
    padding: '5px 11px', cursor: 'pointer',
    fontSize: 11, fontFamily: 'var(--font-body)', whiteSpace: 'nowrap', flexShrink: 0,
    transition: 'background 0.15s, opacity 0.15s',
  }

  return (
    <>
      <div
        style={{
          background: 'var(--bg-surface)',
          border: `1px solid ${isPlanned ? 'var(--border-subtle)' : def.accent + '33'}`,
          borderRadius: 'var(--radius-xl)', overflow: 'hidden',
          opacity: isPlanned ? 0.72 : 1,
          display: 'flex', flexDirection: 'column',
          transition: 'border-color 0.2s, box-shadow 0.2s, transform 0.15s',
        }}
        onMouseEnter={e => {
          const el = e.currentTarget as HTMLDivElement
          if (!isPlanned) el.style.boxShadow = `0 8px 32px rgba(0,0,0,0.3), 0 0 0 1px ${def.accent}55`
          el.style.transform = 'translateY(-2px)'
        }}
        onMouseLeave={e => {
          const el = e.currentTarget as HTMLDivElement
          el.style.boxShadow = 'none'; el.style.transform = 'translateY(0)'
        }}
      >
        <div style={{ height: 3, background: isPlanned ? 'var(--border-subtle)' : `linear-gradient(90deg, ${def.accent}, ${def.accent}44)` }} />

        <div style={{ padding: '22px 24px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
              <span style={{ width: 44, height: 44, borderRadius: 'var(--radius-md)', background: def.accent + '15', color: def.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: `1px solid ${def.accent}22` }}>
                {isPlanned ? <Lock size={18} /> : def.icon}
              </span>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--text-primary)', lineHeight: 1.2 }}>{def.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>{def.nameEn}</div>
              </div>
            </div>
            <StatusBadge status={def.status} />
          </div>

          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>{def.description}</p>

          {def.status === 'live' && signalCount !== undefined && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'rgba(34,211,165,0.08)', border: '1px solid rgba(34,211,165,0.25)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', fontSize: 12, color: 'var(--accent-green)', fontFamily: 'var(--font-mono)' }}>
                <Cpu size={12} /> Работает
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                <Activity size={12} /> Сигналов в очереди: {signalCount}
              </div>
            </div>
          )}

          {def.status === 'backtest' && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', fontSize: 12, color: 'var(--accent-blue)', fontFamily: 'var(--font-mono)', width: 'fit-content' }}>
              <Clock size={12} /> Только бэктест · нет live-исполнения
            </div>
          )}
        </div>

        <div style={{ padding: '0 24px 18px', flex: 1 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 8, fontFamily: 'var(--font-mono)' }}>ПАРАМЕТРЫ</div>
          {def.params.map(p => <ParamRow key={p.key} param={p} />)}
        </div>

        <div style={{ padding: '14px 24px', borderTop: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, background: 'rgba(255,255,255,0.01)', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {def.tags.map(t => (
              <span key={t} style={{ fontSize: 10, padding: '3px 8px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-pill)', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{t}</span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            {!isPlanned && onBacktest && (
              <button
                onClick={onBacktest} disabled={isBtRunning}
                style={{ ...btnBase, background: isBtRunning ? 'var(--bg-elevated)' : `${def.accent}15`, color: isBtRunning ? 'var(--text-muted)' : def.accent, opacity: isBtRunning ? 0.7 : 1 }}
                onMouseEnter={e => { if (!isBtRunning) e.currentTarget.style.background = `${def.accent}28` }}
                onMouseLeave={e => { if (!isBtRunning) e.currentTarget.style.background = `${def.accent}15` }}
              >
                {isBtRunning ? '⟳' : '▶'} Бэктест
              </button>
            )}
            {!isPlanned && onOptimize && def.defaultParamGrid && (
              <button
                onClick={onOptimize} disabled={isOptRunning}
                style={{ ...btnBase, background: isOptRunning ? 'var(--bg-elevated)' : 'var(--bg-elevated)', color: isOptRunning ? 'var(--text-muted)' : 'var(--text-secondary)', opacity: isOptRunning ? 0.7 : 1 }}
                onMouseEnter={e => { if (!isOptRunning) e.currentTarget.style.background = 'var(--border-subtle)' }}
                onMouseLeave={e => { if (!isOptRunning) e.currentTarget.style.background = 'var(--bg-elevated)' }}
              >
                {isOptRunning ? '⟳' : '⚙'} Оптимизация
              </button>
            )}
            <button
              onClick={() => setShowHow(true)}
              style={{ ...btnBase, background: 'none', border: `1px solid ${def.accent}44`, color: def.accent }}
              onMouseEnter={e => (e.currentTarget.style.background = def.accent + '12')}
              onMouseLeave={e => (e.currentTarget.style.background = 'none')}
            >
              <BookOpen size={12} /> Как работает
            </button>
          </div>
        </div>
      </div>

      {showHow && <HowItWorksModal def={def} onClose={() => setShowHow(false)} />}
    </>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

interface StrategiesViewProps {
  runBacktest: (strategyId: string, symbol: string, tf: string, params: Record<string, number>) => void
  runOptimizer: (strategyId: string, symbol: string, tf: string, paramGrid: Record<string, number[]>, targetMetric: string, walkForward: boolean) => void
  getBacktestResults: (strategyId: string) => void
}

export default function StrategiesView({ runBacktest, runOptimizer, getBacktestResults }: StrategiesViewProps) {
  const signals = useStore(s => s.signals)
  const mode    = useStore(s => s.mode)

  // { def, initialParams? } | null
  const [btModal, setBtModal]   = useState<{ def: StrategyDef; initialParams?: Record<string, number> } | null>(null)
  const [optModal, setOptModal] = useState<StrategyDef | null>(null)

  const implemented = STRATEGIES.filter(s => s.status !== 'planned')
  const planned     = STRATEGIES.filter(s => s.status === 'planned')

  const modeLabel: Record<string, string> = {
    alert_only: 'Только алерты',
    semi_auto:  'Полуавтомат',
    auto:       'Авто',
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 20, overflow: 'hidden' }}>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20, color: 'var(--text-primary)', margin: 0 }}>Стратегии</h2>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '4px 0 0' }}>
            {implemented.length} реализовано · {planned.length} запланировано
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '7px 14px', fontSize: 12 }}>
          <span style={{ color: 'var(--text-muted)' }}>Режим исполнения:</span>
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 600 }}>{modeLabel[mode] ?? mode}</span>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', paddingRight: 2 }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>

          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 14, fontFamily: 'var(--font-mono)' }}>РЕАЛИЗОВАНЫ</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, marginBottom: 36 }}>
            {implemented.map(def => (
              <StrategyCard
                key={def.id}
                def={def}
                signalCount={def.id === 'mtf-confluence' ? signals.length : undefined}
                onBacktest={() => setBtModal({ def })}
                onOptimize={() => setOptModal(def)}
              />
            ))}
          </div>

          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 14, fontFamily: 'var(--font-mono)' }}>ЗАПЛАНИРОВАНЫ</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
            {planned.map(def => <StrategyCard key={def.id} def={def} />)}
          </div>

        </div>
      </div>

      {btModal && (
        <BacktestModal
          def={btModal.def}
          initialParams={btModal.initialParams}
          onClose={() => setBtModal(null)}
          onRun={runBacktest}
          onGetResults={getBacktestResults}
          onOpenOptimizer={() => { setBtModal(null); setOptModal(btModal.def) }}
        />
      )}

      {optModal && (
        <OptimizerModal
          def={optModal}
          onClose={() => setOptModal(null)}
          onRun={runOptimizer}
          onGetResults={getBacktestResults}
          onApplyAndBacktest={(params) => {
            const def = optModal
            setOptModal(null)
            setBtModal({ def, initialParams: params })
          }}
        />
      )}
    </div>
  )
}
