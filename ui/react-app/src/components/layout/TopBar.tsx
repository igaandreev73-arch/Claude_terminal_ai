import { Bell, Search } from 'lucide-react'
import { LiveDot } from '../ui/LiveDot'
import { useStore } from '../../store/useStore'

const NAV_TABS = [
  { id: 'dashboard', label: 'Дашборд' },
  { id: 'chart',     label: 'График' },
  { id: 'trade',     label: 'Торговля' },
  { id: 'analytics', label: 'Аналитика' },
  { id: 'data',      label: 'Данные' },
  { id: 'events',    label: 'Шина событий' },
]

export function TopBar() {
  const { activeTab, setActiveTab, connected } = useStore()

  return (
    <header style={{
      height: 56,
      background: 'var(--bg-surface)',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 24px',
      gap: 32,
      position: 'sticky',
      top: 0,
      zIndex: 100,
      backdropFilter: 'blur(12px)',
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <div style={{
          width: 28, height: 28,
          background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
          borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14, fontWeight: 700, color: '#fff',
          fontFamily: 'var(--font-display)',
        }}>T</div>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>
          Terminal<span style={{ color: 'var(--accent-blue)' }}>.</span>
        </span>
      </div>

      {/* Nav */}
      <nav style={{ display: 'flex', gap: 4, flex: 1 }}>
        {NAV_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              border: 'none',
              padding: '6px 14px',
              cursor: 'pointer',
              fontFamily: 'var(--font-body)',
              fontSize: 13,
              color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)',
              borderRadius: 'var(--radius-md)',
              background: activeTab === tab.id ? 'var(--bg-elevated)' : 'transparent',
              transition: 'color 0.15s, background 0.15s',
              position: 'relative',
            } as React.CSSProperties}
          >
            {tab.label}
            {activeTab === tab.id && (
              <span style={{
                position: 'absolute',
                bottom: -1,
                left: '20%', right: '20%',
                height: 2,
                background: 'var(--accent-blue)',
                borderRadius: 2,
              }} />
            )}
          </button>
        ))}
      </nav>

      {/* Right side */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
        {/* Search */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--bg-input)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-pill)',
          padding: '6px 12px',
          width: 180,
        }}>
          <Search size={13} color="var(--text-muted)" />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Поиск пары…</span>
        </div>

        {/* Connection */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {connected ? <LiveDot /> : (
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--accent-red)', display: 'inline-block' }} />
          )}
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            {connected ? 'Онлайн' : 'Офлайн'}
          </span>
        </div>

        {/* Bell */}
        <div style={{ position: 'relative', cursor: 'pointer' }}>
          <Bell size={16} color="var(--text-secondary)" />
          <span style={{
            position: 'absolute', top: -3, right: -3,
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--accent-red)',
          }} />
        </div>

        {/* Avatar */}
        <div style={{
          width: 32, height: 32, borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, fontWeight: 700, color: '#fff',
          fontFamily: 'var(--font-display)',
          cursor: 'pointer',
        }}>IG</div>
      </div>
    </header>
  )
}
