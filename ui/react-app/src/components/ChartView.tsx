import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createChart, IChartApi, ISeriesApi,
  CrosshairMode, UTCTimestamp,
} from 'lightweight-charts'
import { useStore } from '../store/useStore'
import { fetchVpsCandles } from '../hooks/useVpsTelemetry'

const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
const TFS     = ['1m', '5m', '15m', '1h', '4h', '1d']

type OHLCVBar = { time: UTCTimestamp; open: number; high: number; low: number; close: number; volume: number }

function mergeCandles(a: OHLCVBar[], b: OHLCVBar[]): OHLCVBar[] {
  const map = new Map<number, OHLCVBar>()
  for (const c of a) map.set(c.time as number, c)
  for (const c of b) map.set(c.time as number, c)
  return Array.from(map.values()).sort((x, y) => (x.time as number) - (y.time as number))
}

export default function ChartView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)
  const candleRef    = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef    = useRef<ISeriesApi<'Histogram'> | null>(null)
  const { chartSymbol, chartTf, setChartSymbol, setChartTf } = useStore()
  const vpsConfig = useStore(s => s.vpsConfig)
  const key = `${chartSymbol}:${chartTf}`

  // Selectors — subscribe to only the data we need to redraw
  const histCandles = useStore(s => s.historicalCandles[key] as OHLCVBar[] | undefined)
  const rtCandles   = useStore(s => s.candles[key] as OHLCVBar[] | undefined)

  const [loading,   setLoading]   = useState(false)
  const [lastPrice, setLastPrice] = useState<number | null>(null)

  // ── Create chart once ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#8b949e',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1c2128' },
        horzLines: { color: '#1c2128' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#444c56', labelBackgroundColor: '#2d333b' },
        horzLine: { color: '#444c56', labelBackgroundColor: '#2d333b' },
      },
      rightPriceScale: {
        borderColor: '#2d333b',
        scaleMargins: { top: 0.08, bottom: 0.22 },
      },
      timeScale: {
        borderColor: '#2d333b',
        timeVisible: true,
        secondsVisible: false,
        barSpacing: 8,
      },
      width:  containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#26a641', downColor: '#f85149',
      borderVisible: false,
      wickUpColor: '#26a641', wickDownColor: '#f85149',
    })

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })

    chartRef.current  = chart
    candleRef.current = candleSeries
    volumeRef.current = volumeSeries

    const ro = new ResizeObserver(() => {
      if (containerRef.current)
        chart.applyOptions({
          width:  containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
    })
    ro.observe(containerRef.current)

    return () => { ro.disconnect(); chart.remove() }
  }, [])

  // ── Fetch historical candles via VPS REST API ────────────────────────────────
  const fetchCandles = useCallback(async (symbol: string, tf: string) => {
    setLoading(true)
    try {
      const raw = await fetchVpsCandles(vpsConfig, symbol, tf, 500, 'spot')
      if (raw) {
        // OHLCVBar.open_time (ms) → Candle.time (s)
        const candles = raw.map(c => ({
          time: Math.floor(c.open_time / 1000) as UTCTimestamp,
          open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume,
        }))
        const key = `${symbol}:${tf}`
        useStore.getState().setHistoricalCandles(key, candles)
      } else {
        console.warn('ChartView: VPS не вернул свечи для', symbol, tf)
      }
    } catch (e) {
      console.error('Ошибка загрузки свечей с VPS:', e)
    } finally {
      setLoading(false)
    }
  }, [vpsConfig])

  // ── Request data when symbol/tf changes ──────────────────────────────────────
  useEffect(() => {
    void fetchCandles(chartSymbol, chartTf)
  }, [chartSymbol, chartTf, fetchCandles])

  // ── Redraw chart when data arrives ───────────────────────────────────────────
  useEffect(() => {
    if (!candleRef.current || !volumeRef.current) return

    const hist = histCandles ?? []
    const rt   = rtCandles   ?? []
    const data = mergeCandles(hist, rt)

    if (data.length === 0) return

    const last = data[data.length - 1]
    setLastPrice(last.close)

    candleRef.current.setData(data.map(c => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })))
    volumeRef.current.setData(data.map(c => ({
      time: c.time, value: c.volume,
      color: c.close >= c.open ? '#26a64155' : '#f8514955',
    })))
    chartRef.current?.timeScale().scrollToRealTime()
  }, [histCandles, rtCandles])

  const first    = histCandles?.[0]
  const pct      = first && lastPrice ? ((lastPrice - first.open) / first.open) * 100 : null
  const histCount = histCandles?.length ?? 0
  const rtCount   = rtCandles?.length   ?? 0

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', background:'var(--bg-app)' }}>

      {/* Toolbar */}
      <div style={{
        display:'flex', alignItems:'center', gap:12,
        padding:'10px 16px',
        background:'var(--bg-surface)',
        borderBottom:'1px solid var(--border-subtle)',
        flexShrink: 0,
      }}>
        {/* Symbol */}
        <div style={{ display:'flex', gap:2, background:'var(--bg-elevated)', borderRadius:'var(--radius-md)', padding:2 }}>
          {SYMBOLS.map(s => (
            <button key={s} onClick={() => setChartSymbol(s)} style={{
              border:'none', cursor:'pointer', borderRadius:'var(--radius-sm)',
              padding:'4px 10px', fontSize:12, fontWeight:600,
              fontFamily:'var(--font-display)',
              background: chartSymbol === s ? 'var(--bg-surface)' : 'transparent',
              color: chartSymbol === s ? 'var(--text-primary)' : 'var(--text-muted)',
              transition:'all 0.15s',
            }}>{s.replace('/USDT', '')}</button>
          ))}
        </div>

        <div style={{ width:1, height:20, background:'var(--border-subtle)' }} />

        {/* Timeframe */}
        <div style={{ display:'flex', gap:2, background:'var(--bg-elevated)', borderRadius:'var(--radius-md)', padding:2 }}>
          {TFS.map(tf => (
            <button key={tf} onClick={() => setChartTf(tf)} style={{
              border:'none', cursor:'pointer', borderRadius:'var(--radius-sm)',
              padding:'4px 8px', fontSize:11, fontWeight:600,
              fontFamily:'var(--font-mono)',
              background: chartTf === tf ? 'var(--accent-blue)' : 'transparent',
              color: chartTf === tf ? '#fff' : 'var(--text-muted)',
              transition:'all 0.15s',
            }}>{tf}</button>
          ))}
        </div>

        <div style={{ width:1, height:20, background:'var(--border-subtle)' }} />

        {/* Price */}
        <div style={{ display:'flex', alignItems:'baseline', gap:8 }}>
          <span style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:16, color:'var(--text-primary)' }}>
            {lastPrice
              ? lastPrice.toLocaleString('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 })
              : '—'}
          </span>
          {pct !== null && (
            <span style={{ fontSize:12, fontFamily:'var(--font-mono)', color: pct >= 0 ? '#26a641' : '#f85149' }}>
              {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
            </span>
          )}
        </div>

        {/* Stats */}
        <div style={{ marginLeft:'auto', fontSize:11, color:'var(--text-muted)', fontFamily:'var(--font-mono)', display:'flex', gap:12, alignItems:'center' }}>
          {histCount > 0
            ? <span style={{ color:'var(--accent-green)' }}>БД: {histCount}</span>
            : <span>БД: —</span>}
          {rtCount > 0 && <span style={{ color:'var(--accent-blue)' }}>RT: {rtCount}</span>}
          <span>{chartSymbol} · {chartTf}</span>
        </div>
      </div>

      {/* Chart */}
      <div style={{ position:'relative', flex:1, overflow:'hidden' }}>
        <div ref={containerRef} style={{ width:'100%', height:'100%' }} />

        {loading && (
          <div style={{
            position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center',
            background:'rgba(13,17,23,0.7)', backdropFilter:'blur(4px)',
          }}>
            <span style={{ color:'var(--text-muted)', fontSize:13, fontFamily:'var(--font-mono)' }}>
              Загрузка данных…
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
