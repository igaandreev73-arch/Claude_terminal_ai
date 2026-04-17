import React from 'react'
import { useStore } from '../store/useStore'

const TABS = [
  { id: 'dashboard',  label: '⬛ Dashboard' },
  { id: 'chart',      label: '📈 График' },
  { id: 'trade',      label: '⚡ Trade' },
  { id: 'analytics',  label: '📊 Аналитика' },
  { id: 'events',     label: '🔌 Event Bus' },
]

export default function Sidebar() {
  const { activeTab, setActiveTab, connected, busEvents } = useStore()
  const eventsPerSec = busEvents.filter(
    (e) => Date.now() - new Date(e.ts).getTime() < 1000
  ).length

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <span className="logo-text">⬡ CRYPTO</span>
        <span className="logo-sub">Terminal</span>
      </div>

      <nav className="sidebar-nav">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.id === 'events' && busEvents.length > 0 && (
              <span className="nav-badge">{busEvents.length}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className={`conn-status ${connected ? 'online' : 'offline'}`}>
          <span className="dot" />
          {connected ? 'Online' : 'Offline'}
        </div>
        <div className="event-rate">{eventsPerSec} ev/s</div>
      </div>
    </aside>
  )
}
