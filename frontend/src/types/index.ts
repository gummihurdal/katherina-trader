// ── KAT Type System ──

export type SignalSourceName = 'collective2' | 'traderspost' | 'trade_ideas' | 'signalstack' | 'telegram' | 'internal';
export type AssetClass = 'stock' | 'option' | 'future' | 'forex' | 'crypto';
export type ActionType = 'buy' | 'sell' | 'bto' | 'sto' | 'btc' | 'stc';
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit';
export type Urgency = 'immediate' | 'normal' | 'low';
export type TradeStatus = 'pending' | 'open' | 'partial' | 'closed' | 'cancelled' | 'rejected';
export type SourceStatus = 'connected' | 'active' | 'standby' | 'error' | 'halted';
export type Severity = 'info' | 'warning' | 'critical';

export interface SignalSource {
  id: string;
  name: SignalSourceName;
  display_name: string;
  source_type: 'api_poll' | 'webhook' | 'internal';
  is_active: boolean;
  is_paper: boolean;
  max_allocation_pct: number;
  current_allocation_pct: number;
  total_signals: number;
  approved_signals: number;
  rejected_signals: number;
  total_pnl: number;
  win_count: number;
  loss_count: number;
  // Derived
  status: SourceStatus;
  win_rate: number;
  signals_today: number;
  pnl_mtd: number;
  color: string;
}

export interface Signal {
  id: string;
  source_id: string;
  source_strategy_id: string;
  source_strategy_name: string;
  action: ActionType;
  asset_class: AssetClass;
  symbol: string;
  quantity: number;
  order_type: OrderType;
  limit_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_approved: boolean | null;
  risk_rejection_reason: string | null;
  risk_checks: Record<string, any>;
  confidence: number;
  urgency: Urgency;
  notes: string;
  received_at: string;
  // Derived
  source_name?: SignalSourceName;
  source_color?: string;
}

export interface Trade {
  id: string;
  source_id: string;
  signal_id: string | null;
  asset_class: AssetClass;
  symbol: string;
  side: 'long' | 'short';
  quantity: number;
  entry_price: number | null;
  exit_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  status: TradeStatus;
  pnl: number | null;
  pnl_pct: number | null;
  fees: number;
  is_paper: boolean;
  opened_at: string | null;
  closed_at: string | null;
}

export interface Position {
  id: string;
  source_id: string;
  symbol: string;
  asset_class: AssetClass;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  unrealized_pnl: number | null;
  stop_loss: number | null;
  is_paper: boolean;
  // Derived
  source_name?: SignalSourceName;
  source_color?: string;
  pnl_pct?: number;
}

export interface RiskSnapshot {
  portfolio_value: number;
  total_risk_pct: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  weekly_pnl: number;
  weekly_pnl_pct: number;
  cash_pct: number;
  positions_count: number;
  source_allocations: Record<string, number>;
}

export interface RiskCheck {
  name: string;
  status: 'pass' | 'warn' | 'fail';
  value: string;
}

export interface Alert {
  id: string;
  type: string;
  title: string;
  message: string;
  severity: Severity;
  is_read: boolean;
  created_at: string;
}

// ── UI Types ──
export type TabId = 'signals' | 'positions' | 'risk' | 'sources' | 'trades';
