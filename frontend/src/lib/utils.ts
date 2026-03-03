import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function formatCurrency(value: number, compact = false): string {
  if (compact && Math.abs(value) >= 1000) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: 'USD',
      notation: 'compact', maximumFractionDigits: 1,
    }).format(value)
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value)
}

export function formatPnl(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${formatCurrency(value)}`
}

export function formatPct(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', { hour12: false })
}

export function getSourceColor(source: string): string {
  const colors: Record<string, string> = {
    collective2: '#0ea5e9',
    traderspost: '#10b981',
    trade_ideas: '#f59e0b',
    signalstack: '#6b82a3',
    internal: '#a855f7',
    telegram: '#38bdf8',
    manual: '#94a8c4',
  }
  return colors[source] || '#6b82a3'
}

export function getAssetBadge(asset: string): string {
  const badges: Record<string, string> = {
    stock: 'STK', option: 'OPT', future: 'FUT', forex: 'FX', crypto: 'CRY',
  }
  return badges[asset] || asset.toUpperCase().slice(0, 3)
}

export function getActionColor(action: string): string {
  const bullish = ['buy', 'bto']
  const bearish = ['sell', 'stc']
  const neutral = ['sto', 'btc']
  if (bullish.includes(action)) return 'var(--color-bull)'
  if (bearish.includes(action)) return 'var(--color-bear)'
  if (neutral.includes(action)) return 'var(--color-arctic)'
  return 'var(--color-text)'
}
