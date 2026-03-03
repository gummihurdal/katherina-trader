import { useAppStore } from '@/stores/appStore'
import { Panel } from '@/components/shared/Panel'
import { AllocationBar } from '@/components/shared/AllocationBar'
import { formatCurrency } from '@/lib/utils'
import type { SignalSource } from '@/types'

function SourceMini({ source }: { source: SignalSource }) {
  const statusColor = source.status === 'connected' || source.status === 'active'
    ? 'var(--color-bull)' : source.status === 'error' ? 'var(--color-bear)' : 'var(--color-text-ghost)'
  
  return (
    <div className="rounded-md border px-3 py-2.5"
      style={{
        background: 'var(--color-slate-deep)',
        borderColor: 'var(--color-border-dim)',
        borderTop: `2px solid ${source.color}`,
      }}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[12px] font-semibold" style={{ color: 'var(--color-text-bright)' }}>
          {source.display_name}
        </span>
        <span className="w-1.5 h-1.5 rounded-full"
          style={{ background: statusColor, boxShadow: source.is_active ? `0 0 5px ${statusColor}` : 'none' }} />
      </div>
      <div className="text-[10px] mb-1" style={{ color: 'var(--color-text-dim)' }}>
        {source.signals_today} signals today
      </div>
      <div className="flex justify-between text-[11px]">
        <span style={{ color: source.win_rate > 0 ? 'var(--color-text)' : 'var(--color-text-dim)' }}>
          {source.win_rate}% win
        </span>
        <span className="font-mono tabular-nums"
          style={{ color: source.pnl_mtd >= 0 ? 'var(--color-bull)' : 'var(--color-bear)' }}>
          {source.pnl_mtd >= 0 ? '+' : ''}{formatCurrency(source.pnl_mtd)}
        </span>
      </div>
    </div>
  )
}

export function SourceHealth() {
  const { sources } = useAppStore()
  
  return (
    <div className="flex flex-col gap-4">
      <Panel title="SOURCE HEALTH">
        <div className="flex flex-col gap-2">
          {sources.map(s => <SourceMini key={s.id} source={s} />)}
        </div>
      </Panel>
      
      <Panel title="ALLOCATION">
        <div>
          {sources.filter(s => s.current_allocation_pct > 0).map(s => (
            <AllocationBar key={s.id}
              label={s.display_name}
              current={s.current_allocation_pct}
              max={s.max_allocation_pct}
              color={s.color} />
          ))}
          <div className="mt-2 pt-2 border-t" style={{ borderColor: 'var(--color-border-dim)' }}>
            <AllocationBar label="Cash Reserve" current={0.251} max={1.0} color="var(--color-bull)" />
          </div>
        </div>
      </Panel>
    </div>
  )
}
