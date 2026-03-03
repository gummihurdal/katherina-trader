interface AllocationBarProps {
  label: string
  current: number
  max: number
  color?: string
}

export function AllocationBar({ label, current, max, color }: AllocationBarProps) {
  const ratio = max > 0 ? current / max : 0
  const barColor = color || (ratio > 0.9 ? 'var(--color-warn)' : ratio > 0.7 ? 'var(--color-arctic)' : 'var(--color-bull)')
  
  return (
    <div className="flex items-center gap-2.5 text-xs mb-1.5">
      <span className="w-24 truncate" style={{ color: 'var(--color-text)' }}>{label}</span>
      <div className="flex-1 h-1.5 rounded-full overflow-hidden border"
        style={{ background: 'var(--color-slate-deep)', borderColor: 'var(--color-border-dim)' }}>
        <div className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(ratio * 100, 100)}%`, background: barColor }} />
      </div>
      <span className="w-20 text-right font-mono text-[11px] tabular-nums"
        style={{ color: 'var(--color-text-dim)' }}>
        {(current * 100).toFixed(0)}% / {(max * 100).toFixed(0)}%
      </span>
    </div>
  )
}
