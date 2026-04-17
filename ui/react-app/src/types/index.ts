export type Direction = 'bull' | 'bear'
export type ExecutionMode = 'auto' | 'semi_auto' | 'alert_only'
export type AnomalyType = 'anomaly.flash_crash' | 'anomaly.price_spike' | 'anomaly.ob_manip' | 'anomaly.slippage'

export interface Signal {
  id: string
  symbol: string
  direction: Direction
  score: number
  source: string
  auto_eligible: boolean
  created_at: string
  expires_at: string
  details?: Record<string, unknown>
}

export interface Position {
  symbol: string
  direction: Direction
  entry_price: number
  size_usd: number
  opened_at: string
}

export interface BusEvent {
  id: string           // uuid generated client-side for React key
  event_type: string
  data: Record<string, unknown>
  ts: string
}

export interface Candle {
  time: number         // unix seconds (for Lightweight Charts)
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface SystemState {
  mode: ExecutionMode
  positions: Position[]
  signals: Signal[]
  connected: boolean
}

export interface TradeRecord {
  trade_id: string
  symbol?: string
  direction: Direction
  entry_price: number
  exit_price: number
  size_usd: number
  pnl: number
  pnl_pct: number
  closed_by: string
  entry_time: number
  exit_time: number
}
