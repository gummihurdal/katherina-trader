"""
KAT v2.0 — Signal Test Harness
Sends realistic test signals to KAT webhook endpoint.
Run alongside ibkr_bridge.py to test the full pipeline.

Usage:
  python signal_tester.py              # Single random signal
  python signal_tester.py --loop 60    # Random signal every 60s
  python signal_tester.py --burst 5    # 5 signals at once (stress test)
"""

import os
import sys
import json
import time
import random
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://palmswzrpquwemhfrvxs.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Webhook tokens from DB
TOKENS = {
    "traderspost": "tp_744e6dd0bef6142a9c969eaf3ed9223e",
    "holly_ai":    "hl_a9b9997d3d95f7fe358121e905391ffc",
    "signalstack": "ss_44114c4936850c8d7e543bac9c6a36da",
}

# Realistic signal templates
STOCK_SIGNALS = [
    {"symbol": "AAPL",  "price_range": (225, 250),  "qty_range": (5, 20)},
    {"symbol": "MSFT",  "price_range": (420, 450),  "qty_range": (3, 12)},
    {"symbol": "NVDA",  "price_range": (870, 920),  "qty_range": (2, 10)},
    {"symbol": "TSLA",  "price_range": (240, 280),  "qty_range": (5, 15)},
    {"symbol": "META",  "price_range": (590, 640),  "qty_range": (3, 10)},
    {"symbol": "GOOGL", "price_range": (175, 195),  "qty_range": (5, 20)},
    {"symbol": "AMD",   "price_range": (170, 190),  "qty_range": (5, 25)},
    {"symbol": "AMZN",  "price_range": (210, 230),  "qty_range": (3, 12)},
    {"symbol": "CRM",   "price_range": (300, 330),  "qty_range": (3, 10)},
    {"symbol": "NFLX",  "price_range": (880, 960),  "qty_range": (1, 5)},
]

FUTURE_SIGNALS = [
    {"symbol": "@ESH6", "price_range": (5400, 5500), "qty": 1},
    {"symbol": "@NQH6", "price_range": (19700, 20000), "qty": 1},
]

def random_stock_signal():
    s = random.choice(STOCK_SIGNALS)
    price = round(random.uniform(*s["price_range"]), 2)
    qty = random.randint(*s["qty_range"])
    action = random.choice(["buy", "buy", "buy", "sell"])  # 75% buy bias
    stop_pct = random.uniform(0.015, 0.03)
    stop = round(price * (1 - stop_pct) if action == "buy" else price * (1 + stop_pct), 2)
    return s["symbol"], action, qty, price, stop

def random_future_signal():
    s = random.choice(FUTURE_SIGNALS)
    price = round(random.uniform(*s["price_range"]), 2)
    action = random.choice(["buy", "sell"])
    stop = round(price - 30 if action == "buy" else price + 30, 2)
    return s["symbol"], action, s["qty"], price, stop

def send_signal(source="traderspost"):
    """Send a random signal through the specified source."""
    token = TOKENS.get(source)
    if not token:
        print(f"❌ Unknown source: {source}")
        return

    # 80% stocks, 20% futures
    if random.random() < 0.8:
        symbol, action, qty, price, stop = random_stock_signal()
        asset_class = "stock"
    else:
        symbol, action, qty, price, stop = random_future_signal()
        asset_class = "future"

    # Format payload based on source type
    if source == "traderspost":
        payload = {
            "action": action,
            "ticker": symbol,
            "quantity": qty,
            "price": price,
            "stop": stop,
            "assetClass": asset_class,
            "confidence": round(random.uniform(0.6, 0.95), 2),
        }
    elif source == "holly_ai":
        payload = {
            "signal": {
                "action": action,
                "symbol": symbol,
                "shares": qty,
                "price": price,
                "stop": stop,
                "confidence": round(random.uniform(0.65, 0.92), 2),
            }
        }
    elif source == "signalstack":
        payload = {
            "action": action.upper(),
            "symbol": symbol,
            "secType": "FUT" if asset_class == "future" else "STK",
            "quantity": qty,
            "lmtPrice": price,
            "auxPrice": stop,
        }

    # Send via RPC
    url = f"{SUPABASE_URL}/rest/v1/rpc/handle_webhook"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    body = {"webhook_token": token, "payload": payload}

    try:
        r = requests.post(url, json=body, headers=headers, timeout=10)
        result = r.json()

        if result.get("ok"):
            ts = datetime.now().strftime("%H:%M:%S")
            src_tag = {"traderspost": "TP", "holly_ai": "HL", "signalstack": "SS"}[source]
            color = "\033[92m" if action in ("buy", "bto") else "\033[91m"
            reset = "\033[0m"
            print(f"  {ts} [{src_tag}] {color}{action.upper():4s}{reset} {qty:3d} {symbol:8s} @ ${price:>9.2f}  SL ${stop:>9.2f}  → {result['signal_id'][:8]}")
            return True
        else:
            print(f"  ❌ {result.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"  ❌ Request failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="KAT Signal Test Harness")
    parser.add_argument("--loop", type=int, help="Send signal every N seconds")
    parser.add_argument("--burst", type=int, help="Send N signals at once")
    parser.add_argument("--source", default="random", choices=["traderspost", "holly_ai", "signalstack", "random"])
    args = parser.parse_args()

    print("═══════════════════════════════════════════════")
    print(" KAT Signal Test Harness")
    print(f" Endpoint: {SUPABASE_URL}")
    print("═══════════════════════════════════════════════")
    print()

    def pick_source():
        if args.source == "random":
            return random.choice(["traderspost", "holly_ai", "signalstack"])
        return args.source

    if args.burst:
        print(f"  Sending {args.burst} signals...")
        ok = sum(1 for _ in range(args.burst) if send_signal(pick_source()))
        print(f"\n  ✅ {ok}/{args.burst} signals sent")

    elif args.loop:
        print(f"  Sending signal every {args.loop}s (Ctrl+C to stop)")
        print()
        count = 0
        try:
            while True:
                send_signal(pick_source())
                count += 1
                time.sleep(args.loop)
        except KeyboardInterrupt:
            print(f"\n  🛑 Stopped after {count} signals")

    else:
        send_signal(pick_source())


if __name__ == "__main__":
    main()
