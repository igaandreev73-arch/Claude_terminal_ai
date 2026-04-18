import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Bell, Search, CheckCircle, AlertCircle, X, Loader } from 'lucide-react'
import { LiveDot } from '../ui/LiveDot'
import { useStore } from '../../store/useStore'
import type { AppNotification } from '../../store/useStore'

const NAV_TABS = [
  { id: 'dashboard',  label: 'Дашборд'      },
  { id: 'chart',      label: 'График'        },
  { id: 'trade',      label: 'Торговля'      },
  { id: 'analytics',  label: 'Аналитика'     },
  { id: 'strategies', label: 'Стратегии'     },
  { id: 'data',       label: 'Данные'        },
  { id: 'events',     label: 'Шина событий'  },
]

// ── Notification item ─────────────────────────────────────────────────────────

function NotifIcon({ type }: { type: AppNotification['type'] }) {
  if (type === 'success') return <CheckCircle size={14} color="var(--accent-green)" />
  if (type === 'error')   return <AlertCircle size={14} color="var(--accent-red)" />
  if (type === 'progress') return (
    <span style={{ display: 'flex', animation: 'spin 1s linear infinite' }}>
      <Loader size={14} color="var(--accent-blue)" />
    </span>
  )
  return <Bell size={14} color="var(--text-muted)" />
}

function NotifItem({ n, onRemove }: { n: AppNotification; onRemove: () => void }) {
  const age = Math.round((Date.now() - n.createdAt) / 1000)
  const ageStr = age < 60 ? `${age}с назад` : `${Math.round(age / 60)}м назад`

  return (
    <div style={{
      padding: '10px 14px',
      borderBottom: '1px solid var(--border-subtle)',
      background: n.read ? 'transparent' : 'rgba(59,130,246,0.04)',
      position: 'relative',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ marginTop: 1, flexShrink: 0 }}><NotifIcon type={n.type} /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
            {n.title}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', wordBreak: 'break-word' }}>
            {n.message}
          </div>
          {n.type === 'progress' && n.progress !== undefined && (
            <div style={{ marginTop: 6 }}>
              <div style={{
                height: 3, background: 'var(--bg-elevated)',
                borderRadius: 2, overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%',
                  width: `${n.progress}%`,
                  background: 'var(--accent-blue)',
                  borderRadius: 2,
                  transition: 'width 0.4s ease',
                }} />
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
                {n.progress}%
              </div>
            </div>
          )}
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{ageStr}</div>
        </div>
        <button
          onClick={onRemove}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: 'var(--text-muted)', flexShrink: 0 }}
        >
          <X size={11} />
        </button>
      </div>
    </div>
  )
}

// ── Bell with dropdown ────────────────────────────────────────────────────────

function NotificationBell() {
  const { notifications, markAllRead, removeNotification } = useStore()
  const [open, setOpen] = useState(false)
  const [shake, setShake] = useState(false)
  const bellRef = useRef<HTMLDivElement>(null)
  const prevCount = useRef(notifications.length)

  const unread = notifications.filter(n => !n.read).length

  // Shake animation when new notification arrives
  useEffect(() => {
    if (notifications.length > prevCount.current) {
      setShake(true)
      setTimeout(() => setShake(false), 600)
    }
    prevCount.current = notifications.length
  }, [notifications.length])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleOpen = () => {
    setOpen(v => !v)
    if (!open) markAllRead()
  }

  const rect = bellRef.current?.getBoundingClientRect()

  return (
    <div ref={bellRef} style={{ position: 'relative' }}>
      <button
        onClick={handleOpen}
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
          animation: shake ? 'bellShake 0.5s ease' : 'none',
          transition: 'background 0.15s',
        }}
        title="Уведомления"
      >
        <Bell
          size={16}
          color={unread > 0 ? 'var(--accent-blue)' : 'var(--text-secondary)'}
          style={{ transition: 'color 0.2s' }}
        />
        {unread > 0 && (
          <span style={{
            position: 'absolute', top: 2, right: 2,
            minWidth: 14, height: 14,
            background: 'var(--accent-red)',
            borderRadius: 7,
            fontSize: 9,
            fontWeight: 700,
            color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '0 3px',
            fontFamily: 'var(--font-mono)',
            animation: 'livePulse 2s ease infinite',
          }}>
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && rect && createPortal(
        <div style={{
          position: 'fixed',
          top: rect.bottom + 8,
          right: window.innerWidth - rect.right,
          width: 320,
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
              Уведомления
            </span>
            {notifications.length > 0 && (
              <button
                onClick={() => notifications.forEach(n => removeNotification(n.id))}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: 'var(--text-muted)' }}
              >
                Очистить всё
              </button>
            )}
          </div>

          {/* List */}
          <div style={{ maxHeight: 400, overflowY: 'auto' }}>
            {notifications.length === 0 ? (
              <div style={{ padding: '24px 14px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                Уведомлений нет
              </div>
            ) : (
              notifications.map(n => (
                <NotifItem
                  key={n.id}
                  n={n}
                  onRemove={() => removeNotification(n.id)}
                />
              ))
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

// ── TopBar ────────────────────────────────────────────────────────────────────

export function TopBar() {
  const { activeTab, setActiveTab, connected } = useStore()

  return (
    <>
      <style>{`
        @keyframes bellShake {
          0%,100% { transform: rotate(0deg); }
          15%      { transform: rotate(-15deg); }
          30%      { transform: rotate(12deg); }
          45%      { transform: rotate(-10deg); }
          60%      { transform: rotate(8deg); }
          75%      { transform: rotate(-5deg); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>

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
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          {/* Search */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            background: 'var(--bg-input)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-pill)',
            padding: '6px 12px',
            width: 160,
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
          <NotificationBell />

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
    </>
  )
}
