interface StatCardProps {
  label: string
  value: string
  sub?: string
  color?: string
}

export function StatCard({ label, value, sub, color }: StatCardProps) {
  return (
    <div className="rounded-md border px-4 py-3 min-w-[140px] flex-1"
      style={{ background: 'var(--color-slate-card)', borderColor: 'var(--color-border)' }}>
      <div className="text-[10px] uppercase tracking-[0.1em] mb-1.5"
        style={{ color: 'var(--color-text-dim)' }}>
        {label}
      </div>
      <div className="text-xl font-bold font-mono tabular-nums leading-none"
        style={{ color: color || 'var(--color-text-white)' }}>
        {value}
      </div>
      {sub && (
        <div className="text-[11px] mt-1" style={{ color: 'var(--color-text-dim)' }}>
          {sub}
        </div>
      )}
    </div>
  )
}
