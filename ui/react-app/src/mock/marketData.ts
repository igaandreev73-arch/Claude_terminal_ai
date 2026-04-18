export const mockPrices: Record<string, number> = {
  'BTC/USDT': 64820.5,
  'ETH/USDT': 3124.8,
  'SOL/USDT': 148.32,
  'BNB/USDT': 578.9,
  'XRP/USDT': 0.5231,
}

export const mockChanges: Record<string, number> = {
  'BTC/USDT': 2.31,
  'ETH/USDT': -0.87,
  'SOL/USDT': 4.12,
  'BNB/USDT': 1.05,
  'XRP/USDT': -1.43,
}

export const mockTransactions = [
  { id: '1', symbol: 'BTC/USDT', type: 'receive' as const, amount: 0.042, usd: 2722.5,  time: '2m ago' },
  { id: '2', symbol: 'ETH/USDT', type: 'send'    as const, amount: 1.2,   usd: 3749.8,  time: '18m ago' },
  { id: '3', symbol: 'SOL/USDT', type: 'receive' as const, amount: 15.0,  usd: 2224.8,  time: '1h ago' },
  { id: '4', symbol: 'BNB/USDT', type: 'send'    as const, amount: 2.5,   usd: 1447.3,  time: '3h ago' },
  { id: '5', symbol: 'XRP/USDT', type: 'receive' as const, amount: 500,   usd: 261.6,   time: '5h ago' },
]

export const mockWalletAlloc = [
  { symbol: 'BTC', pct: 52, color: '#f59e0b' },
  { symbol: 'ETH', pct: 30, color: '#a78bfa' },
  { symbol: 'USDT', pct: 18, color: '#14b8a6' },
]

export const mockGrowthData = Array.from({ length: 24 }, (_, i) => ({
  time: `${i}:00`,
  btc:  64000 + Math.sin(i * 0.4) * 1200 + Math.random() * 400,
  eth:  3050  + Math.sin(i * 0.5 + 1) * 120 + Math.random() * 40,
}))

export const mockSparklines: Record<string, number[]> = {
  'BTC/USDT': [62100,63400,63800,62900,64200,63700,64820],
  'ETH/USDT': [3180, 3090, 3140, 3200, 3080, 3160, 3124],
  'SOL/USDT': [140,  143,  138,  151,  147,  149,  148],
  'BNB/USDT': [565,  572,  568,  581,  575,  579,  578],
}
