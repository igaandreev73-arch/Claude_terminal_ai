import React from 'react'
import { useStore } from './store/useStore'
import { useWebSocket } from './hooks/useWebSocket'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import ChartView from './components/ChartView'
import TradePanel from './components/TradePanel'
import Analytics from './components/Analytics'
import EventBusMonitor from './components/EventBusMonitor'
import type { ExecutionMode } from './types'

export default function App() {
  const { activeTab } = useStore()
  const { send } = useWebSocket()

  function confirmSignal(signalId: string) {
    send({ type: 'command', command: 'confirm_signal', payload: { signal_id: signalId } })
  }

  function rejectSignal(signalId: string) {
    send({ type: 'command', command: 'reject_signal', payload: { signal_id: signalId } })
  }

  function closePosition(symbol: string) {
    send({ type: 'command', command: 'close_position', payload: { symbol } })
  }

  function changeMode(mode: ExecutionMode) {
    send({ type: 'command', command: 'set_mode', payload: { mode } })
  }

  function openPosition(params: {
    symbol: string
    direction: 'bull' | 'bear'
    size_usd: number
    leverage: number
    sl_pct: number
    tp_pct: number
  }) {
    send({ type: 'command', command: 'open_position', payload: params })
  }

  return (
    <div className="app">
      <Sidebar />
      <main className="main-content">
        {activeTab === 'dashboard' && (
          <Dashboard
            onConfirm={confirmSignal}
            onReject={rejectSignal}
            onClose={closePosition}
            onModeChange={changeMode}
          />
        )}
        {activeTab === 'chart' && <ChartView />}
        {activeTab === 'trade' && <TradePanel onOpenPosition={openPosition} />}
        {activeTab === 'analytics' && <Analytics />}
        {activeTab === 'events' && <EventBusMonitor />}
      </main>
    </div>
  )
}
