/**
 * useVpsTelemetry — polling VPS telemetry every 5 seconds.
 * Также предоставляет функцию для получения свечей с VPS REST API.
 */
import { useEffect, useRef } from 'react'
import { useStore } from '../store/useStore'

const VPS_URL  = 'http://132.243.235.173:8800'
const VPS_KEY  = 'vps_telemetry_key_2026'
const INTERVAL = 5000

async function fetchVpsStatus(): Promise<VpsStatus | null> {
  const ctrl  = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 6000)
  try {
    const res = await fetch(`${VPS_URL}/status?api_key=${VPS_KEY}`, { signal: ctrl.signal })
    clearTimeout(timer)
    if (!res.ok) return null
    return await res.json() as VpsStatus
  } catch {
    clearTimeout(timer)
    return null
  }
}

/**
 * Запрашивает свечи напрямую с VPS REST API.
 * Используется как fallback, если локальный WS сервер недоступен.
 */
export async function fetchVpsCandles(
  symbol: string,
  tf: string,
  limit: number = 500,
  marketType: string = 'spot',
): Promise<OHLCVBar[] | null> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 10000)
  try {
    const params = new URLSearchParams({
      symbol, tf, limit: String(limit), market_type: marketType,
    })
    const res = await fetch(
      `${VPS_URL}/api/candles?api_key=${VPS_KEY}&${params}`,
      { signal: ctrl.signal },
    )
    clearTimeout(timer)
    if (!res.ok) return null
    const json = await res.json() as { candles: OHLCVBar[] }
    return json.candles
  } catch {
    clearTimeout(timer)
    return null
  }
}

export interface VpsSymbolData {
  symbol:       string
  candles:      number
  first_candle: string | null
  last_candle:  string | null
  ob_snapshots: number
  liquidations: number
  trust_score:  number
}

export interface VpsStatus {
  timestamp:    string
  service: {
    active: boolean
    status: string
    since:  string
  }
  system: {
    cpu_percent:  number
    ram_used_mb:  number
    ram_total_mb: number
    ram_percent:  number
    disk_used_gb: number
    disk_free_gb: number
    disk_percent: number
  }
  database: {
    size_mb:             number
    candles:             number
    orderbook_snapshots: number
    liquidations:        number
    trades_raw:          number
    futures_metrics:     number
  }
  data:        VpsSymbolData[]
  symbols:     string[]
  telegram_ok: boolean
}

export interface OHLCVBar {
  open_time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  is_closed?: boolean
}

export function useVpsTelemetry() {
  const setVpsStatus = useStore((s: any) => s.setVpsStatus)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    fetchVpsStatus().then(data => { if (data) setVpsStatus(data) })
    timerRef.current = setInterval(async () => {
      const data = await fetchVpsStatus()
      if (data) setVpsStatus(data)
    }, INTERVAL)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])
}
