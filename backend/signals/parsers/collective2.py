"""Collective2 API signal parser."""
from datetime import datetime
from ..models import UnifiedSignal, SignalSource, AssetClass, ActionType, OrderType, Urgency

C2_ACTION = {"BTO": ActionType.BUY_TO_OPEN, "STO": ActionType.SELL_TO_OPEN,
    "BTC": ActionType.BUY_TO_CLOSE, "STC": ActionType.SELL_TO_CLOSE,
    "BUY": ActionType.BUY, "SELL": ActionType.SELL, "SSHORT": ActionType.SELL}
C2_ASSET = {"stock": AssetClass.STOCK, "option": AssetClass.OPTION,
    "future": AssetClass.FUTURE, "forex": AssetClass.FOREX}

class C2Parser:
    def parse(self, payload: dict) -> UnifiedSignal:
        sig = payload.get("signal", payload)
        action = C2_ACTION.get(sig.get("action", "BUY").upper(), ActionType.BUY)
        asset = C2_ASSET.get(sig.get("typeofsymbol", "stock").lower(), AssetClass.STOCK)
        ot, lp, sp = OrderType.MARKET, None, None
        if sig.get("limit"):
            ot, lp = OrderType.LIMIT, float(sig["limit"])
        if sig.get("stop"):
            sp = float(sig["stop"])
            ot = OrderType.STOP_LIMIT if lp else OrderType.STOP
        return UnifiedSignal(
            source=SignalSource.COLLECTIVE2,
            source_strategy_id=f"c2_{payload.get('systemid', '?')}",
            source_strategy_name=payload.get("systemname", "C2 Strategy"),
            action=action, asset_class=asset, symbol=sig.get("symbol", ""),
            quantity=int(sig.get("quant", 0)), order_type=ot, limit_price=lp,
            stop_price=sp, expiry=sig.get("expir"),
            strike=float(sig["strike"]) if sig.get("strike") else None,
            put_call=sig.get("putcall"), urgency=Urgency.NORMAL,
            notes=f"C2 system {payload.get('systemid', '?')}")
