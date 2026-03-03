import { useAppStore } from '@/stores/appStore'
import { Header } from '@/components/layout/Header'
import { TabBar } from '@/components/layout/TabBar'
import { StatCard } from '@/components/shared/StatCard'
import { SignalFeed } from '@/components/signals/SignalFeed'
import { SourceHealth } from '@/components/signals/SourceHealth'
import { PositionsTable } from '@/components/positions/PositionsTable'
import { GuardianPanel } from '@/components/risk/GuardianPanel'
import { SourcesGrid } from '@/components/sources/SourcesGrid'
import { formatCurrency, formatPnl, formatPct } from '@/lib/utils'

export default function App() {
  const { activeTab, risk, positions, signals } = useAppStore()
  
  const totalPnl = positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0)
  const approvedCount = signals.filter(s => s.risk_approved === true).length
  const rejectedCount = signals.filter(s => s.risk_approved === false).length

  return (
    <div className="min-h-screen" style={{ background: 'var(--color-obsidian)' }}>
      <Header />
      <TabBar />
      
      <main className="p-5">
        {/* Stats Row */}
        <div className="flex flex-wrap gap-3 mb-5">
          <StatCard label="Portfolio Value" value={formatCurrency(risk.portfolio_value)} sub={`${risk.positions_count} positions`} />
          <StatCard label="Day P&L" value={formatPnl(risk.daily_pnl)} sub={formatPct(risk.daily_pnl_pct * 100)} color={risk.daily_pnl >= 0 ? 'var(--color-bull)' : 'var(--color-bear)'} />
          <StatCard label="Signals Today" value={`${signals.length}`} sub={`${approvedCount} approved · ${rejectedCount} rejected`} color="var(--color-arctic)" />
          <StatCard label="Cash Reserve" value={`${(risk.cash_pct * 100).toFixed(1)}%`} sub={formatCurrency(risk.portfolio_value * risk.cash_pct) + ' available'} />
          <StatCard label="Win Rate (30d)" value="69%" sub="142 / 206 trades" color="var(--color-bull)" />
          <StatCard label="Max Drawdown" value="-2.1%" sub="All-time: -4.8%" color="var(--color-warn)" />
        </div>

        {/* Tab Content */}
        {activeTab === 'signals' && (
          <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 320px' }}>
            <SignalFeed />
            <SourceHealth />
          </div>
        )}
        
        {activeTab === 'positions' && <PositionsTable />}
        {activeTab === 'risk' && <GuardianPanel />}
        {activeTab === 'sources' && <SourcesGrid />}
        
        {activeTab === 'trades' && (
          <div className="rounded-md border p-8 text-center"
            style={{ background: 'var(--color-slate-card)', borderColor: 'var(--color-border)' }}>
            <div className="text-lg mb-2" style={{ color: 'var(--color-text-dim)' }}>📓</div>
            <div className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
              Trade Journal — Coming in Phase 3
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
