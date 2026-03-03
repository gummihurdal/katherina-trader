export const SOURCE_CONFIG = {
  collective2: { label: 'Collective2', short: 'C2', color: '#0ea5e9' },
  traderspost: { label: 'TradersPost', short: 'TP', color: '#10b981' },
  trade_ideas: { label: 'Holly AI', short: 'HOLLY', color: '#f59e0b' },
  signalstack: { label: 'SignalStack', short: 'SS', color: '#6b82a3' },
  internal: { label: 'Internal', short: 'INT', color: '#a855f7' },
  telegram: { label: 'Telegram', short: 'TG', color: '#38bdf8' },
} as const

export const RISK_LIMITS = {
  maxPositionPct: 0.02,
  maxPortfolioRisk: 0.10,
  maxDailyLoss: 0.03,
  maxWeeklyLoss: 0.05,
  maxConcentration: 0.15,
  maxOptionsPct: 0.30,
  minCashReserve: 0.20,
  maxPositions: 15,
  maxSignalsPerSourceDay: 20,
} as const

export const TABS = [
  { id: 'signals' as const, label: 'SIGNAL HUB', shortcut: '1' },
  { id: 'positions' as const, label: 'POSITIONS', shortcut: '2' },
  { id: 'risk' as const, label: 'GUARDIAN', shortcut: '3' },
  { id: 'sources' as const, label: 'SOURCES', shortcut: '4' },
  { id: 'trades' as const, label: 'JOURNAL', shortcut: '5' },
] as const
