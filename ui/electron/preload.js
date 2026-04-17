const { contextBridge } = require('electron')

// Expose a minimal API to the renderer process.
// All real communication goes through WebSocket (ws://localhost:8765/ws),
// so the preload is intentionally minimal.
contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  version: process.versions.electron,
})
