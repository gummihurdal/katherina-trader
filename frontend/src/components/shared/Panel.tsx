import type { ReactNode } from 'react'

interface PanelProps {
  title?: string
  titleRight?: ReactNode
  children: ReactNode
  className?: string
  noPadding?: boolean
}

export function Panel({ title, titleRight, children, className = '', noPadding }: PanelProps) {
  return (
    <div className={`rounded-md border overflow-hidden ${className}`}
      style={{ background: 'var(--color-slate-card)', borderColor: 'var(--color-border)' }}>
      {title && (
        <div className="flex items-center justify-between px-3.5 py-2.5 border-b"
          style={{ borderColor: 'var(--color-border)' }}>
          <span className="text-[13px] font-semibold tracking-wide"
            style={{ color: 'var(--color-text-white)' }}>
            {title}
          </span>
          {titleRight}
        </div>
      )}
      <div className={noPadding ? '' : 'p-3.5'}>
        {children}
      </div>
    </div>
  )
}
