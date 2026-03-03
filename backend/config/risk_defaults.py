"""KAT — Risk Configuration Defaults"""
from dataclasses import dataclass

@dataclass
class RiskConfig:
    max_position_pct: float = 0.02
    max_portfolio_risk_pct: float = 0.10
    max_daily_loss_pct: float = 0.03
    max_weekly_loss_pct: float = 0.05
    max_correlation: float = 0.70
    max_single_stock_pct: float = 0.15
    max_options_pct: float = 0.30
    max_futures_margin_pct: float = 0.25
    min_cash_reserve_pct: float = 0.20
    require_stop_loss: bool = True
    max_concurrent_positions: int = 15
    max_signals_per_source_day: int = 20
    max_c2_allocation_pct: float = 0.30
    max_holly_allocation_pct: float = 0.20
    max_internal_allocation_pct: float = 0.40
    max_other_allocation_pct: float = 0.10
    default_stop_loss_pct: float = 0.02
    default_options_stop_pct: float = 0.50
    default_futures_stop_ticks: int = 20
