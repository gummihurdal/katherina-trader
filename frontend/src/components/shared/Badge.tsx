interface BadgeProps {
  label: string
  color?: string
  small?: boolean
}

export function Badge({ label, color, small }: BadgeProps) {
  return (
    <span className={`inline-flex items-center justify-center rounded font-mono font-semibold tracking-wider ${small ? 'text-[8px] px-1 py-px' : 'text-[9px] px-1.5 py-0.5'}`}
      style={{
        color: color || 'var(--color-text-dim)',
        background: color ? `${color}18` : 'var(--color-slate-hover)',
      }}>
      {label}
    </span>
  )
}
