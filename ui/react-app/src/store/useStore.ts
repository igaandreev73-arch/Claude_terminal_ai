import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { BusEvent, Candle, ExecutionMode, Position, Signal, TradeRecord } from '../types'

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
}), {
  name: 'terminal-ui',
  partialize: (state) => ({
    activeTab: state.activeTab,
    chartSymbol: state.chartSymbol,
    chartTf: state.chartTf,
  }),
}))
