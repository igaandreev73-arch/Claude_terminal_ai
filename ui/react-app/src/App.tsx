import { useStore }       from './store/useStore'
import { useWebSocket }   from './hooks/useWebSocket'
import { TopBar }         from './components/layout/TopBar'
import { MainDashboard }  from './components/MainDashboard'
import ChartView          from './components/ChartView'
import TradePanel         from './components/TradePanel'
import Analytics          from './components/Analytics'
import DataView           from './components/DataView'
import EventBusMonitor    from './components/EventBusMonitor'
import StrategiesView     from './components/StrategiesView'

export default function App() {
  const { activeTab } = useStore()
  const { send, startBackfill, stopTask, resumeTask, runValidation } = useWebSocket()

  function openPosition(params: {
    symbol: string; direction: 'bull' | 'bear'
    size_usd: number; leverage: number; sl_pct: number; tp_pct: number
  }) {
    send({ type: 'command', command: 'open_position', payload: params })
  }

  return (
    <div style={{ display: 'grid', gridTemplateRows: '56px 1fr', height: '100vh', background: 'var(--bg-app)' }}>
      <TopBar onStopTask={stopTask} onResumeTask={resumeTask} />

      <main style={{ padding: '20px 24px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {activeTab === 'dashboard' && <MainDashboard />}
        {activeTab === 'chart'     && <ChartView />}
        {activeTab === 'trade'     && (
          <TradePanel onOpenPosition={openPosition} />
        )}
        {activeTab === 'analytics'   && <Analytics />}
        {activeTab === 'strategies'  && <StrategiesView />}
        {activeTab === 'data'        && (
          <DataView
            onRequestStats={() => send({ type: 'command', command: 'get_db_stats', payload: {} })}
            startBackfill={startBackfill}
            runValidation={runValidation}
          />
        )}
        {activeTab === 'events'    && <EventBusMonitor />}
      </main>
    </div>
  )
}
