import { useEffect, useRef } from 'react'
import { useStore } from '../store/useStore'
import type { BacktestResultUI, OptimizerResultUI, TaskInfo } from '../store/useStore'
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
    upsertTask,
    setBacktestResult, setOptimizerResult,
    setBacktestRunning, setOptimizerRunning,
    setBacktestProgress,
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
      // Восстанавливаем уведомления для задач, которые ещё идут на бэкенде
      const backfills = (msg.active_backfills ?? []) as Array<{
        task_id: string; symbol: string; period: string; percent: number;
        fetched: number; total: number; status: string; speed_cps?: number; eta_seconds?: number
      }>
      for (const bf of backfills) {
        if (!notifMapRef.current.has(bf.task_id)) {
          const id = addNotification({
            type: 'progress',
            title: `Загрузка: ${bf.symbol}`,
            message: `Восстановлено после переподключения`,
            progress: bf.percent,
            taskId: bf.task_id,
          })
          notifMapRef.current.set(bf.task_id, id)
        }
        upsertTask({
          task_id: bf.task_id,
          type: 'backfill',
          symbol: bf.symbol,
          period: bf.period,
          status: bf.status ?? 'running',
          percent: bf.percent,
          fetched: bf.fetched ?? 0,
          total_pages: bf.total ?? 0,
          speed_cps: bf.speed_cps,
          eta_seconds: bf.eta_seconds,
        })
      }
      // Приостановленные задачи
      const pausedTasks = (msg.paused_tasks ?? []) as TaskInfo[]
      for (const pt of pausedTasks) {
        upsertTask(pt)
      }
      return
    }

    if (type === 'mode_changed') {
      setMode(msg.mode as ReturnType<typeof useStore.getState>['mode'])
      return
    }

    if (type === 'pong') return

    if (type === 'backtest_results') {
      for (const r of (msg.results ?? []) as BacktestResultUI[]) {
        setBacktestResult(`${r.strategy_id}:${r.symbol}:${r.timeframe}`, r)
      }
      return
    }

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
        const taskId    = data.task_id as string
        const symbol    = data.symbol  as string
        const percent   = data.percent as number
        const fetched   = data.fetched as number
        const total     = data.total   as number
        const tf        = (data.current_tf as string) || ''
        const speedCps  = data.speed_cps as number | undefined
        const etaSec    = data.eta_seconds as number | undefined
        const status    = (data.status as string) || 'running'
        const existing  = notifMapRef.current.get(taskId)
        const speedStr  = speedCps ? ` · ${speedCps.toFixed(0)} св/с` : ''
        if (existing) {
          updateNotification(existing, {
            progress: percent,
            message: `${symbol} · ${tf} · ${fetched}/${total} запросов (${percent}%)${speedStr}`,
          })
        } else {
          const id = addNotification({
            type: 'progress', title: `Загрузка: ${symbol}`,
            message: `Запускается загрузка…`, progress: 0, taskId,
          })
          notifMapRef.current.set(taskId, id)
        }
        upsertTask({
          task_id: taskId,
          type: 'backfill',
          symbol,
          period: data.period as string | undefined,
          status,
          percent,
          fetched,
          total_pages: total,
          total_saved: data.total_saved as number | undefined,
          speed_cps: speedCps,
          eta_seconds: etaSec,
        })
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
        upsertTask({
          task_id: taskId,
          type: 'backfill',
          symbol,
          period: data.period as string | undefined,
          status: 'completed',
          percent: 100,
          fetched: 0,
          total_pages: 0,
          total_saved: data.total_saved as number | undefined,
        })
        // Автоматически обновляем статистику БД
        wsRef.current?.send(JSON.stringify({ type: 'command', command: 'get_db_stats', payload: {} }))
        return
      }
      if (eventType === 'backfill.error') {
        const taskId = data.task_id as string
        const symbol = (data.symbol ?? '') as string
        const existing = notifMapRef.current.get(taskId)
        const err = data.error as string
        if (existing) {
          updateNotification(existing, { type: 'error', message: `Ошибка: ${err}` })
          notifMapRef.current.delete(taskId)
        } else {
          addNotification({ type: 'error', title: `Ошибка загрузки`, message: err })
        }
        upsertTask({
          task_id: taskId,
          type: 'backfill',
          symbol,
          status: 'error',
          percent: 0,
          fetched: 0,
          total_pages: 0,
          error: err,
        })
        return
      }
      if (eventType === 'backtest.started') {
        setBacktestRunning(data.strategy_id as string, true)
        setBacktestProgress(data.strategy_id as string, 0)
        return
      }
      if (eventType === 'backtest.progress') {
        setBacktestProgress(data.strategy_id as string, data.percent as number)
        return
      }
      if (eventType === 'backtest.completed') {
        const r = data as unknown as BacktestResultUI
        setBacktestResult(`${r.strategy_id}:${r.symbol}:${r.timeframe}`, r)
        setBacktestRunning(r.strategy_id, false)
        return
      }
      if (eventType === 'backtest.error') {
        setBacktestRunning(data.strategy_id as string, false)
        addNotification({ type: 'error', title: 'Ошибка бэктеста', message: data.error as string })
        return
      }
      if (eventType === 'optimizer.started') {
        setOptimizerRunning(data.strategy_id as string, true)
        return
      }
      if (eventType === 'optimizer.completed') {
        const r = data as unknown as OptimizerResultUI
        setOptimizerResult(`${r.strategy_id}:${r.symbol}`, r)
        setOptimizerRunning(r.strategy_id, false)
        return
      }
      if (eventType === 'optimizer.error') {
        setOptimizerRunning(data.strategy_id as string, false)
        addNotification({ type: 'error', title: 'Ошибка оптимизации', message: data.error as string })
        return
      }

      if (eventType === 'validation.result') {
        const taskId = data.task_id as string
        const symbol = data.symbol  as string
        upsertTask({
          task_id: taskId,
          type: 'validation',
          symbol,
          status: (data.status as string) === 'error' ? 'error' : 'completed',
          percent: 100,
          fetched: 0,
          total_pages: 0,
          result: JSON.stringify(data),
          error: data.error as string | undefined,
        })
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

  function stopTask(task_id: string) {
    send({ type: 'command', command: 'stop_task', payload: { task_id } })
  }

  function resumeTask(task_id: string) {
    send({ type: 'command', command: 'resume_task', payload: { task_id } })
  }

  function runValidation(symbol: string, mode: 'quick' | 'full') {
    send({ type: 'command', command: 'run_validation', payload: { symbol, mode } })
  }

  function runBacktest(strategyId: string, symbol: string, timeframe: string, params: Record<string, number>) {
    send({ type: 'command', command: 'run_backtest', payload: { strategy_id: strategyId, symbol, timeframe, params } })
  }

  function runOptimizer(strategyId: string, symbol: string, timeframe: string, paramGrid: Record<string, number[]>, targetMetric: string, walkForward: boolean) {
    send({ type: 'command', command: 'run_optimizer', payload: { strategy_id: strategyId, symbol, timeframe, param_grid: paramGrid, target_metric: targetMetric, walk_forward: walkForward } })
  }

  function getBacktestResults(strategyId: string) {
    send({ type: 'command', command: 'get_backtest_results', payload: { strategy_id: strategyId } })
  }

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])

  return { send, startBackfill, stopTask, resumeTask, runValidation, runBacktest, runOptimizer, getBacktestResults }
}
