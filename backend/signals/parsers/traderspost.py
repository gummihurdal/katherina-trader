"""TradersPost webhook signal parser."""
from ..models import UnifiedSignal, SignalSource, AssetClass, ActionType, OrderType, Urgency

TP_ACTION = {"buy": ActionType.BUY, "sell": ActionType.SELL,
    "buy_to_open": ActionType.BUY_TO_OPEN, "sell_to_open": ActionType.SELL_TO_OPEN,
    "buy_to_close": ActionType.BUY_TO_CLOSE, "sell_to_close": ActionType.SELL_TO_CLOSE}

class TradersPostParser:
    def parse(self, payload: dict) -> UnifiedSignal:
        action = TP_ACTION.get(payload.get("action", "buy").lower(), ActionType.BUY)
        ac_map = {"stock": AssetClass.STOCK, "option": AssetClass.OPTION,
            "future": AssetClass.FUTURE, "forex": AssetClass.FOREX, "crypto": AssetClass.CRYPTO}
        ac = ac_map.get(payload.get("class", "").lower(), AssetClass.STOCK)
        ot, lp, sp = OrderType.MARKET, None, None
        if payload.get("limit_price") or payload.get("price"):
            ot, lp = OrderType.LIMIT, float(payload.get("limit_price") or payload["price"])
        if payload.get("stop_price"):
            sp = float(payload["stop_price"])
            ot = OrderType.STOP_LIMIT if lp else OrderType.STOP
        return UnifiedSignal(
            source=SignalSource.TRADERSPOST,
            source_strategy_id=payload.get("strategy_id", "tp"),
            source_strategy_name=payload.get("strategy_name", "TradersPost"),
            action=action, asset_class=ac, symbol=payload.get("ticker", ""),
            quantity=int(payload.get("quantity", 0)), order_type=ot,
            limit_price=lp, stop_price=sp,
            stop_loss=float(payload["stop"]) if payload.get("stop") else None,
            take_profit=float(payload["target"]) if payload.get("target") else None,
            confidence=0.7 if payload.get("sentiment") in ("bullish", "bearish") else 0.5,
            notes=payload.get("message", ""))
