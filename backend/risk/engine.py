"""
KAT — Guardian Risk Engine
Absolute veto power over ALL signals from ALL sources.
10 sequential checks. Every check must pass.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from ..signals.models import UnifiedSignal, AssetClass, SignalSource, ActionType
from ..config.risk_defaults import RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class PortfolioState:
    """Current portfolio snapshot for risk calculations."""
    total_value: float = 0.0
    cash: float = 0.0
    positions: list = field(default_factory=list)
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    weekly_pnl: float = 0.0
    weekly_pnl_pct: float = 0.0
    source_allocations: dict = field(default_factory=dict)
    source_signal_counts: dict = field(default_factory=dict)


class Guardian:
    """
    The Guardian Risk Engine.
    Runs 10 sequential checks on every signal.
    ALL must pass. No exceptions. No overrides.
    """

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self._halted = False
        self._halted_sources: set = set()

    def evaluate(self, signal: UnifiedSignal, portfolio: PortfolioState) -> UnifiedSignal:
        """Run all 10 risk checks. Populates signal.risk_* fields."""

        # Global halt
        if self._halted:
            signal.risk_approved = False
            signal.risk_rejection_reason = "GLOBAL HALT ACTIVE"
            signal.risk_checks = {"halted": True}
            logger.critical(f"REJECTED (HALTED): {signal}")
            return signal

        # Source halt
        if signal.source.value in self._halted_sources:
            signal.risk_approved = False
            signal.risk_rejection_reason = f"Source {signal.source.value} is halted"
            signal.risk_checks = {"source_halted": True}
            logger.warning(f"REJECTED (SOURCE HALTED): {signal}")
            return signal

        # Run 10 checks
        checks = {}
        checks["1_capital"] = self._check_capital(signal, portfolio)
        checks["2_position_size"] = self._check_position_size(signal, portfolio)
        checks["3_portfolio_heat"] = self._check_portfolio_heat(signal, portfolio)
        checks["4_correlation"] = self._check_correlation(signal, portfolio)
        checks["5_concentration"] = self._check_concentration(signal, portfolio)
        checks["6_pnl_limits"] = self._check_pnl_limits(signal, portfolio)
        checks["7_cash_reserve"] = self._check_cash_reserve(signal, portfolio)
        checks["8_stop_loss"] = self._check_stop_loss(signal, portfolio)
        checks["9_source_allocation"] = self._check_source_allocation(signal, portfolio)
        checks["10_compliance"] = self._check_compliance(signal, portfolio)

        signal.risk_checks = checks

        # All must pass
        failed = [k for k, v in checks.items() if not v.get("passed", False)]
        if failed:
            signal.risk_approved = False
            signal.risk_rejection_reason = f"Failed: {', '.join(failed)}"
            logger.warning(f"REJECTED: {signal} | {signal.risk_rejection_reason}")
        else:
            signal.risk_approved = True
            logger.info(f"APPROVED: {signal}")

        return signal

    # ── CHECK 1: Capital Available ──
    def _check_capital(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        estimated_cost = (signal.limit_price or 0) * signal.quantity
        if signal.asset_class == AssetClass.OPTION:
            estimated_cost *= 100
        has_capital = portfolio.cash >= estimated_cost
        return {"passed": has_capital, "required": estimated_cost, "available": portfolio.cash}

    # ── CHECK 2: Position Size ──
    def _check_position_size(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        if portfolio.total_value == 0:
            return {"passed": True, "note": "no portfolio value"}
        estimated_cost = (signal.limit_price or 0) * signal.quantity
        if signal.asset_class == AssetClass.OPTION:
            estimated_cost *= 100
        pct = estimated_cost / portfolio.total_value
        passed = pct <= self.config.max_position_pct
        return {"passed": passed, "position_pct": round(pct, 4), "max": self.config.max_position_pct}

    # ── CHECK 3: Portfolio Heat ──
    def _check_portfolio_heat(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        # Heat = sum of capital at risk (position value × distance to stop) / total value
        total_risk = 0.0
        for pos in portfolio.positions:
            pos_val = pos.get("value", 0)
            stop_pct = pos.get("stop_distance_pct", 0.02)  # default 2% if unknown
            total_risk += pos_val * stop_pct
        new_trade_risk = (signal.limit_price or 0) * signal.quantity
        if signal.stop_loss and signal.limit_price:
            risk_per_unit = abs(signal.limit_price - signal.stop_loss)
            new_trade_risk = risk_per_unit * signal.quantity
        if signal.asset_class == AssetClass.OPTION:
            new_trade_risk *= 100
        heat_pct = (total_risk + new_trade_risk) / portfolio.total_value if portfolio.total_value else 0
        passed = heat_pct < self.config.max_portfolio_risk_pct
        return {"passed": passed, "current_risk_pct": round(heat_pct, 4)}

    # ── CHECK 4: Correlation ──
    def _check_correlation(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        same_symbol = any(p.get("symbol") == signal.symbol for p in portfolio.positions)
        is_closing = signal.action in (ActionType.SELL, ActionType.BUY_TO_CLOSE, ActionType.SELL_TO_CLOSE)
        return {"passed": not same_symbol or is_closing, "same_symbol_held": same_symbol}

    # ── CHECK 5: Concentration ──
    def _check_concentration(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        if portfolio.total_value == 0:
            return {"passed": True}
        symbol_exposure = sum(
            abs(p.get("value", 0)) for p in portfolio.positions
            if p.get("symbol") == signal.symbol
        )
        estimated_add = (signal.limit_price or 0) * signal.quantity
        total_pct = (symbol_exposure + estimated_add) / portfolio.total_value
        passed = total_pct <= self.config.max_single_stock_pct
        return {"passed": passed, "concentration_pct": round(total_pct, 4)}

    # ── CHECK 6: Daily/Weekly P&L ──
    def _check_pnl_limits(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        daily_ok = abs(portfolio.daily_pnl_pct) < self.config.max_daily_loss_pct
        weekly_ok = abs(portfolio.weekly_pnl_pct) < self.config.max_weekly_loss_pct
        if not daily_ok:
            self.halt_all("Daily loss limit breached")
        if not weekly_ok:
            self.halt_all("Weekly loss limit breached")
        return {"passed": daily_ok and weekly_ok,
                "daily_pnl_pct": portfolio.daily_pnl_pct,
                "weekly_pnl_pct": portfolio.weekly_pnl_pct}

    # ── CHECK 7: Cash Reserve ──
    def _check_cash_reserve(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        if portfolio.total_value == 0:
            return {"passed": True}
        estimated_cost = (signal.limit_price or 0) * signal.quantity
        remaining_cash_pct = (portfolio.cash - estimated_cost) / portfolio.total_value
        passed = remaining_cash_pct >= self.config.min_cash_reserve_pct
        return {"passed": passed, "remaining_cash_pct": round(remaining_cash_pct, 4)}

    # ── CHECK 8: Stop Loss ──
    def _check_stop_loss(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        if not self.config.require_stop_loss:
            return {"passed": True}
        is_closing = signal.action in (ActionType.SELL, ActionType.BUY_TO_CLOSE, ActionType.SELL_TO_CLOSE)
        if is_closing:
            return {"passed": True, "note": "closing trade"}
        has_sl = signal.stop_loss is not None
        if not has_sl and signal.limit_price:
            # Auto-add default stop loss
            if signal.asset_class == AssetClass.OPTION:
                signal.stop_loss = signal.limit_price * (1 - self.config.default_options_stop_pct)
            else:
                signal.stop_loss = signal.limit_price * (1 - self.config.default_stop_loss_pct)
            has_sl = True
        return {"passed": has_sl, "stop_loss": signal.stop_loss, "auto_added": signal.stop_loss is not None and not has_sl}

    # ── CHECK 9: Source Allocation ──
    def _check_source_allocation(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        source_name = signal.source.value
        current_alloc = portfolio.source_allocations.get(source_name, 0)
        max_alloc = self._get_max_allocation(signal.source)
        signal_count = portfolio.source_signal_counts.get(source_name, 0)
        count_ok = signal_count < self.config.max_signals_per_source_day
        alloc_ok = current_alloc < max_alloc
        if not count_ok:
            self.halt_source(source_name, "Signal flood detected")
        return {"passed": alloc_ok and count_ok,
                "current_alloc": current_alloc, "max_alloc": max_alloc,
                "signals_today": signal_count}

    # ── CHECK 10: Compliance ──
    def _check_compliance(self, signal: UnifiedSignal, portfolio: PortfolioState) -> dict:
        restricted = []  # TODO: Load from config (SNB restricted list)
        is_restricted = signal.symbol in restricted
        return {"passed": not is_restricted, "restricted": is_restricted}

    def _get_max_allocation(self, source: SignalSource) -> float:
        if source == SignalSource.COLLECTIVE2:
            return self.config.max_c2_allocation_pct
        if source == SignalSource.TRADE_IDEAS:
            return self.config.max_holly_allocation_pct
        if source.is_internal:
            return self.config.max_internal_allocation_pct
        return self.config.max_other_allocation_pct

    # ── Circuit Breakers ──
    def halt_all(self, reason: str):
        self._halted = True
        logger.critical(f"🚨 GLOBAL HALT: {reason}")

    def halt_source(self, source_name: str, reason: str):
        self._halted_sources.add(source_name)
        logger.warning(f"⚠️ SOURCE HALT [{source_name}]: {reason}")

    def resume_all(self):
        self._halted = False
        logger.info("✅ Global halt lifted")

    def resume_source(self, source_name: str):
        self._halted_sources.discard(source_name)
        logger.info(f"✅ Source resumed: {source_name}")

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halted_sources(self) -> frozenset:
        return frozenset(self._halted_sources)
