import React, { useState } from 'react'
import { createPortal } from 'react-dom'
import { useStore } from '../store/useStore'
import {
  Activity, BarChart2, Brain, Clock, Cpu,
  TrendingUp, Zap, Lock, X, BookOpen,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

type Status = 'live' | 'backtest' | 'planned'

interface Param {
  key: string
  label: string
  value: string | number
  unit?: string
}

interface StrategyDef {
  id: string
  name: string
  nameEn: string
  status: Status
  icon: React.ReactNode
  accent: string
  description: string
  how: string
  params: Param[]
  tags: string[]
  module?: string
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
      padding: '4px 10px',
      borderRadius: 'var(--radius-pill)',
      background: c.bg,
      color: c.color,
      fontSize: 10,
      fontWeight: 700,
      fontFamily: 'var(--font-mono)',
      letterSpacing: '0.07em',
      flexShrink: 0,
    }}>
      {status === 'live' && (
        <span style={{
          width: 5, height: 5, borderRadius: '50%',
          background: 'var(--accent-green)',
          animation: 'livePulse 2s ease infinite',
          flexShrink: 0,
        }} />
      )}
      {c.label}
    </span>
  )
}

// ── Param row ─────────────────────────────────────────────────────────────────

function ParamRow({ param }: { param: Param }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '7px 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{param.label}</span>
      <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 500 }}>
        {param.value}
        {param.unit && <span style={{ color: 'var(--text-muted)', marginLeft: 3, fontSize: 11 }}>{param.unit}</span>}
      </span>
    </div>
  )
}

// ── How-it-works modal ────────────────────────────────────────────────────────

function HowItWorksModal({ def, onClose }: { def: StrategyDef; onClose: () => void }) {
  return createPortal(
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 400,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backdropFilter: 'blur(4px)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-surface)',
          border: `1px solid ${def.accent}44`,
          borderRadius: 'var(--radius-xl)',
          padding: '28px 32px',
          maxWidth: 560,
          width: '90%',
          boxShadow: '0 12px 48px rgba(0,0,0,0.6)',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Modal header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              width: 36, height: 36,
              borderRadius: 'var(--radius-md)',
              background: def.accent + '18',
              color: def.accent,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              {def.icon}
            </span>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>
                {def.name}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 1 }}>
                Как работает
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4, display: 'flex' }}
          >
            <X size={17} />
          </button>
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: `linear-gradient(90deg, ${def.accent}66, transparent)` }} />

        {/* Content */}
        <div style={{
          borderLeft: `3px solid ${def.accent}`,
          paddingLeft: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}>
          {def.how.split('\n\n').map((para, i) => (
            <p key={i} style={{
              fontSize: 13,
              color: 'var(--text-secondary)',
              lineHeight: 1.7,
              margin: 0,
            }}>
              {para}
            </p>
          ))}
        </div>

        {/* Module path */}
        {def.module && (
          <div style={{
            display: 'flex', gap: 6, flexWrap: 'wrap',
            paddingTop: 8,
            borderTop: '1px solid var(--border-subtle)',
          }}>
            {def.module.split('\n').map(m => (
              <span key={m} style={{
                fontSize: 10,
                fontFamily: 'var(--font-mono)',
                color: def.accent,
                background: def.accent + '10',
                borderRadius: 'var(--radius-sm)',
                padding: '3px 8px',
              }}>{m}</span>
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body
  )
}

// ── Strategy card ─────────────────────────────────────────────────────────────

function StrategyCard({ def, signalCount }: { def: StrategyDef; signalCount?: number }) {
  const [showHow, setShowHow] = useState(false)
  const isPlanned = def.status === 'planned'

  return (
    <>
      <div style={{
        background: 'var(--bg-surface)',
        border: `1px solid ${isPlanned ? 'var(--border-subtle)' : def.accent + '33'}`,
        borderRadius: 'var(--radius-xl)',
        overflow: 'hidden',
        opacity: isPlanned ? 0.72 : 1,
        display: 'flex',
        flexDirection: 'column',
        transition: 'border-color 0.2s, box-shadow 0.2s, transform 0.15s',
      }}
        onMouseEnter={e => {
          const el = e.currentTarget as HTMLDivElement
          if (!isPlanned) el.style.boxShadow = `0 8px 32px rgba(0,0,0,0.3), 0 0 0 1px ${def.accent}55`
          el.style.transform = 'translateY(-2px)'
        }}
        onMouseLeave={e => {
          const el = e.currentTarget as HTMLDivElement
          el.style.boxShadow = 'none'
          el.style.transform = 'translateY(0)'
        }}
      >
        {/* Top accent line */}
        <div style={{ height: 3, background: isPlanned ? 'var(--border-subtle)' : `linear-gradient(90deg, ${def.accent}, ${def.accent}44)` }} />

        {/* Header */}
        <div style={{ padding: '22px 24px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Icon + name + badge */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
              <span style={{
                width: 44, height: 44,
                borderRadius: 'var(--radius-md)',
                background: def.accent + '15',
                color: def.accent,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
                border: `1px solid ${def.accent}22`,
              }}>
                {isPlanned ? <Lock size={18} /> : def.icon}
              </span>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--text-primary)', lineHeight: 1.2 }}>
                  {def.name}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>
                  {def.nameEn}
                </div>
              </div>
            </div>
            <StatusBadge status={def.status} />
          </div>

          {/* Description */}
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
            {def.description}
          </p>

          {/* Live pill */}
          {def.status === 'live' && signalCount !== undefined && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 5,
                background: 'rgba(34,211,165,0.08)',
                border: '1px solid rgba(34,211,165,0.25)',
                borderRadius: 'var(--radius-sm)',
                padding: '4px 10px',
                fontSize: 12,
                color: 'var(--accent-green)',
                fontFamily: 'var(--font-mono)',
              }}>
                <Cpu size={12} /> Работает
              </div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 5,
                background: 'var(--bg-elevated)',
                borderRadius: 'var(--radius-sm)',
                padding: '4px 10px',
                fontSize: 12,
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-mono)',
              }}>
                <Activity size={12} /> Сигналов в очереди: {signalCount}
              </div>
            </div>
          )}

          {def.status === 'backtest' && (
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              background: 'rgba(59,130,246,0.08)',
              border: '1px solid rgba(59,130,246,0.2)',
              borderRadius: 'var(--radius-sm)',
              padding: '4px 10px',
              fontSize: 12,
              color: 'var(--accent-blue)',
              fontFamily: 'var(--font-mono)',
              width: 'fit-content',
            }}>
              <Clock size={12} /> Только бэктест · нет live-исполнения
            </div>
          )}
        </div>

        {/* Params */}
        <div style={{ padding: '0 24px 18px', flex: 1 }}>
          <div style={{
            fontSize: 10, fontWeight: 700, color: 'var(--text-muted)',
            letterSpacing: '0.1em', marginBottom: 8,
            fontFamily: 'var(--font-mono)',
          }}>
            ПАРАМЕТРЫ
          </div>
          {def.params.map(p => <ParamRow key={p.key} param={p} />)}
        </div>

        {/* Footer */}
        <div style={{
          padding: '14px 24px',
          borderTop: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          background: 'rgba(255,255,255,0.01)',
        }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {def.tags.map(t => (
              <span key={t} style={{
                fontSize: 10, padding: '3px 8px',
                background: 'var(--bg-elevated)',
                borderRadius: 'var(--radius-pill)',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-mono)',
              }}>{t}</span>
            ))}
          </div>

          <button
            onClick={() => setShowHow(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              background: 'none',
              border: `1px solid ${def.accent}44`,
              borderRadius: 'var(--radius-sm)',
              padding: '5px 10px',
              cursor: 'pointer',
              color: def.accent,
              fontSize: 11,
              fontFamily: 'var(--font-body)',
              whiteSpace: 'nowrap',
              flexShrink: 0,
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = def.accent + '12')}
            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
          >
            <BookOpen size={12} /> Как работает
          </button>
        </div>
      </div>

      {showHow && <HowItWorksModal def={def} onClose={() => setShowHow(false)} />}
    </>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function StrategiesView() {
  const signals = useStore(s => s.signals)
  const mode    = useStore(s => s.mode)

  const implemented = STRATEGIES.filter(s => s.status !== 'planned')
  const planned     = STRATEGIES.filter(s => s.status === 'planned')

  const modeLabel: Record<string, string> = {
    alert_only: 'Только алерты',
    semi_auto:  'Полуавтомат',
    auto:       'Авто',
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 20, overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20, color: 'var(--text-primary)', margin: 0 }}>
            Стратегии
          </h2>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '4px 0 0' }}>
            {implemented.length} реализовано · {planned.length} запланировано
          </p>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          padding: '7px 14px',
          fontSize: 12,
        }}>
          <span style={{ color: 'var(--text-muted)' }}>Режим исполнения:</span>
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 600 }}>
            {modeLabel[mode] ?? mode}
          </span>
        </div>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto', paddingRight: 2 }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>

          {/* Implemented */}
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 14, fontFamily: 'var(--font-mono)' }}>
            РЕАЛИЗОВАНЫ
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 20,
            marginBottom: 36,
          }}>
            {implemented.map(def => (
              <StrategyCard
                key={def.id}
                def={def}
                signalCount={def.id === 'mtf-confluence' ? signals.length : undefined}
              />
            ))}
          </div>

          {/* Planned */}
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 14, fontFamily: 'var(--font-mono)' }}>
            ЗАПЛАНИРОВАНЫ
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 20,
          }}>
            {planned.map(def => (
              <StrategyCard key={def.id} def={def} />
            ))}
          </div>

        </div>
      </div>
    </div>
  )
}
