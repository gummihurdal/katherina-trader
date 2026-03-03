import { useAppStore } from '@/stores/appStore'
import { Panel } from '@/components/shared/Panel'
import type { RiskCheck } from '@/types'
import { RISK_LIMITS } from '@/lib/constants'

function CheckRow({ check }: { check: RiskCheck }) {
  const icon = check.status === 'pass' ? '✓' : check.status === 'warn' ? '⚠' : '✗'
  const color = check.status === 'pass' ? 'var(--color-bull)' : check.status === 'warn' ? 'var(--color-warn)' : 'var(--color-bear)'
  return (
    <div className="flex items-center gap-2 py-1 text-xs">
      <span className="w-4 text-center text-[13px]" style={{ color }}>{icon}</span>
      <span className="w-28" style={{ color: 'var(--color-text)' }}>{check.name}</span>
      <span className="flex-1 font-mono text-[11px]"
        style={{ color: check.status === 'warn' ? 'var(--color-warn)' : 'var(--color-text-dim)' }}>
        {check.value}
      </span>
    </div>
  )
}

export function GuardianPanel() {
  const { riskChecks, risk, isHalted } = useAppStore()
  const allPassing = riskChecks.every(c => c.status !== 'fail')

  const breakers = [
    { label: 'Daily Loss >3%', value: `Current: ${(risk.daily_pnl_pct * 100).toFixed(1)}%` },
    { label: 'Weekly Loss >5%', value: `Current: ${(risk.weekly_pnl_pct * 100).toFixed(1)}%` },
    { label: 'Single Source >2%/day', value: 'Max: C2 +1.1%' },
    { label: 'Signal Flood >20/src', value: 'Max: Holly 6' },
    { label: 'IBKR Connection', value: 'Paper:7496' },
    { label: 'Data Feed', value: '5s TTL' },
  ]

  const limits = [
    ['Per trade', `${(RISK_LIMITS.maxPositionPct * 100)}%`],
    ['Portfolio heat', `${(RISK_LIMITS.maxPortfolioRisk * 100)}%`],
    ['Daily loss', `${(RISK_LIMITS.maxDailyLoss * 100)}%`],
    ['Weekly loss', `${(RISK_LIMITS.maxWeeklyLoss * 100)}%`],
    ['Concentration', `${(RISK_LIMITS.maxConcentration * 100)}%`],
    ['Options cap', `${(RISK_LIMITS.maxOptionsPct * 100)}%`],
    ['Cash reserve', `≥${(RISK_LIMITS.minCashReserve * 100)}%`],
    ['Max positions', `${RISK_LIMITS.maxPositions}`],
  ]

  return (
    <div className="grid grid-cols-2 gap-4">
      <Panel title="🛡 Guardian — 10 Risk Checks">
        <div>
          {riskChecks.map((c, i) => <CheckRow key={i} check={c} />)}
          <div className="mt-3 py-2 px-3 rounded text-center text-[11px] border"
            style={{
              background: allPassing && !isHalted ? 'var(--color-bull-dim)' : 'var(--color-bear-dim)',
              borderColor: allPassing && !isHalted ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)',
              color: allPassing && !isHalted ? 'var(--color-bull)' : 'var(--color-bear)',
            }}>
            {isHalted ? '⏹ SYSTEM HALTED — Manual resume required' :
              allPassing ? 'ALL CHECKS PASSING — System operational' : 'CHECKS FAILING — Review required'}
          </div>
        </div>
      </Panel>
      
      <div className="flex flex-col gap-4">
        <Panel title="Circuit Breakers">
          <div>
            {breakers.map((b, i) => (
              <div key={i} className="flex items-center gap-2 py-1 text-xs">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-bull)' }} />
                <span className="flex-1" style={{ color: 'var(--color-text)' }}>{b.label}</span>
                <span className="font-mono text-[11px]" style={{ color: 'var(--color-text-dim)' }}>{b.value}</span>
              </div>
            ))}
          </div>
        </Panel>
        
        <Panel title="Risk Limits">
          <div>
            {limits.map(([k, v], i) => (
              <div key={i} className="flex justify-between py-1 text-xs">
                <span style={{ color: 'var(--color-text-dim)' }}>{k}</span>
                <span className="font-mono" style={{ color: 'var(--color-text)' }}>{v}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}
