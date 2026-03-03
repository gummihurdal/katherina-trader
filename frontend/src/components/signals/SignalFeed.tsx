import { useAppStore } from '@/stores/appStore'
import { Badge } from '@/components/shared/Badge'
import { formatTime, getActionColor, getAssetBadge } from '@/lib/utils'
import { SOURCE_CONFIG } from '@/lib/constants'
import type { Signal, SignalSourceName } from '@/types'

function SignalRow({ signal }: { signal: Signal }) {
  const sourceCfg = SOURCE_CONFIG[signal.source_name as keyof typeof SOURCE_CONFIG]
  const actionColor = getActionColor(signal.action)
  
  return (
    <div className="grid items-center gap-1.5 px-3 py-1.5 border-b font-mono text-xs"
      style={{
        gridTemplateColumns: '62px 48px 42px 36px 90px 50px 72px 1fr',
        borderColor: 'var(--color-border-dim)',
        background: signal.risk_approved === false ? 'var(--color-bear-glow)' : 'transparent',
      }}>
      <span className="text-[11px]" style={{ color: 'var(--color-text-dim)' }}>
        {formatTime(signal.received_at)}
      </span>
      <Badge label={sourceCfg?.short || '?'} color={signal.source_color} />
      <span className="font-bold" style={{ color: actionColor }}>
        {signal.action.toUpperCase()}
      </span>
      <Badge label={getAssetBadge(signal.asset_class)} small />
      <span className="font-medium truncate" style={{ color: 'var(--color-text-white)' }}>
        {signal.symbol}
      </span>
      <span style={{ color: 'var(--color-text-dim)' }}>{signal.quantity}</span>
      <span style={{ color: 'var(--color-text)' }}>
        {signal.limit_price ? `$${signal.limit_price.toLocaleString()}` : '—'}
      </span>
      {signal.risk_approved ? (
        <span className="text-[11px]" style={{ color: 'var(--color-bull)' }}>✓ APPROVED</span>
      ) : signal.risk_approved === false ? (
        <span className="text-[11px] truncate" style={{ color: 'var(--color-bear)' }}>
          ✗ {signal.risk_rejection_reason}
        </span>
      ) : (
        <span className="text-[11px]" style={{ color: 'var(--color-text-dim)' }}>⏳ PENDING</span>
      )}
    </div>
  )
}

export function SignalFeed() {
  const { signals } = useAppStore()
  const approved = signals.filter(s => s.risk_approved === true).length
  const rejected = signals.filter(s => s.risk_approved === false).length

  return (
    <div className="rounded-md border overflow-hidden"
      style={{ background: 'var(--color-slate-card)', borderColor: 'var(--color-border)' }}>
      
      {/* Header */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b"
        style={{ borderColor: 'var(--color-border)' }}>
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold" style={{ color: 'var(--color-text-white)' }}>
            Signal Feed
          </span>
          <span className="w-1.5 h-1.5 rounded-full" 
            style={{ background: 'var(--color-bull)', boxShadow: '0 0 6px var(--color-bull)', animation: 'pulse-glow 2s infinite' }} />
          <span className="text-[10px]" style={{ color: 'var(--color-text-dim)' }}>LIVE</span>
        </div>
        <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-dim)' }}>
          {approved} approved · {rejected} rejected
        </span>
      </div>
      
      {/* Column Headers */}
      <div className="grid items-center gap-1.5 px-3 py-1.5 border-b text-[9px] uppercase tracking-wider"
        style={{
          gridTemplateColumns: '62px 48px 42px 36px 90px 50px 72px 1fr',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-ghost)',
        }}>
        <span>Time</span><span>Src</span><span>Act</span><span>Type</span>
        <span>Symbol</span><span>Qty</span><span>Price</span><span>Status</span>
      </div>
      
      {/* Rows */}
      <div className="max-h-[440px] overflow-y-auto">
        {signals.map(s => <SignalRow key={s.id} signal={s} />)}
      </div>
    </div>
  )
}
