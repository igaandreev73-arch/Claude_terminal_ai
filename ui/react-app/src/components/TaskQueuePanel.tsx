import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Layers, X, Play, Square, CheckCircle, AlertCircle, Clock, Loader } from 'lucide-react'
import { useStore } from '../store/useStore'
import type { TaskInfo } from '../store/useStore'

function formatEta(seconds: number | undefined): string {
  if (!seconds || seconds <= 0) return ''
  if (seconds < 60) return `~${Math.round(seconds)}с`
  if (seconds < 3600) return `~${Math.round(seconds / 60)}м`
  return `~${Math.round(seconds / 3600)}ч`
}

function TaskStatusIcon({ status }: { status: string }) {
  if (status === 'running') return (
    <span style={{ display: 'flex', animation: 'spin 1s linear infinite' }}>
      <Loader size={13} color="var(--accent-blue)" />
    </span>
  )
  if (status === 'completed') return <CheckCircle size={13} color="var(--accent-green)" />
  if (status === 'error')     return <AlertCircle size={13} color="var(--accent-red)" />
  if (status === 'paused')    return <Clock size={13} color="var(--accent-orange)" />
  return <Clock size={13} color="var(--text-muted)" />
}

function ValidationResult({ result }: { result: string | undefined }) {
  if (!result) return null
  try {
    const r = JSON.parse(result)
    const ok = r.ok as boolean
    return (
      <div style={{ fontSize: 10, color: ok ? 'var(--accent-green)' : 'var(--accent-red)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>
        {ok ? '✓ OK' : '✗ Проблемы'} · проверено {r.total_checked ?? 0} · пропущено {r.total_missing ?? 0} · расхождений {r.total_mismatch ?? 0}
      </div>
    )
  } catch {
    return null
  }
}

interface TaskRowProps {
  task: TaskInfo
  onStop: (id: string) => void
  onResume: (id: string) => void
}

const TASK_TYPE_LABEL: Record<string, string> = {
  backfill: 'Загрузка',
  validation: 'Проверка',
  backtest: 'Бэктест',
  optimizer: 'Оптимизация',
}

const TASK_TYPE_COLOR: Record<string, string> = {
  backfill: 'var(--accent-blue)',
  validation: 'var(--accent-purple)',
  backtest: 'var(--accent-green)',
  optimizer: 'var(--accent-orange)',
}

function TaskRow({ task, onStop, onResume }: TaskRowProps) {
  const isRunning = task.status === 'running'
  const isPaused  = task.status === 'paused'
  const isValidation = task.type === 'validation'
  const isBackground = task.type === 'backtest' || task.type === 'optimizer'
  const typeLabel = TASK_TYPE_LABEL[task.type] ?? task.type
  const typeColor = TASK_TYPE_COLOR[task.type] ?? 'var(--text-muted)'

  return (
    <div style={{
      padding: '10px 14px',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <TaskStatusIcon status={task.status} />
        <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', background: typeColor + '18', color: typeColor, padding: '1px 6px', borderRadius: 4, flexShrink: 0 }}>
          {typeLabel}
        </span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>
          {task.symbol}
          {task.period ? <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> · {task.period}</span> : null}
        </span>
        {isRunning && !isBackground && (
          <button
            onClick={() => onStop(task.task_id)}
            title="Остановить"
            style={{
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer', padding: '2px 6px',
              color: 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: 4,
              fontSize: 11,
            }}
          >
            <Square size={10} /> Стоп
          </button>
        )}
        {isPaused && (
          <button
            onClick={() => onResume(task.task_id)}
            title="Продолжить"
            style={{
              background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.25)',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer', padding: '2px 6px',
              color: 'var(--accent-blue)', display: 'flex', alignItems: 'center', gap: 4,
              fontSize: 11,
            }}
          >
            <Play size={10} /> Продолжить
          </button>
        )}
      </div>

      {isRunning && !isValidation && (
        <>
          <div style={{ height: 3, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: isBackground ? `${task.percent || 0}%` : `${task.percent}%`,
              background: typeColor,
              borderRadius: 2,
              transition: 'width 0.4s ease',
            }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
            {isBackground
              ? <span>{task.percent}% завершено</span>
              : <span>{task.percent}% · {task.fetched}/{task.total_pages} стр.</span>
            }
            <span>
              {!isBackground && task.speed_cps ? `${task.speed_cps.toFixed(0)} св/с` : ''}
              {!isBackground && task.eta_seconds ? ` · ETA ${formatEta(task.eta_seconds)}` : ''}
            </span>
          </div>
        </>
      )}

      {(task.status === 'completed' || task.status === 'error') && (
        <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {task.status === 'completed' && task.total_saved
            ? `Сохранено: ${task.total_saved.toLocaleString()} свечей`
            : null}
          {task.status === 'error' && task.error
            ? <span style={{ color: 'var(--accent-red)' }}>Ошибка: {task.error}</span>
            : null}
          {isValidation && <ValidationResult result={task.result} />}
        </div>
      )}

      {isPaused && (
        <div style={{ fontSize: 10, color: 'var(--accent-orange)', fontFamily: 'var(--font-mono)' }}>
          Приостановлено · {task.percent}% выполнено
        </div>
      )}
    </div>
  )
}

// ── Dropdown panel ────────────────────────────────────────────────────────────

interface TaskPanelProps {
  rect: DOMRect
  onClose: () => void
  onStop: (id: string) => void
  onResume: (id: string) => void
}

function TaskPanel({ rect, onClose, onStop, onResume }: TaskPanelProps) {
  const { tasks, clearCompletedTasks } = useStore()

  const running   = tasks.filter(t => t.status === 'running')
  const paused    = tasks.filter(t => t.status === 'paused')
  const finished  = tasks.filter(t => t.status === 'completed' || t.status === 'error').slice(0, 10)

  const hasAny = running.length > 0 || paused.length > 0 || finished.length > 0

  return createPortal(
    <div style={{
      position: 'fixed',
      top: rect.bottom + 8,
      right: window.innerWidth - rect.right,
      width: 340,
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
      zIndex: 500,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 14px',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          Очередь задач
        </span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {finished.length > 0 && (
            <button
              onClick={clearCompletedTasks}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: 'var(--text-muted)' }}
            >
              Очистить завершённые
            </button>
          )}
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: 'var(--text-muted)' }}>
            <X size={13} />
          </button>
        </div>
      </div>

      {/* List */}
      <div style={{ maxHeight: 440, overflowY: 'auto' }}>
        {!hasAny && (
          <div style={{ padding: '24px 14px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
            Нет активных задач
          </div>
        )}

        {running.length > 0 && (
          <>
            <div style={{ padding: '6px 14px', fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', background: 'var(--bg-elevated)' }}>
              ВЫПОЛНЯЕТСЯ · {running.length}
            </div>
            {running.map(t => (
              <TaskRow key={t.task_id} task={t} onStop={onStop} onResume={onResume} />
            ))}
          </>
        )}

        {paused.length > 0 && (
          <>
            <div style={{ padding: '6px 14px', fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', background: 'var(--bg-elevated)' }}>
              ПРИОСТАНОВЛЕНО · {paused.length}
            </div>
            {paused.map(t => (
              <TaskRow key={t.task_id} task={t} onStop={onStop} onResume={onResume} />
            ))}
          </>
        )}

        {finished.length > 0 && (
          <>
            <div style={{ padding: '6px 14px', fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.08em', fontFamily: 'var(--font-mono)', background: 'var(--bg-elevated)' }}>
              ЗАВЕРШЕНО
            </div>
            {finished.map(t => (
              <TaskRow key={t.task_id} task={t} onStop={onStop} onResume={onResume} />
            ))}
          </>
        )}
      </div>
    </div>,
    document.body
  )
}

// ── Icon button (exported for TopBar) ────────────────────────────────────────

interface TaskQueueIconProps {
  onStop: (id: string) => void
  onResume: (id: string) => void
}

export function TaskQueueIcon({ onStop, onResume }: TaskQueueIconProps) {
  const { tasks } = useStore()
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLDivElement>(null)

  const runningCount = tasks.filter(t => t.status === 'running').length
  const isRunning    = runningCount > 0

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (btnRef.current && !btnRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const rect = btnRef.current?.getBoundingClientRect()

  return (
    <div ref={btnRef} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          background: open ? 'var(--bg-elevated)' : 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 6,
          borderRadius: 'var(--radius-sm)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          position: 'relative',
          transition: 'background 0.15s',
        }}
        title="Очередь задач"
      >
        <span style={{ display: 'flex', animation: isRunning ? 'spin 2s linear infinite' : 'none' }}>
          <Layers
            size={16}
            color={isRunning ? 'var(--accent-blue)' : 'var(--text-secondary)'}
            style={{ transition: 'color 0.2s' }}
          />
        </span>
        {runningCount > 0 && (
          <span style={{
            position: 'absolute', top: 2, right: 2,
            minWidth: 14, height: 14,
            background: 'var(--accent-blue)',
            borderRadius: 7,
            fontSize: 9,
            fontWeight: 700,
            color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '0 3px',
            fontFamily: 'var(--font-mono)',
          }}>
            {runningCount > 9 ? '9+' : runningCount}
          </span>
        )}
      </button>

      {open && rect && (
        <TaskPanel
          rect={rect}
          onClose={() => setOpen(false)}
          onStop={(id) => { onStop(id) }}
          onResume={(id) => { onResume(id) }}
        />
      )}
    </div>
  )
}
