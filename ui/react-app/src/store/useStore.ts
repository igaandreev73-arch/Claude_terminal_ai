import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { VpsStatus } from '../hooks/useVpsTelemetry'
import type { BusEvent, Candle, ExecutionMode, Position, Signal, TradeRecord } from '../types'

// ── Pulse types ────────────────────────────────────────────────────────────────

export interface ConnectionStatus {
  name: string
  label: string
  stage: 'normal' | 'degraded' | 'lost' | 'dead' | 'stopped'
  last_ok_at: number | null    // unix timestamp
  is_critical: boolean
  market_type: string
  silence_sec?: number
}

export interface ModuleStatus {
  name: string
  label: string
  status: 'ok' | 'slow' | 'degraded' | 'frozen' | 'stopped'
  last_action_at: number | null
  events_per_min: number
  latency_ms: number | null
}

export interface RateLimitStatus {
  used: number
  limit: number
  pct: number        // 0–100
  priority: string   // NORMAL / HIGH / CRITICAL
}

export interface DataTrustRow {
  symbol: string
  timeframe: string
  market_type: string
  last_candle_at: number | null
  gaps_24h: number
  verification_status: string
  trust_score: number
  size_mb: number
}

export interface BasisRow {
  symbol: string
  spot: number
  futures: number
  basis: number
  basis_pct: number
  updated_at: number
}

export interface PulseState {
  connections: ConnectionStatus[]
  modules: ModuleStatus[]
  rate_limit: RateLimitStatus
  data_rows: DataTrustRow[]
  basis: BasisRow[]
  db_size_mb: number
  db_growth_mb_7d: number
  db_forecast_days: number | null
  last_aggregation_at: number | null
  updated_at: number
}

export interface CriticalEvent {
  id: string
  level: 'warning' | 'error' | 'critical'
  module: string
  message: string
  started_at: number
  seen: boolean
}

export interface TradeDetail {
  entry_time: number
  exit_time: number
  direction: 'long' | 'short'
  entry_price: number
  exit_price: number
  size_usd: number
  pnl: number
  pnl_pct: number
  closed_by: 'sl' | 'tp' | 'signal' | 'end'
}

export interface BacktestResultUI {
  id: string
  strategy_id: string
  symbol: string
  timeframe: string
  params: Record<string, unknown>
  metrics: Record<string, number | null>
  equity_curve: number[]
  trades_count: number
  trades_detail?: TradeDetail[]
  period_start?: number
  period_end?: number
  is_optimization?: boolean
  created_at: number
}

export interface OptimizerResultUI {
  run_id: string
  strategy_id: string
  symbol: string
  timeframe: string
  target_metric: string
  best_params: Record<string, unknown>
  best_metric: number
  best_equity_curve: number[]
  all_results: Array<{ params: Record<string, unknown>; metrics: Record<string, number | null>; trades_count: number }>
  fingerprint: Record<string, unknown>
  created_at: number
}

export interface TaskInfo {
  task_id: string
  type: string       // 'backfill' | 'validation'
  symbol: string
  period?: string
  status: string     // 'running' | 'paused' | 'completed' | 'error' | 'cancelled'
  percent: number
  fetched: number
  total_pages: number
  total_saved?: number
  speed_cps?: number
  eta_seconds?: number
  start_time?: number
  result?: string
  error?: string
  created_at?: number
}

export interface AppNotification {
  id: string
  type: 'progress' | 'success' | 'error' | 'info'
  title: string
  message: string
  progress?: number   // 0–100, только для type='progress'
  taskId?: string
  createdAt: number
  read: boolean
}

export interface DbTableStat {
  symbol: string
  timeframe: string
  count: number
  from: string | null
  to: string | null
  invalid: number
  ok: number
}

export interface ObStat {
  symbol: string
  count: number
  from: string | null
  to: string | null
  avg_imbalance: number
}

const MAX_EVENTS = 500
const MAX_CANDLES = 500

interface Store {
  connected: boolean
  setConnected: (v: boolean) => void

  mode: ExecutionMode
  setMode: (m: ExecutionMode) => void
  positions: Position[]
  setPositions: (p: Position[]) => void
  signals: Signal[]
  setSignals: (s: Signal[]) => void

  busEvents: BusEvent[]
  pushEvent: (e: BusEvent) => void
  clearEvents: () => void
  eventFilter: string
  setEventFilter: (f: string) => void

  // Realtime candles (from WS events)
  candles: Record<string, Candle[]>
  pushCandle: (key: string, c: Candle) => void

  // Historical candles loaded from DB on demand
  historicalCandles: Record<string, Candle[]>
  setHistoricalCandles: (key: string, candles: Candle[]) => void

  trades: TradeRecord[]
  pushTrade: (t: TradeRecord) => void
  demoStats: Record<string, number>
  setDemoStats: (s: Record<string, number>) => void

  dbStats: { candles: DbTableStat[]; orderbook: ObStat[] } | null
  setDbStats: (s: { candles: DbTableStat[]; orderbook: ObStat[] }) => void

  notifications: AppNotification[]
  addNotification: (n: Omit<AppNotification, 'id' | 'createdAt' | 'read'>) => string
  updateNotification: (id: string, patch: Partial<AppNotification>) => void
  markAllRead: () => void
  removeNotification: (id: string) => void

  activeTab: string
  setActiveTab: (t: string) => void

  chartSymbol: string
  chartTf: string
  setChartSymbol: (s: string) => void
  setChartTf: (tf: string) => void

  tasks: TaskInfo[]
  upsertTask: (t: TaskInfo) => void
  removeTask: (task_id: string) => void
  clearCompletedTasks: () => void

  // Backtest / Optimizer results (keyed by result.id)
  backtestResults: Record<string, BacktestResultUI>
  setBacktestResult: (key: string, r: BacktestResultUI) => void
  // Optimizer results (keyed by `strategyId:symbol`)
  optimizerResults: Record<string, OptimizerResultUI>
  setOptimizerResult: (key: string, r: OptimizerResultUI) => void
  // Running flags (keyed by strategy_id)
  backtestRunning: Record<string, boolean>
  setBacktestRunning: (strategyId: string, v: boolean) => void
  backtestProgress: Record<string, number>
  setBacktestProgress: (strategyId: string, pct: number) => void
  optimizerRunning: Record<string, boolean>
  setOptimizerRunning: (strategyId: string, v: boolean) => void


  // ── VPS Telemetry ──────────────────────────────────────────────────────────
  vpsStatus: VpsStatus | null
  setVpsStatus: (s: VpsStatus) => void
  // ── Pulse tab ──────────────────────────────────────────────────────────────
  pulseState: PulseState | null
  setPulseState: (s: PulseState) => void
  criticalEvents: CriticalEvent[]
  pushCriticalEvent: (e: CriticalEvent) => void
  markCriticalEventSeen: (id: string) => void
}

export const useStore = create<Store>()(persist((set) => ({
  connected: false,
  setConnected: (v) => set({ connected: v }),

  mode: 'alert_only',
  setMode: (m) => set({ mode: m }),
  positions: [],
  setPositions: (p) => set({ positions: p }),
  signals: [],
  setSignals: (s) => set({ signals: s }),

  busEvents: [],
  pushEvent: (e) =>
    set((state) => ({ busEvents: [e, ...state.busEvents].slice(0, MAX_EVENTS) })),
  clearEvents: () => set({ busEvents: [] }),
  eventFilter: '',
  setEventFilter: (f) => set({ eventFilter: f }),

  candles: {},
  pushCandle: (key, c) =>
    set((state) => {
      const prev = state.candles[key] ?? []
      const existing = prev.findIndex((x) => x.time === c.time)
      let next: Candle[]
      if (existing >= 0) {
        next = prev.map((x, i) => (i === existing ? c : x))
      } else {
        next = [...prev, c].slice(-MAX_CANDLES)
      }
      return { candles: { ...state.candles, [key]: next } }
    }),

  historicalCandles: {},
  setHistoricalCandles: (key, candles) =>
    set((state) => ({ historicalCandles: { ...state.historicalCandles, [key]: candles } })),

  trades: [],
  pushTrade: (t) => set((state) => ({ trades: [t, ...state.trades].slice(0, 200) })),
  demoStats: {},
  setDemoStats: (s) => set({ demoStats: s }),

  dbStats: null,
  setDbStats: (s) => set({ dbStats: s }),

  notifications: [],
  addNotification: (n) => {
    const id = `notif-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    set((s) => ({
      notifications: [{ ...n, id, createdAt: Date.now(), read: false }, ...s.notifications].slice(0, 50),
    }))
    return id
  },
  updateNotification: (id, patch) =>
    set((s) => ({
      notifications: s.notifications.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    })),
  markAllRead: () =>
    set((s) => ({ notifications: s.notifications.map((n) => ({ ...n, read: true })) })),
  removeNotification: (id) =>
    set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) })),

  activeTab: 'dashboard',
  setActiveTab: (t) => set({ activeTab: t }),

  chartSymbol: 'BTC/USDT',
  chartTf: '1m',
  setChartSymbol: (s) => set({ chartSymbol: s }),
  setChartTf: (tf) => set({ chartTf: tf }),

  tasks: [],
  upsertTask: (t) =>
    set((s) => {
      const idx = s.tasks.findIndex((x) => x.task_id === t.task_id)
      if (idx >= 0) {
        const next = [...s.tasks]
        next[idx] = { ...next[idx], ...t }
        return { tasks: next }
      }
      return { tasks: [t, ...s.tasks].slice(0, 100) }
    }),
  removeTask: (task_id) =>
    set((s) => ({ tasks: s.tasks.filter((t) => t.task_id !== task_id) })),
  clearCompletedTasks: () =>
    set((s) => ({ tasks: s.tasks.filter((t) => t.status === 'running' || t.status === 'paused') })),

  backtestResults: {},
  setBacktestResult: (key, r) => set((s) => ({ backtestResults: { ...s.backtestResults, [key]: r } })),
  optimizerResults: {},
  setOptimizerResult: (key, r) => set((s) => ({ optimizerResults: { ...s.optimizerResults, [key]: r } })),
  backtestRunning: {},
  setBacktestRunning: (id, v) => set((s) => ({ backtestRunning: { ...s.backtestRunning, [id]: v } })),
  backtestProgress: {},
  setBacktestProgress: (id, pct) => set((s) => ({ backtestProgress: { ...s.backtestProgress, [id]: pct } })),
  optimizerRunning: {},
  setOptimizerRunning: (id, v) => set((s) => ({ optimizerRunning: { ...s.optimizerRunning, [id]: v } })),

  vpsStatus: null,
  setVpsStatus: (s) => set({ vpsStatus: s }),
  pulseState: null,
  setPulseState: (s) => set({ pulseState: s }),
  criticalEvents: [],
  pushCriticalEvent: (e) =>
    set((s) => ({
      criticalEvents: [e, ...s.criticalEvents.filter(x => x.id !== e.id)].slice(0, 200),
    })),
  markCriticalEventSeen: (id) =>
    set((s) => ({
      criticalEvents: s.criticalEvents.map(e => e.id === id ? { ...e, seen: true } : e),
    })),
}), {
  name: 'terminal-ui',
  partialize: (state) => ({
    activeTab: state.activeTab,
    chartSymbol: state.chartSymbol,
    chartTf: state.chartTf,
  }),
}))
