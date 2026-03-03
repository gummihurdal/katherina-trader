import { useEffect } from 'react'
import { useAppStore } from '@/stores/appStore'
import { formatCurrency, formatPnl } from '@/lib/utils'

export function Header() {
  const { risk, positions, isHalted, isPaper, toggleHalt, time, setTime } = useAppStore()

  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(interval)
  }, [setTime])

  const totalPnl = positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0)

  return (
    <header className="flex items-center justify-between px-5 py-2.5 border-b"
      style={{ background: 'var(--color-slate-card)', borderColor: 'var(--color-border)' }}>
      
      {/* Left: Logo + Status */}
      <div className="flex items-center gap-3.5">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md flex items-center justify-center text-sm font-black text-white"
            style={{ background: 'linear-gradient(135deg, #0ea5e9, #a855f7)' }}>
            K
          </div>
          <div>
            <div className="text-sm font-bold tracking-wider" style={{ color: 'var(--color-text-white)' }}>
              KATHERINA
            </div>
            <div className="text-[9px] tracking-[0.2em] -mt-0.5" style={{ color: 'var(--color-arctic)' }}>
              AUTONOMOUS TRADER v2.0
            </div>
          </div>
        </div>
        
        <div className="text-[10px] font-bold px-2.5 py-1 rounded tracking-wider border"
          style={{
            background: isHalted ? 'var(--color-bear-dim)' : 'var(--color-bull-dim)',
            color: isHalted ? 'var(--color-bear)' : 'var(--color-bull)',
            borderColor: isHalted ? 'rgba(239,68,68,0.3)' : 'rgba(16,185,129,0.3)',
          }}>
          {isHalted ? '⏹ HALTED' : isPaper ? '● PAPER' : '● LIVE'}
        </div>
      </div>

      {/* Right: Portfolio + Clock + Kill Switch */}
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-text-dim)' }}>Portfolio</div>
          <div className="text-base font-bold font-mono tabular-nums" style={{ color: 'var(--color-text-white)' }}>
            {formatCurrency(risk.portfolio_value)}
          </div>
        </div>
        
        <div className="w-px h-7" style={{ background: 'var(--color-border)' }} />
        
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-text-dim)' }}>Day P&L</div>
          <div className="text-base font-bold font-mono tabular-nums"
            style={{ color: totalPnl >= 0 ? 'var(--color-bull)' : 'var(--color-bear)' }}>
            {formatPnl(totalPnl)}
          </div>
        </div>
        
        <div className="w-px h-7" style={{ background: 'var(--color-border)' }} />
        
        <div className="font-mono text-xs tabular-nums" style={{ color: 'var(--color-text-dim)' }}>
          {time.toLocaleTimeString('en-US', { hour12: false })}
        </div>
        
        <button onClick={toggleHalt}
          className="text-[10px] font-bold px-3.5 py-1.5 rounded tracking-wider text-white border-none cursor-pointer transition-all hover:brightness-110"
          style={{
            background: isHalted ? 'var(--color-bull)' : 'var(--color-bear)',
            boxShadow: isHalted ? '0 0 16px var(--color-bull-glow)' : '0 0 16px var(--color-bear-glow)',
          }}>
          {isHalted ? 'RESUME' : 'KILL SWITCH'}
        </button>
      </div>
    </header>
  )
}
