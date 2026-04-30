/**
 * useVpsTelemetry — polling VPS telemetry every 5 seconds.
 * Также предоставляет функцию для получения свечей с VPS REST API.
 * Адрес сервера и API-ключ берутся из useStore.vpsConfig.
 */
import { useEffect, useRef } from 'react'
import { useStore, type VpsConfig } from '../store/useStore'

const INTERVAL = 5000

async function fetchVpsStatus(url: string, apiKey: string): Promise<VpsStatus | null> {
  const ctrl  = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 6000)
  try {
    const res = await fetch(`${url}/status?api_key=${apiKey}`, { signal: ctrl.signal })
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
 * Принимает конфиг VPS для гибкости (может быть из store или передан вручную).
 */
export async function fetchVpsCandles(
  config: VpsConfig,
  symbol: string,
  tf: string,
  limit: number = 500,
  marketType: string = 'spot',
): Promise<OHLCVBar[] | null> {
  const baseUrl = `http://${config.host}:${config.port}`
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 10000)
  try {
    const params = new URLSearchParams({
      symbol, tf, limit: String(limit), market_type: marketType,
    })
    const res = await fetch(
      `${baseUrl}/api/candles?api_key=${config.apiKey}&${params}`,
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
  const vpsConfig = useStore((s: any) => s.vpsConfig)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const url = `http://${vpsConfig.host}:${vpsConfig.port}`

    fetchVpsStatus(url, vpsConfig.apiKey).then(data => { if (data) setVpsStatus(data) })
    timerRef.current = setInterval(async () => {
      const data = await fetchVpsStatus(url, vpsConfig.apiKey)
      if (data) setVpsStatus(data)
    }, INTERVAL)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [vpsConfig.host, vpsConfig.port, vpsConfig.apiKey, setVpsStatus])
}
