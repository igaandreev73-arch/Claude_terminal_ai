import { useEffect, useRef } from 'react'
import { useStore } from '../store/useStore'
import type { BusEvent, Candle, Position, Signal, TradeRecord } from '../types'

const WS_URL = 'ws://localhost:8765/ws'
const RECONNECT_MS = 3000

let eventCounter = 0

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const {
    setConnected, setMode, setPositions, setSignals,
    pushEvent, pushCandle, pushTrade, setDemoStats, setDbStats,
    addNotification, updateNotification,
  } = useStore()

  // taskId → notificationId (для обновления прогресс-уведомлений)
  const notifMapRef = useRef<Map<string, string>>(new Map())

  function connect() {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }

    ws.onclose = () => {
      setConnected(false)
      reconnectTimer.current = setTimeout(connect, RECONNECT_MS)
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string)
        handleMessage(msg)
      } catch {
        // ignore malformed
      }
    }
  }

  function handleMessage(msg: Record<string, unknown>) {
    const type = msg.type as string

    if (type === 'state') {
      setPositions((msg.positions ?? []) as Position[])
      setSignals((msg.signals ?? []) as Signal[])
      setMode((msg.mode ?? 'alert_only') as string as ReturnType<typeof useStore.getState>['mode'])
      return
    }

    if (type === 'mode_changed') {
      setMode(msg.mode as ReturnType<typeof useStore.getState>['mode'])
      return
    }

    if (type === 'pong') return

    if (type === 'db_stats') {
      setDbStats(msg as any)
      return
    }

    if (type === 'candles_data') {
      const key = `${msg.symbol as string}:${msg.tf as string}`
      useStore.getState().setHistoricalCandles(key, msg.candles as Candle[])
      return
    }

    if (type === 'event') {
      const eventType = msg.event_type as string
      const data = (msg.data ?? {}) as Record<string, unknown>
      const ts = msg.ts as string

      // ── Backfill notifications ────────────────────────────────────────────
      if (eventType === 'backfill.progress') {
        const taskId  = data.task_id as string
        const symbol  = data.symbol  as string
        const percent = data.percent as number
        const fetched = data.fetched as number
        const total   = data.total   as number
        const tf      = (data.current_tf as string) || ''
        const existing = notifMapRef.current.get(taskId)
        if (existing) {
          updateNotification(existing, {
            progress: percent,
            message: `${symbol} · ${tf} · ${fetched}/${total} запросов (${percent}%)`,
          })
        } else {
          const id = addNotification({
            type: 'progress', title: `Загрузка: ${symbol}`,
            message: `Запускается загрузка…`, progress: 0, taskId,
          })
          notifMapRef.current.set(taskId, id)
        }
        return
      }
      if (eventType === 'backfill.complete') {
        const taskId = data.task_id as string
        const symbol = data.symbol  as string
        const existing = notifMapRef.current.get(taskId)
        if (existing) {
          updateNotification(existing, { type: 'success', progress: 100, message: `Данные загружены для ${symbol}` })
          notifMapRef.current.delete(taskId)
        } else {
          addNotification({ type: 'success', title: `Загрузка завершена`, message: `${symbol}: данные загружены` })
        }
        // Автоматически обновляем статистику БД
        wsRef.current?.send(JSON.stringify({ type: 'command', command: 'get_db_stats', payload: {} }))
        return
      }
      if (eventType === 'backfill.error') {
        const taskId = data.task_id as string
        const existing = notifMapRef.current.get(taskId)
        const err = data.error as string
        if (existing) {
          updateNotification(existing, { type: 'error', message: `Ошибка: ${err}` })
          notifMapRef.current.delete(taskId)
        } else {
          addNotification({ type: 'error', title: `Ошибка загрузки`, message: err })
        }
        return
      }

      const busEvent: BusEvent = {
        id: String(++eventCounter),
        event_type: eventType,
        data,
        ts,
      }
      pushEvent(busEvent)

      // Candle updates → chart store
      if (eventType === 'candle.1m.closed') {
        const candle = data as Record<string, unknown>
        if (candle.symbol && candle.open_time) {
          const c: Candle = {
            time: Math.floor((candle.open_time as number) / 1000),
            open: candle.open as number,
            high: candle.high as number,
            low: candle.low as number,
            close: candle.close as number,
            volume: candle.volume as number,
          }
          pushCandle(`${candle.symbol as string}:1m`, c)
        }
      }

      // Signal updates
      if (eventType === 'signal.generated') {
        const s = data as unknown as Signal
        const signals = useStore.getState().signals
        useStore.getState().setSignals([s, ...signals.filter((x) => x.id !== s.id)].slice(0, 50))
      }
      if (eventType === 'signal.expired' || eventType === 'signal.executed') {
        const id = data.id as string
        useStore.getState().setSignals(useStore.getState().signals.filter((s) => s.id !== id))
      }

      // Position updates
      if (eventType === 'execution.position_opened') {
        const pos = data as unknown as Position
        const positions = useStore.getState().positions
        useStore.getState().setPositions([...positions, pos])
      }
      if (eventType === 'execution.position_closed') {
        const sym = (data.symbol ?? data.symbol) as string
        useStore.getState().setPositions(
          useStore.getState().positions.filter((p) => p.symbol !== sym)
        )
      }

      // Demo trades
      if (eventType === 'demo.trade.closed') {
        pushTrade(data as unknown as TradeRecord)
      }
      if (eventType === 'demo.stats.updated') {
        setDemoStats(data as Record<string, number>)
      }
    }
  }

  function send(message: Record<string, unknown>) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    }
  }

  function startBackfill(symbol: string, period: string) {
    const taskId = `${symbol}-${period}-${Date.now()}`
    // Создаём уведомление немедленно, не ждём WS-события
    const id = addNotification({
      type: 'progress',
      title: `Загрузка: ${symbol}`,
      message: 'Запрос отправлен, ожидаем старта…',
      progress: 0,
      taskId,
    })
    notifMapRef.current.set(taskId, id)
    send({ type: 'command', command: 'start_backfill', payload: { symbol, period, task_id: taskId } })
  }

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])

  return { send, startBackfill }
}
