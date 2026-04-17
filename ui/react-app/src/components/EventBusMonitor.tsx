import { useRef, useEffect, useState } from 'react'
import { useStore } from '../store/useStore'

const EVENT_COLORS: Record<string, string> = {
  'candle':      '#4a9eff',
  'ta':          '#7c6fcd',
  'smc':         '#9b59b6',
  'volume':      '#2ecc71',
  'ob':          '#e67e22',
  'mtf':         '#1abc9c',
  'correlation': '#3498db',
  'signal':      '#f39c12',
  'anomaly':     '#e74c3c',
  'execution':   '#00ff88',
  'demo':        '#95a5a6',
  'HEALTH':      '#bdc3c7',
}

function getColor(eventType: string): string {
  const prefix = eventType.split('.')[0]
  return EVENT_COLORS[prefix] ?? '#666'
}

function formatData(data: Record<string, unknown>): string {
  const keys = ['symbol', 'direction', 'score', 'pnl', 'change_pct', 'drop_pct', 'message']
  const parts: string[] = []
  for (const k of keys) {
    if (k in data) {
      const v = data[k]
      parts.push(`${k}=${typeof v === 'number' ? v.toFixed(3) : String(v)}`)
    }
  }
  return parts.join(' · ') || JSON.stringify(data).slice(0, 80)
}

export default function EventBusMonitor() {
  const { busEvents, clearEvents, eventFilter, setEventFilter } = useStore()
  const [paused, setPaused] = useState(false)
  const [localFilter, setLocalFilter] = useState(eventFilter)
  const bottomRef = useRef<HTMLDivElement>(null)

  const filtered = busEvents.filter((e) =>
    !localFilter || e.event_type.includes(localFilter) || JSON.stringify(e.data).includes(localFilter)
  )

  // Auto-scroll to top (newest events are first)
  useEffect(() => {
    if (!paused && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [busEvents.length, paused])

  return (
    <div className="event-monitor">
      <div className="monitor-toolbar">
        <input
          className="filter-input"
          placeholder="Фильтр (event type, symbol, ...)"
          value={localFilter}
          onChange={(e) => {
            setLocalFilter(e.target.value)
            setEventFilter(e.target.value)
          }}
        />
        <span className="event-count">{filtered.length} событий</span>
        <button className={`toolbar-btn ${paused ? 'active' : ''}`} onClick={() => setPaused(!paused)}>
          {paused ? '▶ Возобновить' : '⏸ Пауза'}
        </button>
        <button className="toolbar-btn" onClick={clearEvents}>Очистить</button>
      </div>

      <div className="event-legend">
        {Object.entries(EVENT_COLORS).map(([k, c]) => (
          <span key={k} className="legend-item" style={{ borderColor: c }}>
            {k}
          </span>
        ))}
      </div>

      <div className="event-list">
        {filtered.slice(0, 300).map((ev) => (
          <div key={ev.id} className="event-row">
            <span className="event-time">{ev.ts.slice(11, 19)}</span>
            <span
              className="event-type"
              style={{ color: getColor(ev.event_type) }}
            >
              {ev.event_type}
            </span>
            <span className="event-data">{formatData(ev.data)}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
