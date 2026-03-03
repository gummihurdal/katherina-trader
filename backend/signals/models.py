"""
KAT — Unified Signal Object
Every signal from every source is normalized to this format
before reaching the Guardian risk engine.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime
import uuid


class SignalSource(Enum):
    COLLECTIVE2 = "collective2"
    TRADERSPOST = "traderspost"
    TRADE_IDEAS = "trade_ideas"
    SIGNALSTACK = "signalstack"
    TELEGRAM = "telegram"
    INTERNAL_IRON_CONDOR = "internal_iron_condor"
    INTERNAL_MOMENTUM = "internal_momentum"
    INTERNAL_COVERED_CALLS = "internal_covered_calls"
    INTERNAL_DIVIDEND = "internal_dividend"
    MANUAL = "manual"

    @property
    def is_internal(self) -> bool:
        return self.value.startswith("internal_") or self == SignalSource.MANUAL


class AssetClass(Enum):
    STOCK = "stock"
    OPTION = "option"
    FUTURE = "future"
    FOREX = "forex"
    CRYPTO = "crypto"


class ActionType(Enum):
    BUY = "buy"
    SELL = "sell"
    BUY_TO_OPEN = "bto"
    SELL_TO_OPEN = "sto"
    BUY_TO_CLOSE = "btc"
    SELL_TO_CLOSE = "stc"

    CLOSING_ACTIONS = {"sell", "btc", "stc"}

    @property
    def is_opening(self) -> bool:
        return self.value not in {"sell", "btc", "stc"}

    @property
    def is_closing(self) -> bool:
        return self.value in {"sell", "btc", "stc"}


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class Urgency(Enum):
    IMMEDIATE = "immediate"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class SignalLeg:
    """A single leg of a multi-leg options trade."""
    action: ActionType
    symbol: str
    quantity: int
    expiry: Optional[str] = None
    strike: Optional[float] = None
    put_call: Optional[str] = None
    limit_price: Optional[float] = None


@dataclass
class UnifiedSignal:
    """
    The canonical signal format used throughout KAT.
    ALL signals — from any source — are converted to this format
    before reaching the Guardian risk engine.
    """

    # ── Identity ──
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: SignalSource = SignalSource.MANUAL
    source_strategy_id: str = ""
    source_strategy_name: str = ""

    # ── Trade Details ──
    action: ActionType = ActionType.BUY
    asset_class: AssetClass = AssetClass.STOCK
    symbol: str = ""
    quantity: int = 0
    order_type: OrderType = OrderType.MARKET

    # ── Pricing ──
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None

    # ── Risk Management ──
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # ── Options / Futures ──
    expiry: Optional[str] = None
    strike: Optional[float] = None
    put_call: Optional[str] = None
    legs: list = field(default_factory=list)

    # ── Metadata ──
    confidence: float = 0.0
    urgency: Urgency = Urgency.NORMAL
    notes: str = ""
    raw_payload: dict = field(default_factory=dict)

    # ── Timestamps ──
    signal_time: datetime = field(default_factory=datetime.utcnow)
    received_time: datetime = field(default_factory=datetime.utcnow)

    # ── Risk Engine (populated by Guardian) ──
    risk_approved: Optional[bool] = None
    risk_checks: dict = field(default_factory=dict)
    risk_rejection_reason: Optional[str] = None

    # ── Execution (populated by Execution Manager) ──
    trade_id: Optional[str] = None
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None

    def has_stop_loss(self) -> bool:
        return self.stop_loss is not None

    def to_dict(self) -> dict:
        """Serialize for database / API."""
        return {
            "id": self.id,
            "source": self.source.value,
            "source_strategy_id": self.source_strategy_id,
            "source_strategy_name": self.source_strategy_name,
            "action": self.action.value,
            "asset_class": self.asset_class.value,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "expiry": self.expiry,
            "strike": self.strike,
            "put_call": self.put_call,
            "confidence": self.confidence,
            "urgency": self.urgency.value,
            "notes": self.notes,
            "signal_time": self.signal_time.isoformat(),
            "received_time": self.received_time.isoformat(),
            "risk_approved": self.risk_approved,
            "risk_checks": self.risk_checks,
            "risk_rejection_reason": self.risk_rejection_reason,
        }

    def __str__(self) -> str:
        s = "✓" if self.risk_approved else ("✗" if self.risk_approved is False else "?")
        return (
            f"[{s}] {self.source.value} | {self.action.value.upper()} "
            f"{self.quantity} {self.symbol} ({self.asset_class.value}) "
            f"@ {self.limit_price or 'MKT'}"
        )
