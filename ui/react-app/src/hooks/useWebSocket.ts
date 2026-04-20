import { useEffect, useRef } from 'react'
import { useStore } from '../store/useStore'
import type { BacktestResultUI, OptimizerResultUI, TaskInfo, PulseState, CriticalEvent } from '../store/useStore'
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
    setPulseState, pushCriticalEvent,
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
        setBacktestResult(r.id, r)
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

    if (type === 'pulse_state') {
      setPulseState(msg as unknown as PulseState)
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
        const stratId = data.strategy_id as string
        const runId   = data.run_id as string
        setBacktestRunning(stratId, true)
        setBacktestProgress(stratId, 0)
        upsertTask({
          task_id: runId, type: 'backtest',
          symbol: data.symbol as string,
          period: `${data.symbol}/${data.timeframe}`,
          status: 'running', percent: 0, fetched: 0, total_pages: 0,
          created_at: Math.floor(Date.now() / 1000),
        })
        return
      }
      if (eventType === 'backtest.progress') {
        const pct = data.percent as number
        setBacktestProgress(data.strategy_id as string, pct)
        upsertTask({
          task_id: data.run_id as string, type: 'backtest',
          symbol: data.symbol as string || '',
          status: 'running', percent: pct, fetched: 0, total_pages: 0,
        })
        return
      }
      if (eventType === 'backtest.completed') {
        const r = data as unknown as BacktestResultUI
        setBacktestResult(r.id, r)
        setBacktestRunning(r.strategy_id, false)
        const pnl = r.metrics?.total_pnl_pct ?? 0
        addNotification({
          type: 'success', title: `Бэктест завершён: ${r.symbol}`,
          message: `PnL ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}% · ${r.trades_count} сделок`,
        })
        upsertTask({
          task_id: r.id, type: 'backtest',
          symbol: r.symbol, period: `${r.symbol}/${r.timeframe}`,
          status: 'completed', percent: 100, fetched: 0, total_pages: 0,
        })
        return
      }
      if (eventType === 'backtest.error') {
        const stratId = data.strategy_id as string
        const runId   = (data.run_id as string) || stratId
        setBacktestRunning(stratId, false)
        addNotification({ type: 'error', title: 'Ошибка бэктеста', message: data.error as string })
        upsertTask({
          task_id: runId, type: 'backtest',
          symbol: (data.symbol as string) || '',
          status: 'error', percent: 0, fetched: 0, total_pages: 0,
          error: data.error as string,
        })
        return
      }
      if (eventType === 'optimizer.started') {
        const stratId = data.strategy_id as string
        const runId   = data.run_id as string
        setOptimizerRunning(stratId, true)
        upsertTask({
          task_id: runId, type: 'optimizer',
          symbol: data.symbol as string,
          period: `${data.symbol}/${data.timeframe}`,
          status: 'running', percent: 0, fetched: 0, total_pages: 0,
          created_at: Math.floor(Date.now() / 1000),
        })
        return
      }
      if (eventType === 'optimizer.completed') {
        const r = data as unknown as OptimizerResultUI
        setOptimizerResult(`${r.strategy_id}:${r.symbol}`, r)
        setOptimizerRunning(r.strategy_id, false)
        addNotification({
          type: 'success', title: `Оптимизация завершена: ${r.symbol}`,
          message: `Лучший ${r.target_metric}: ${(r.best_metric ?? 0).toFixed(3)}`,
        })
        upsertTask({
          task_id: r.run_id, type: 'optimizer',
          symbol: r.symbol, period: `${r.symbol}/${r.timeframe}`,
          status: 'completed', percent: 100, fetched: 0, total_pages: 0,
        })
        return
      }
      if (eventType === 'optimizer.error') {
        const stratId = data.strategy_id as string
        const runId   = (data.run_id as string) || stratId
        setOptimizerRunning(stratId, false)
        // Force store to true first so the useEffect in StrategiesView always sees a change
        useStore.setState((s) => ({
          optimizerRunning: { ...s.optimizerRunning, [stratId]: true },
        }))
        setTimeout(() => setOptimizerRunning(stratId, false), 0)
        addNotification({ type: 'error', title: 'Ошибка оптимизации', message: data.error as string })
        upsertTask({
          task_id: runId, type: 'optimizer',
          symbol: (data.symbol as string) || '',
          status: 'error', percent: 0, fetched: 0, total_pages: 0,
          error: data.error as string,
        })
        return
      }

      // ── Watchdog events → criticalEvents ─────────────────────────────────
      if (eventType === 'watchdog.degraded' || eventType === 'watchdog.lost' || eventType === 'watchdog.dead') {
        const level: CriticalEvent['level'] =
          eventType === 'watchdog.dead' ? 'critical' :
          eventType === 'watchdog.lost' ? 'error' : 'warning'
        const conn = data.connection as string
        pushCriticalEvent({
          id: `${eventType}:${conn}`,
          level,
          module: conn,
          message: eventType === 'watchdog.degraded'
            ? `Соединение ${conn} деградировало`
            : eventType === 'watchdog.lost'
            ? `Соединение ${conn} потеряно`
            : `Соединение ${conn} мертво — нужно ручное вмешательство`,
          started_at: (data.since as number) ?? Math.floor(Date.now() / 1000),
          seen: false,
        })
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

  function requestPulseState() {
    send({ type: 'command', command: 'get_pulse_state', payload: {} })
  }

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])

  return { send, startBackfill, stopTask, resumeTask, runValidation, runBacktest, runOptimizer, getBacktestResults, requestPulseState }
}
