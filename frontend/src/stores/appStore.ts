import { create } from 'zustand'
import type { TabId, SignalSource, Signal, Position, RiskSnapshot, RiskCheck } from '@/types'

interface AppState {
  // UI
  activeTab: TabId
  setActiveTab: (tab: TabId) => void
  
  // System
  isLive: boolean
  isPaper: boolean
  isHalted: boolean
  haltedSources: Set<string>
  toggleHalt: () => void
  haltSource: (source: string) => void
  resumeSource: (source: string) => void
  
  // Data
  sources: SignalSource[]
  signals: Signal[]
  positions: Position[]
  risk: RiskSnapshot
  riskChecks: RiskCheck[]
  
  // Clock
  time: Date
  setTime: (t: Date) => void
}

// ── Mock Data (until Supabase connected) ──
const MOCK_SOURCES: SignalSource[] = [
  { id: 's1', name: 'collective2', display_name: 'Collective2', source_type: 'api_poll', is_active: true, is_paper: true, max_allocation_pct: 0.30, current_allocation_pct: 0.23, total_signals: 847, approved_signals: 612, rejected_signals: 235, total_pnl: 14230, win_count: 428, loss_count: 184, status: 'connected', win_rate: 72, signals_today: 4, pnl_mtd: 2340, color: '#0ea5e9' },
  { id: 's2', name: 'traderspost', display_name: 'TradersPost', source_type: 'webhook', is_active: true, is_paper: true, max_allocation_pct: 0.20, current_allocation_pct: 0.12, total_signals: 312, approved_signals: 203, rejected_signals: 109, total_pnl: 4820, win_count: 132, loss_count: 71, status: 'connected', win_rate: 65, signals_today: 2, pnl_mtd: 580, color: '#10b981' },
  { id: 's3', name: 'trade_ideas', display_name: 'Holly AI', source_type: 'webhook', is_active: true, is_paper: true, max_allocation_pct: 0.20, current_allocation_pct: 0.18, total_signals: 1240, approved_signals: 843, rejected_signals: 397, total_pnl: 8940, win_count: 573, loss_count: 270, status: 'connected', win_rate: 68, signals_today: 6, pnl_mtd: 1190, color: '#f59e0b' },
  { id: 's4', name: 'signalstack', display_name: 'SignalStack', source_type: 'webhook', is_active: false, is_paper: true, max_allocation_pct: 0.10, current_allocation_pct: 0, total_signals: 0, approved_signals: 0, rejected_signals: 0, total_pnl: 0, win_count: 0, loss_count: 0, status: 'standby', win_rate: 0, signals_today: 0, pnl_mtd: 0, color: '#6b82a3' },
  { id: 's5', name: 'internal', display_name: 'Internal Strategies', source_type: 'internal', is_active: true, is_paper: true, max_allocation_pct: 0.40, current_allocation_pct: 0.28, total_signals: 523, approved_signals: 371, rejected_signals: 152, total_pnl: 11620, win_count: 263, loss_count: 108, status: 'active', win_rate: 71, signals_today: 3, pnl_mtd: 920, color: '#a855f7' },
]

const MOCK_SIGNALS: Signal[] = [
  { id: 'sig1', source_id: 's1', source_strategy_id: 'c2_94679', source_strategy_name: 'ES Momentum Pro', action: 'buy', asset_class: 'future', symbol: '@ESH6', quantity: 2, order_type: 'limit', limit_price: 5421.50, stop_loss: 5400.00, take_profit: 5460.00, risk_approved: true, risk_rejection_reason: null, risk_checks: {}, confidence: 0.82, urgency: 'normal', notes: '', received_at: new Date(Date.now() - 120000).toISOString(), source_name: 'collective2', source_color: '#0ea5e9' },
  { id: 'sig2', source_id: 's3', source_strategy_id: 'holly_grail', source_strategy_name: 'Holly Grail', action: 'buy', asset_class: 'stock', symbol: 'NVDA', quantity: 15, order_type: 'limit', limit_price: 892.30, stop_loss: 875.00, take_profit: 920.00, risk_approved: true, risk_rejection_reason: null, risk_checks: {}, confidence: 0.74, urgency: 'immediate', notes: '', received_at: new Date(Date.now() - 240000).toISOString(), source_name: 'trade_ideas', source_color: '#f59e0b' },
  { id: 'sig3', source_id: 's5', source_strategy_id: 'iron_condor', source_strategy_name: 'Iron Condor TSLA', action: 'sto', asset_class: 'option', symbol: 'TSLA IC 240/250/270/280', quantity: 1, order_type: 'limit', limit_price: 8.40, stop_loss: null, take_profit: null, risk_approved: true, risk_rejection_reason: null, risk_checks: {}, confidence: 0.71, urgency: 'normal', notes: '40 DTE', received_at: new Date(Date.now() - 360000).toISOString(), source_name: 'internal', source_color: '#a855f7' },
  { id: 'sig4', source_id: 's1', source_strategy_id: 'c2_swing', source_strategy_name: 'C2 Swing Alpha', action: 'sell', asset_class: 'stock', symbol: 'META', quantity: 20, order_type: 'market', limit_price: 612.40, stop_loss: 625.00, take_profit: 590.00, risk_approved: false, risk_rejection_reason: 'Check 5: Concentration >15%', risk_checks: {}, confidence: 0.65, urgency: 'normal', notes: '', received_at: new Date(Date.now() - 480000).toISOString(), source_name: 'collective2', source_color: '#0ea5e9' },
  { id: 'sig5', source_id: 's2', source_strategy_id: 'tv_momentum', source_strategy_name: 'TV Momentum', action: 'buy', asset_class: 'stock', symbol: 'AMD', quantity: 25, order_type: 'limit', limit_price: 178.50, stop_loss: 172.00, take_profit: 190.00, risk_approved: true, risk_rejection_reason: null, risk_checks: {}, confidence: 0.68, urgency: 'normal', notes: 'MACD cross', received_at: new Date(Date.now() - 600000).toISOString(), source_name: 'traderspost', source_color: '#10b981' },
  { id: 'sig6', source_id: 's3', source_strategy_id: 'holly_20', source_strategy_name: 'Holly 2.0', action: 'buy', asset_class: 'stock', symbol: 'AAPL', quantity: 10, order_type: 'limit', limit_price: 241.20, stop_loss: 235.00, take_profit: 252.00, risk_approved: true, risk_rejection_reason: null, risk_checks: {}, confidence: 0.72, urgency: 'immediate', notes: '', received_at: new Date(Date.now() - 780000).toISOString(), source_name: 'trade_ideas', source_color: '#f59e0b' },
  { id: 'sig7', source_id: 's5', source_strategy_id: 'momentum', source_strategy_name: 'Momentum Scanner', action: 'buy', asset_class: 'stock', symbol: 'MSFT', quantity: 8, order_type: 'limit', limit_price: 432.10, stop_loss: 424.00, take_profit: 445.00, risk_approved: true, risk_rejection_reason: null, risk_checks: {}, confidence: 0.69, urgency: 'normal', notes: 'RSI bounce', received_at: new Date(Date.now() - 900000).toISOString(), source_name: 'internal', source_color: '#a855f7' },
  { id: 'sig8', source_id: 's1', source_strategy_id: 'c2_opts', source_strategy_name: 'C2 Options Flow', action: 'bto', asset_class: 'option', symbol: 'SPY 550C 03/21', quantity: 3, order_type: 'limit', limit_price: 12.40, stop_loss: 6.20, take_profit: 18.00, risk_approved: false, risk_rejection_reason: 'Check 5: Options allocation >30%', risk_checks: {}, confidence: 0.58, urgency: 'normal', notes: '', received_at: new Date(Date.now() - 1080000).toISOString(), source_name: 'collective2', source_color: '#0ea5e9' },
  { id: 'sig9', source_id: 's3', source_strategy_id: 'holly_neo', source_strategy_name: 'Holly Neo', action: 'sell', asset_class: 'stock', symbol: 'GOOGL', quantity: 12, order_type: 'limit', limit_price: 178.90, stop_loss: 185.00, take_profit: 170.00, risk_approved: true, risk_rejection_reason: null, risk_checks: {}, confidence: 0.66, urgency: 'normal', notes: '', received_at: new Date(Date.now() - 1260000).toISOString(), source_name: 'trade_ideas', source_color: '#f59e0b' },
  { id: 'sig10', source_id: 's2', source_strategy_id: 'nq_scalper', source_strategy_name: 'NQ Scalper', action: 'buy', asset_class: 'future', symbol: '@NQM6', quantity: 1, order_type: 'limit', limit_price: 19850.00, stop_loss: 19800.00, take_profit: 19920.00, risk_approved: true, risk_rejection_reason: null, risk_checks: {}, confidence: 0.77, urgency: 'immediate', notes: '', received_at: new Date(Date.now() - 1440000).toISOString(), source_name: 'traderspost', source_color: '#10b981' },
]

const MOCK_POSITIONS: Position[] = [
  { id: 'p1', source_id: 's3', symbol: 'NVDA', asset_class: 'stock', quantity: 15, avg_cost: 892.30, current_price: 898.40, unrealized_pnl: 91.50, stop_loss: 875.00, is_paper: true, source_name: 'trade_ideas', source_color: '#f59e0b', pnl_pct: 0.68 },
  { id: 'p2', source_id: 's1', symbol: '@ESH6', asset_class: 'future', quantity: 2, avg_cost: 5421.50, current_price: 5434.25, unrealized_pnl: 637.50, stop_loss: 5400.00, is_paper: true, source_name: 'collective2', source_color: '#0ea5e9', pnl_pct: 0.24 },
  { id: 'p3', source_id: 's5', symbol: 'TSLA IC', asset_class: 'option', quantity: 1, avg_cost: 8.40, current_price: 7.20, unrealized_pnl: 120.00, stop_loss: null, is_paper: true, source_name: 'internal', source_color: '#a855f7', pnl_pct: 14.3 },
  { id: 'p4', source_id: 's2', symbol: 'AMD', asset_class: 'stock', quantity: 25, avg_cost: 178.50, current_price: 180.10, unrealized_pnl: 40.00, stop_loss: 172.00, is_paper: true, source_name: 'traderspost', source_color: '#10b981', pnl_pct: 0.90 },
  { id: 'p5', source_id: 's3', symbol: 'AAPL', asset_class: 'stock', quantity: 10, avg_cost: 241.20, current_price: 240.80, unrealized_pnl: -4.00, stop_loss: 235.00, is_paper: true, source_name: 'trade_ideas', source_color: '#f59e0b', pnl_pct: -0.17 },
  { id: 'p6', source_id: 's5', symbol: 'MSFT', asset_class: 'stock', quantity: 8, avg_cost: 432.10, current_price: 435.60, unrealized_pnl: 28.00, stop_loss: 424.00, is_paper: true, source_name: 'internal', source_color: '#a855f7', pnl_pct: 0.81 },
  { id: 'p7', source_id: 's2', symbol: '@NQM6', asset_class: 'future', quantity: 1, avg_cost: 19850.00, current_price: 19872.50, unrealized_pnl: 450.00, stop_loss: 19800.00, is_paper: true, source_name: 'traderspost', source_color: '#10b981', pnl_pct: 0.11 },
]

const MOCK_RISK: RiskSnapshot = {
  portfolio_value: 96420, total_risk_pct: 0.072,
  daily_pnl: 1363, daily_pnl_pct: 0.014,
  weekly_pnl: 2840, weekly_pnl_pct: 0.028,
  cash_pct: 0.251, positions_count: 7,
  source_allocations: { collective2: 0.23, traderspost: 0.12, trade_ideas: 0.18, internal: 0.28 },
}

const MOCK_RISK_CHECKS: RiskCheck[] = [
  { name: 'Capital', status: 'pass', value: '$48,230 available' },
  { name: 'Position Size', status: 'pass', value: 'Max 1.8% (limit 2%)' },
  { name: 'Portfolio Heat', status: 'pass', value: '7.2% (limit 10%)' },
  { name: 'Correlation', status: 'pass', value: 'Max pair 0.42 (limit 0.70)' },
  { name: 'Concentration', status: 'warn', value: 'NVDA at 13.9% (limit 15%)' },
  { name: 'Daily P&L', status: 'pass', value: '+1.4% ($1,363)' },
  { name: 'Cash Reserve', status: 'pass', value: '25.1% (min 20%)' },
  { name: 'Stop-Loss', status: 'pass', value: 'All positions covered' },
  { name: 'Source Alloc', status: 'pass', value: 'All within limits' },
  { name: 'Compliance', status: 'pass', value: 'No restricted symbols' },
]

export const useAppStore = create<AppState>((set) => ({
  activeTab: 'signals',
  setActiveTab: (tab) => set({ activeTab: tab }),
  isLive: false,
  isPaper: true,
  isHalted: false,
  haltedSources: new Set(),
  toggleHalt: () => set((s) => ({ isHalted: !s.isHalted })),
  haltSource: (source) => set((s) => {
    const next = new Set(s.haltedSources)
    next.add(source)
    return { haltedSources: next }
  }),
  resumeSource: (source) => set((s) => {
    const next = new Set(s.haltedSources)
    next.delete(source)
    return { haltedSources: next }
  }),
  sources: MOCK_SOURCES,
  signals: MOCK_SIGNALS,
  positions: MOCK_POSITIONS,
  risk: MOCK_RISK,
  riskChecks: MOCK_RISK_CHECKS,
  time: new Date(),
  setTime: (t) => set({ time: t }),
}))
