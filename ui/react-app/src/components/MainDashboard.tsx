import { BalanceCard }     from './cards/BalanceCard'
import { WalletCard }      from './cards/WalletCard'
import { TransactionCard } from './cards/TransactionCard'
import { ExchangePanel }   from './exchange/ExchangePanel'
import { GrowthChart }     from './chart/GrowthChart'
import { CoinCard }        from './cards/CoinCard'

const COIN_CARDS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']

export function MainDashboard() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 16,
      height: '100%',
      overflow: 'auto',
    }}>
      {/* Top row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr 1.2fr', gap: 16 }}>
        <BalanceCard />
        <WalletCard />
        <TransactionCard />
      </div>

      {/* Mid row */}
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16, minHeight: 300 }}>
        <ExchangePanel />
        <GrowthChart />
      </div>

      {/* Bottom row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {COIN_CARDS.map((sym) => <CoinCard key={sym} symbol={sym} />)}
      </div>
    </div>
  )
}
