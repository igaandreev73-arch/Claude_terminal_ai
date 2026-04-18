import { clsx } from 'clsx'

const COIN_MAP: Record<string, string> = {
  BTC: 'coin-btc', ETH: 'coin-eth', USDT: 'coin-usdt',
  BNB: 'coin-bnb', SOL: 'coin-sol', XRP: 'coin-xrp',
}

interface Props {
  symbol: string
  size?: 'sm' | 'md' | 'lg'
}

export function CoinAvatar({ symbol, size = 'md' }: Props) {
  const ticker = symbol.replace('/USDT', '').replace('-USDT', '')
  const colorClass = COIN_MAP[ticker] ?? 'coin-btc'
  const sizeClass = `coin-avatar-${size}`
  return (
    <div className={clsx('coin-avatar', colorClass, sizeClass)}>
      {ticker.slice(0, 3)}
    </div>
  )
}
