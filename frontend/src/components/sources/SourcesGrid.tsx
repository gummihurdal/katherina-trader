import { useAppStore } from '@/stores/appStore'
import { formatCurrency } from '@/lib/utils'
import type { SignalSource } from '@/types'

function SourceCard({ source }: { source: SignalSource }) {
  return (
    <div className="rounded-md border px-4 py-4 flex-1 min-w-[260px]"
      style={{
        background: 'var(--color-slate-card)',
        borderColor: 'var(--color-border)',
        borderTop: `3px solid ${source.color}`,
      }}>
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-[15px] font-bold" style={{ color: 'var(--color-text-white)' }}>
          {source.display_name}
        </span>
        <span className="text-[10px] font-semibold px-2 py-0.5 rounded tracking-wider uppercase border"
          style={{
            background: source.is_active ? 'var(--color-bull-dim)' : 'var(--color-slate-hover)',
            color: source.is_active ? 'var(--color-bull)' : 'var(--color-text-dim)',
            borderColor: source.is_active ? 'rgba(16,185,129,0.2)' : 'var(--color-border)',
          }}>
          {source.status}
        </span>
      </div>
      <div className="text-[11px] mb-3" style={{ color: 'var(--color-text-dim)' }}>
        Type: {source.source_type}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: 'Win Rate', value: `${source.win_rate}%`, color: source.win_rate > 60 ? 'var(--color-bull)' : 'var(--color-text)' },
          { label: 'MTD P&L', value: formatCurrency(source.pnl_mtd), color: source.pnl_mtd >= 0 ? 'var(--color-bull)' : 'var(--color-bear)' },
          { label: 'Signals Today', value: `${source.signals_today}`, color: 'var(--color-text)' },
          { label: 'Allocation', value: `${(source.current_allocation_pct * 100).toFixed(0)}%`, color: 'var(--color-arctic)' },
        ].map((item, i) => (
          <div key={i}>
            <div className="text-[10px]" style={{ color: 'var(--color-text-dim)' }}>{item.label}</div>
            <div className="text-lg font-bold font-mono tabular-nums" style={{ color: item.color }}>
              {item.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function SourcesGrid() {
  const { sources } = useAppStore()
  return (
    <div className="flex flex-wrap gap-3">
      {sources.map(s => <SourceCard key={s.id} source={s} />)}
    </div>
  )
}
