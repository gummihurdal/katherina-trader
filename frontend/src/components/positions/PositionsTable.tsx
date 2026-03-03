import { useAppStore } from '@/stores/appStore'
import { Badge } from '@/components/shared/Badge'
import { formatCurrency, formatPnl, getAssetBadge } from '@/lib/utils'
import { SOURCE_CONFIG } from '@/lib/constants'
import type { Position, SignalSourceName } from '@/types'

function PositionRow({ pos }: { pos: Position }) {
  const srcCfg = SOURCE_CONFIG[pos.source_name as keyof typeof SOURCE_CONFIG]
  return (
    <div className="grid items-center gap-1 px-3 py-1.5 border-b font-mono text-xs"
      style={{
        gridTemplateColumns: '90px 36px 50px 80px 80px 90px 56px',
        borderColor: 'var(--color-border-dim)',
      }}>
      <span className="font-semibold truncate" style={{ color: 'var(--color-text-white)' }}>{pos.symbol}</span>
      <Badge label={getAssetBadge(pos.asset_class)} small />
      <span style={{ color: 'var(--color-text)' }}>{pos.quantity}</span>
      <span style={{ color: 'var(--color-text-dim)' }}>{formatCurrency(pos.avg_cost)}</span>
      <span style={{ color: 'var(--color-text)' }}>{pos.current_price ? formatCurrency(pos.current_price) : '—'}</span>
      <span className="font-semibold"
        style={{ color: (pos.unrealized_pnl || 0) >= 0 ? 'var(--color-bull)' : 'var(--color-bear)' }}>
        {formatPnl(pos.unrealized_pnl || 0)}
      </span>
      <Badge label={srcCfg?.short || '?'} color={pos.source_color} />
    </div>
  )
}

export function PositionsTable() {
  const { positions } = useAppStore()
  const totalPnl = positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0)

  return (
    <div className="rounded-md border overflow-hidden"
      style={{ background: 'var(--color-slate-card)', borderColor: 'var(--color-border)' }}>
      <div className="px-3.5 py-2.5 border-b" style={{ borderColor: 'var(--color-border)' }}>
        <span className="text-[13px] font-semibold" style={{ color: 'var(--color-text-white)' }}>
          Open Positions ({positions.length})
        </span>
      </div>
      <div className="grid items-center gap-1 px-3 py-1.5 border-b text-[9px] uppercase tracking-wider"
        style={{
          gridTemplateColumns: '90px 36px 50px 80px 80px 90px 56px',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-ghost)',
        }}>
        <span>Symbol</span><span>Type</span><span>Qty</span><span>Avg</span>
        <span>Current</span><span>P&L</span><span>Source</span>
      </div>
      {positions.map(p => <PositionRow key={p.id} pos={p} />)}
      <div className="flex justify-end gap-4 px-3 py-2.5 border-t text-xs"
        style={{ borderColor: 'var(--color-border)' }}>
        <span style={{ color: 'var(--color-text-dim)' }}>Total Unrealized:</span>
        <span className="font-mono font-bold tabular-nums"
          style={{ color: totalPnl >= 0 ? 'var(--color-bull)' : 'var(--color-bear)' }}>
          {formatPnl(totalPnl)}
        </span>
      </div>
    </div>
  )
}
