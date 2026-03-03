"""Telegram signal message parser."""
import re
from ..models import UnifiedSignal, SignalSource, AssetClass, ActionType, OrderType, Urgency

class TelegramParser:
    def parse(self, payload: dict) -> UnifiedSignal:
        text = payload.get("text", "")
        action = ActionType.BUY if any(w in text.upper() for w in ["BUY", "LONG", "CALL"]) else ActionType.SELL
        sym = re.search(r'[\$#]([A-Z]{1,5})', text.upper())
        symbol = sym.group(1) if sym else ""
        entry = self._price(text, ["entry", "buy at", "sell at", "price"])
        stop = self._price(text, ["sl", "stop", "stop loss"])
        target = self._price(text, ["tp", "target", "take profit"])
        return UnifiedSignal(
            source=SignalSource.TELEGRAM, source_strategy_id=payload.get("channel_id", "tg"),
            source_strategy_name=payload.get("channel_name", "Telegram"),
            action=action, asset_class=AssetClass.STOCK, symbol=symbol, quantity=0,
            order_type=OrderType.LIMIT if entry else OrderType.MARKET, limit_price=entry,
            stop_loss=stop, take_profit=target, confidence=0.5,
            notes=f"TG: {text[:200]}")

    def _price(self, text, kws):
        for kw in kws:
            m = re.search(rf'{kw}[:\s]*\$?([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: return float(m.group(1).replace(",", ""))
        return None
