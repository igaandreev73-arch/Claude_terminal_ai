import { useState } from 'react'
import { useStore, type VpsConfig } from '../store/useStore'

interface Props {
  open: boolean
  onClose: () => void
}

export default function VpsSettingsModal({ open, onClose }: Props) {
  const config = useStore(s => s.vpsConfig)
  const setVpsConfig = useStore(s => s.setVpsConfig)

  const [host, setHost] = useState(config.host)
  const [port, setPort] = useState(String(config.port))
  const [apiKey, setApiKey] = useState(config.apiKey)
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle')
  const [testMsg, setTestMsg] = useState('')
  const [error, setError] = useState('')

  if (!open) return null

  function validate(): boolean {
    if (!host.trim()) { setError('Укажите адрес сервера'); return false }
    const p = parseInt(port, 10)
    if (isNaN(p) || p < 1 || p > 65535) { setError('Порт должен быть числом от 1 до 65535'); return false }
    if (!apiKey.trim()) { setError('Укажите API-ключ'); return false }
    setError('')
    return true
  }

  async function testConnection() {
    if (!validate()) return
    setTestStatus('testing')
    setTestMsg('')
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 6000)
    try {
      const res = await fetch(
        `http://${host.trim()}:${parseInt(port, 10)}/health?api_key=${apiKey.trim()}`,
        { signal: ctrl.signal },
      )
      clearTimeout(timer)
      if (res.ok) {
        setTestStatus('ok')
        setTestMsg('✅ Соединение установлено')
      } else {
        setTestStatus('error')
        setTestMsg(`❌ HTTP ${res.status}: ${res.statusText}`)
      }
    } catch (e: any) {
      clearTimeout(timer)
      setTestStatus('error')
      setTestMsg(`❌ Ошибка: ${e.message || 'таймаут'}`)
    }
  }

  function save() {
    if (!validate()) return
    const cfg: VpsConfig = { host: host.trim(), port: parseInt(port, 10), apiKey: apiKey.trim() }
    setVpsConfig(cfg)
    onClose()
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 10px',
    borderRadius: 6,
    border: '1px solid var(--border-subtle)',
    background: 'var(--bg-surface)',
    color: 'var(--text-primary)',
    fontSize: 13,
    fontFamily: 'var(--font-mono)',
    outline: 'none',
    boxSizing: 'border-box',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)',
    marginBottom: 4,
  }

  const btnStyle: React.CSSProperties = {
    padding: '7px 16px',
    borderRadius: 6,
    border: 'none',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg-elevated)',
        borderRadius: 'var(--radius-lg)',
        padding: '20px 24px',
        width: 420,
        maxWidth: '90vw',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 16 }}>
          ⚙️ Настройки VPS-сервера
        </div>

        {/* Host */}
        <div style={{ marginBottom: 12 }}>
          <div style={labelStyle}>Адрес сервера</div>
          <input
            style={inputStyle}
            value={host}
            onChange={e => { setHost(e.target.value); setTestStatus('idle') }}
            placeholder="132.243.235.173"
          />
        </div>

        {/* Port */}
        <div style={{ marginBottom: 12 }}>
          <div style={labelStyle}>Порт</div>
          <input
            style={inputStyle}
            value={port}
            onChange={e => { setPort(e.target.value); setTestStatus('idle') }}
            placeholder="8800"
          />
        </div>

        {/* API Key */}
        <div style={{ marginBottom: 16 }}>
          <div style={labelStyle}>API-ключ</div>
          <input
            style={inputStyle}
            type="password"
            value={apiKey}
            onChange={e => { setApiKey(e.target.value); setTestStatus('idle') }}
            placeholder="vps_telemetry_key_2026"
          />
        </div>

        {/* Error */}
        {error && (
          <div style={{ color: '#f87171', fontSize: 11, marginBottom: 12, fontFamily: 'var(--font-mono)' }}>
            {error}
          </div>
        )}

        {/* Test result */}
        {testStatus !== 'idle' && (
          <div style={{
            padding: '8px 12px',
            borderRadius: 6,
            marginBottom: 12,
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            background: testStatus === 'ok' ? '#14532d' : testStatus === 'error' ? '#7f1d1d' : '#1e293b',
            color: testStatus === 'ok' ? '#86efac' : testStatus === 'error' ? '#fca5a5' : '#94a3b8',
          }}>
            {testStatus === 'testing' ? '⏳ Проверка соединения...' : testMsg}
          </div>
        )}

        {/* Buttons */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button
            style={{ ...btnStyle, background: 'var(--bg-surface)', color: 'var(--text-muted)' }}
            onClick={onClose}
          >
            Отмена
          </button>
          <button
            style={{ ...btnStyle, background: '#1e3a5f', color: '#93c5fd' }}
            onClick={testConnection}
          >
            🔍 Проверить
          </button>
          <button
            style={{ ...btnStyle, background: '#14532d', color: '#86efac' }}
            onClick={save}
          >
            💾 Сохранить
          </button>
        </div>
      </div>
    </div>
  )
}
