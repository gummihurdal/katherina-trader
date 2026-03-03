"""SignalStack webhook signal parser."""
from ..models import UnifiedSignal, SignalSource, AssetClass, ActionType, OrderType, Urgency

class SignalStackParser:
    def parse(self, payload: dict) -> UnifiedSignal:
        action = ActionType.BUY if payload.get("action", "buy").lower() == "buy" else ActionType.SELL
        ac_map = {"stock": AssetClass.STOCK, "option": AssetClass.OPTION,
            "future": AssetClass.FUTURE, "forex": AssetClass.FOREX, "crypto": AssetClass.CRYPTO}
        ac = ac_map.get(payload.get("class", "stock").lower(), AssetClass.STOCK)
        ot, lp, sp = OrderType.MARKET, None, None
        if payload.get("limit_price"):
            ot, lp = OrderType.LIMIT, float(payload["limit_price"])
        if payload.get("stop_price"):
            sp = float(payload["stop_price"])
            ot = OrderType.STOP_LIMIT if lp else OrderType.STOP
        symbol = payload.get("symbol", "")
        expiry, strike, pc = None, None, None
        if ac == AssetClass.OPTION and len(symbol) > 10:
            try:
                for i, c in enumerate(symbol):
                    if c.isdigit(): break
                ds = symbol[i:i+6]
                pc = "call" if symbol[i+6] == "C" else "put"
                strike = int(symbol[i+7:]) / 1000
                expiry = f"20{ds[:2]}-{ds[2:4]}-{ds[4:6]}"
            except (IndexError, ValueError):
                pass
        return UnifiedSignal(
            source=SignalSource.SIGNALSTACK, source_strategy_id="signalstack",
            source_strategy_name="SignalStack", action=action, asset_class=ac,
            symbol=symbol, quantity=int(payload.get("quantity", 0)),
            order_type=ot, limit_price=lp, stop_price=sp,
            expiry=expiry, strike=strike, put_call=pc)
