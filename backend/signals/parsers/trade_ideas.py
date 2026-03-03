"""Trade Ideas Holly AI signal parser."""
from ..models import UnifiedSignal, SignalSource, AssetClass, ActionType, OrderType, Urgency

class TradeIdeasParser:
    def parse(self, payload: dict) -> UnifiedSignal:
        action = ActionType.BUY if "buy" in payload.get("action", "buy").lower() else ActionType.SELL
        return UnifiedSignal(
            source=SignalSource.TRADE_IDEAS,
            source_strategy_id=payload.get("strategy", "holly_ai"),
            source_strategy_name=payload.get("strategy_name", "Holly AI"),
            action=action, asset_class=AssetClass.STOCK,
            symbol=payload.get("symbol", payload.get("ticker", "")),
            quantity=int(payload.get("quantity", payload.get("shares", 0))),
            order_type=OrderType.LIMIT if payload.get("entry") else OrderType.MARKET,
            limit_price=float(payload["entry"]) if payload.get("entry") else None,
            stop_loss=float(payload["stop"]) if payload.get("stop") else None,
            take_profit=float(payload["target"]) if payload.get("target") else None,
            confidence=float(payload.get("confidence", 0.68)),
            urgency=Urgency.IMMEDIATE,
            notes=f"Holly: {payload.get('strategy', '?')}")
