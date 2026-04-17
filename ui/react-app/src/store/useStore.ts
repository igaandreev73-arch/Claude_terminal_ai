import { create } from 'zustand'
import type { BusEvent, Candle, ExecutionMode, Position, Signal, TradeRecord } from '../types'

const MAX_EVENTS = 500
const MAX_CANDLES = 500

interface Store {
  // Connection
  connected: boolean
  setConnected: (v: boolean) => void

  // System state
  mode: ExecutionMode
  setMode: (m: ExecutionMode) => void
  positions: Position[]
  setPositions: (p: Position[]) => void
  signals: Signal[]
  setSignals: (s: Signal[]) => void

  // Event Bus Monitor
  busEvents: BusEvent[]
  pushEvent: (e: BusEvent) => void
  clearEvents: () => void
  eventFilter: string
  setEventFilter: (f: string) => void

  // Charts — candles per symbol+tf
  candles: Record<string, Candle[]>
  pushCandle: (key: string, c: Candle) => void

  // Demo / paper trades
  trades: TradeRecord[]
  pushTrade: (t: TradeRecord) => void
  demoStats: Record<string, number>
  setDemoStats: (s: Record<string, number>) => void

  // Active tab
  activeTab: string
  setActiveTab: (t: string) => void

  // Selected chart symbol / tf
  chartSymbol: string
  chartTf: string
  setChartSymbol: (s: string) => void
  setChartTf: (tf: string) => void
}

export const useStore = create<Store>((set) => ({
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
    set((state) => ({
      busEvents: [e, ...state.busEvents].slice(0, MAX_EVENTS),
    })),
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

  trades: [],
  pushTrade: (t) => set((state) => ({ trades: [t, ...state.trades].slice(0, 200) })),
  demoStats: {},
  setDemoStats: (s) => set({ demoStats: s }),

  activeTab: 'dashboard',
  setActiveTab: (t) => set({ activeTab: t }),

  chartSymbol: 'BTC/USDT',
  chartTf: '1m',
  setChartSymbol: (s) => set({ chartSymbol: s }),
  setChartTf: (tf) => set({ chartTf: tf }),
}))
