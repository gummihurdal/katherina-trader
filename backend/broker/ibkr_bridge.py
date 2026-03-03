"""
KAT v2.0 — IBKR Bridge
Runs on your desktop alongside TWS/IB Gateway.
Syncs: Positions, P&L, Account → Supabase
Executes: Approved signals → IBKR orders
"""

import time
import json
import threading
import logging
from datetime import datetime, timezone
from decimal import Decimal

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("KAT-IBKR")

# ═══════════════════════════════════════════════════════════════
#  CONFIG — edit these or use .env
# ═══════════════════════════════════════════════════════════════
import os
from dotenv import load_dotenv
load_dotenv()

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "7497"))  # 7497=TWS paper, 4002=Gateway paper
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "10"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://palmswzrpquwemhfrvxs.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "30"))  # seconds
POLL_SIGNALS_INTERVAL = int(os.getenv("POLL_SIGNALS_INTERVAL", "5"))  # seconds
USER_ID = os.getenv("KAT_USER_ID", "5bca56a8-cc43-49f9-b3f7-69a78c11ef27")


# ═══════════════════════════════════════════════════════════════
#  IBKR WRAPPER
# ═══════════════════════════════════════════════════════════════
class KATWrapper(EWrapper):
    def __init__(self):
        super().__init__()
        self.account_values = {}
        self.positions = {}
        self.next_order_id = None
        self.order_statuses = {}
        self.connected = False

    def nextValidId(self, orderId):
        self.next_order_id = orderId
        self.connected = True
        log.info(f"✅ Connected to IBKR | Next order ID: {orderId}")

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        if errorCode in (2104, 2106, 2158, 2119):  # Market data info msgs
            return
        log.warning(f"IBKR [{errorCode}]: {errorString}")

    def accountSummary(self, reqId, account, tag, value, currency):
        self.account_values[tag] = {"value": value, "currency": currency}

    def accountSummaryEnd(self, reqId):
        log.info(f"📊 Account summary received ({len(self.account_values)} fields)")

    def position(self, account, contract, position, avgCost):
        key = contract.symbol
        if contract.secType == "FUT":
            key = f"@{contract.symbol}{contract.lastTradeDateOrContractMonth}"
        elif contract.secType == "OPT":
            key = f"{contract.symbol} {contract.strike}{contract.right[0]}"

        if position != 0:
            self.positions[key] = {
                "symbol": key,
                "sec_type": contract.secType,
                "quantity": int(position),
                "avg_cost": float(avgCost),
                "contract": contract,
                "exchange": contract.exchange,
                "currency": contract.currency,
            }
        elif key in self.positions:
            del self.positions[key]

    def positionEnd(self):
        log.info(f"📦 Positions: {len(self.positions)} open")

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, 
                    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        self.order_statuses[orderId] = {
            "status": status,
            "filled": filled,
            "remaining": remaining,
            "avg_fill_price": avgFillPrice,
        }
        log.info(f"📝 Order {orderId}: {status} (filled {filled}/{filled+remaining} @ {avgFillPrice})")

    def connectionClosed(self):
        self.connected = False
        log.error("❌ IBKR connection lost")


# ═══════════════════════════════════════════════════════════════
#  BRIDGE
# ═══════════════════════════════════════════════════════════════
class KATBridge:
    def __init__(self):
        self.wrapper = KATWrapper()
        self.client = EClient(self.wrapper)
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self._running = False

    # ── Connection ──
    def connect(self):
        log.info(f"🔌 Connecting to IBKR at {IBKR_HOST}:{IBKR_PORT} (client {IBKR_CLIENT_ID})...")
        self.client.connect(IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID)

        # Run client message loop in background thread
        thread = threading.Thread(target=self.client.run, daemon=True)
        thread.start()

        # Wait for connection
        for _ in range(30):
            if self.wrapper.connected:
                break
            time.sleep(0.5)

        if not self.wrapper.connected:
            log.error("❌ Failed to connect to IBKR. Is TWS/Gateway running?")
            return False

        return True

    # ── Account Sync ──
    def sync_account(self):
        """Pull account data from IBKR → push to Supabase."""
        if not self.wrapper.connected:
            return

        # Request account summary
        self.client.reqAccountSummary(
            9001, "All",
            "NetLiquidation,TotalCashValue,BuyingPower,UnrealizedPnL,RealizedPnL,GrossPositionValue"
        )
        time.sleep(2)
        self.client.cancelAccountSummary(9001)

        # Request positions
        self.client.reqPositions()
        time.sleep(2)
        self.client.cancelPositions()

        # Push to Supabase
        av = self.wrapper.account_values
        net_liq = float(av.get("NetLiquidation", {}).get("value", 0))
        cash = float(av.get("TotalCashValue", {}).get("value", 0))
        unrealized = float(av.get("UnrealizedPnL", {}).get("value", 0))

        if net_liq > 0:
            cash_pct = cash / net_liq if net_liq else 0

            # Upsert risk snapshot
            self.supabase.table("risk_snapshots").insert({
                "user_id": USER_ID,
                "portfolio_value": net_liq,
                "cash_pct": round(cash_pct, 4),
                "positions_count": len(self.wrapper.positions),
                "daily_pnl": unrealized,
                "daily_pnl_pct": round(unrealized / net_liq, 4) if net_liq else 0,
                "total_risk_pct": round(1 - cash_pct, 4),
                "weekly_pnl": 0,
                "weekly_pnl_pct": 0,
                "source_allocations": {},
            }).execute()

            log.info(f"💰 Account: ${net_liq:,.2f} | Cash: {cash_pct:.1%} | P&L: ${unrealized:,.2f}")

        # Sync positions to Supabase
        for sym, pos in self.wrapper.positions.items():
            asset_class = {"STK": "stock", "FUT": "future", "OPT": "option", "CASH": "forex"}.get(pos["sec_type"], "stock")
            self.supabase.table("positions").upsert({
                "user_id": USER_ID,
                "symbol": pos["symbol"],
                "asset_class": asset_class,
                "quantity": pos["quantity"],
                "avg_cost": pos["avg_cost"],
                "current_price": pos["avg_cost"],  # Updated via market data
                "unrealized_pnl": 0,
                "is_paper": IBKR_PORT in (7497, 4002),
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="user_id,symbol").execute()

        log.info(f"🔄 Synced {len(self.wrapper.positions)} positions to Supabase")

    # ── Signal Execution ──
    def poll_signals(self):
        """Check for approved signals that haven't been executed yet."""
        if not self.wrapper.connected:
            return

        # Get approved signals without a trade_id
        result = self.supabase.table("signals") \
            .select("*,signal_sources(name)") \
            .eq("user_id", USER_ID) \
            .eq("risk_approved", True) \
            .is_("trade_id", "null") \
            .is_("processed_at", "null") \
            .order("signal_time", desc=False) \
            .limit(10) \
            .execute()

        for sig in (result.data or []):
            self.execute_signal(sig)

    def execute_signal(self, sig):
        """Convert approved signal → IBKR order."""
        if self.wrapper.next_order_id is None:
            log.error("No order ID available")
            return

        order_id = self.wrapper.next_order_id
        self.wrapper.next_order_id += 1

        # Build contract
        contract = Contract()
        symbol = sig["symbol"]

        if sig["asset_class"] == "future":
            # Futures: @ESH6 → ES with expiry
            clean = symbol.lstrip("@")
            contract.secType = "FUT"
            contract.symbol = clean[:2] if len(clean) > 3 else clean
            contract.exchange = "CME"
            contract.currency = "USD"
        elif sig["asset_class"] == "option":
            contract.secType = "OPT"
            contract.symbol = symbol.split()[0]
            contract.exchange = "SMART"
            contract.currency = "USD"
        else:
            contract.secType = "STK"
            contract.symbol = symbol
            contract.exchange = "SMART"
            contract.currency = "USD"

        # Build order
        order = Order()
        action_map = {"buy": "BUY", "bto": "BUY", "btc": "BUY", "sell": "SELL", "sto": "SELL", "stc": "SELL"}
        order.action = action_map.get(sig["action"], "BUY")
        order.totalQuantity = sig["quantity"]

        if sig.get("limit_price"):
            order.orderType = "LMT"
            order.lmtPrice = float(sig["limit_price"])
        else:
            order.orderType = "MKT"

        order.eTradeOnly = False
        order.firmQuoteOnly = False
        order.tif = "DAY"

        # Place order
        log.info(f"🚀 EXECUTING: {order.action} {sig['quantity']} {symbol} @ {order.orderType} {getattr(order, 'lmtPrice', 'MKT')}")
        self.client.placeOrder(order_id, contract, order)

        # Create trade record
        source_name = sig.get("signal_sources", {}).get("name", "unknown")
        self.supabase.table("trades").insert({
            "user_id": USER_ID,
            "signal_id": sig["id"],
            "source_id": sig["source_id"],
            "asset_class": sig["asset_class"],
            "symbol": symbol,
            "side": order.action.lower(),
            "order_type": order.orderType.lower(),
            "quantity": sig["quantity"],
            "entry_price": sig.get("limit_price"),
            "stop_loss": sig.get("stop_loss"),
            "status": "submitted",
            "is_paper": IBKR_PORT in (7497, 4002),
            "risk_checks": sig.get("risk_checks", {}),
            "metadata": {"ibkr_order_id": order_id, "source": source_name},
        }).execute()

        # Mark signal as processed
        self.supabase.table("signals").update({
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", sig["id"]).execute()

        log.info(f"✅ Order {order_id} submitted for {symbol}")

        # Attach stop-loss if present
        if sig.get("stop_loss"):
            sl_order_id = self.wrapper.next_order_id
            self.wrapper.next_order_id += 1

            sl_order = Order()
            sl_order.action = "SELL" if order.action == "BUY" else "BUY"
            sl_order.totalQuantity = sig["quantity"]
            sl_order.orderType = "STP"
            sl_order.auxPrice = float(sig["stop_loss"])
            sl_order.eTradeOnly = False
            sl_order.firmQuoteOnly = False
            sl_order.tif = "GTC"

            self.client.placeOrder(sl_order_id, contract, sl_order)
            log.info(f"🛡️ Stop-loss {sl_order_id} placed at ${sig['stop_loss']}")

    # ── Main Loop ──
    def run(self):
        if not self.connect():
            return

        self._running = True
        log.info("═══════════════════════════════════════")
        log.info(" KAT IBKR BRIDGE — ONLINE")
        log.info(f" Mode: {'PAPER' if IBKR_PORT in (7497, 4002) else 'LIVE'}")
        log.info(f" Sync: every {SYNC_INTERVAL}s")
        log.info(f" Signals: polling every {POLL_SIGNALS_INTERVAL}s")
        log.info("═══════════════════════════════════════")

        last_sync = 0
        last_poll = 0

        try:
            while self._running:
                now = time.time()

                if now - last_sync >= SYNC_INTERVAL:
                    try:
                        self.sync_account()
                    except Exception as e:
                        log.error(f"Sync error: {e}")
                    last_sync = now

                if now - last_poll >= POLL_SIGNALS_INTERVAL:
                    try:
                        self.poll_signals()
                    except Exception as e:
                        log.error(f"Signal poll error: {e}")
                    last_poll = now

                time.sleep(1)

        except KeyboardInterrupt:
            log.info("🛑 Shutting down...")
        finally:
            self.client.disconnect()
            log.info("Disconnected from IBKR")


if __name__ == "__main__":
    bridge = KATBridge()
    bridge.run()
