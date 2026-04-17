import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi } from 'lightweight-charts'
import { useStore } from '../store/useStore'

const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
const TIMEFRAMES = ['1m', '3m', '5m', '15m', '1h', '4h']

export default function ChartView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  const { chartSymbol, chartTf, candles, setChartSymbol, setChartTf } = useStore()
  const key = `${chartSymbol}:${chartTf}`

  // Create chart once
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#0d1117' },
        textColor: '#c9d1d9',
      },
      grid: {
        vertLines: { color: '#21262d' },
        horzLines: { color: '#21262d' },
      },
      crosshair: { mode: 1 },
      timeScale: { timeVisible: true, secondsVisible: false },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    })

    const series = chart.addCandlestickSeries({
      upColor: '#00ff88',
      downColor: '#ff4444',
      borderVisible: false,
      wickUpColor: '#00ff88',
      wickDownColor: '#ff4444',
    })

    chartRef.current = chart
    seriesRef.current = series

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [])

  // Update series data when symbol/tf changes or new candles arrive
  useEffect(() => {
    if (!seriesRef.current) return
    const data = candles[key] ?? []
    if (data.length > 0) {
      seriesRef.current.setData(
        data.map((c) => ({
          time: c.time as import('lightweight-charts').UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))
      )
    }
  }, [key, candles])

  return (
    <div className="chart-view">
      <div className="chart-toolbar">
        <div className="selector-group">
          {SYMBOLS.map((s) => (
            <button
              key={s}
              className={`selector-btn ${chartSymbol === s ? 'active' : ''}`}
              onClick={() => setChartSymbol(s)}
            >
              {s.replace('/USDT', '')}
            </button>
          ))}
        </div>
        <div className="selector-group">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              className={`selector-btn ${chartTf === tf ? 'active' : ''}`}
              onClick={() => setChartTf(tf)}
            >
              {tf}
            </button>
          ))}
        </div>
        <span className="chart-title">
          {chartSymbol} · {chartTf}
        </span>
      </div>
      <div ref={containerRef} className="chart-container" />
    </div>
  )
}
