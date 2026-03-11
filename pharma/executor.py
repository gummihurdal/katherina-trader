"""
KAT PHARMA — executor.py
════════════════════════════════════════════════════════════════════
Reads signals from the KAT Pharma signal table, executes trades
through IBKR, and manages the full lifecycle automatically.

Sits alongside orchestrator.py in /root/katherina-trader/pharma/

FLOW:
  orchestrator.py → writes signals to DB
  executor.py     → reads signals, fires IBKR orders, manages exits

DEPLOY ON HETZNER:
  pip install ib_insync
  Then add three cron jobs (see bottom of file).

IBKR REQUIREMENT:
  IB Gateway must be running (headless TWS alternative).
  Download: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
  Run on the same machine as this script, or port-forward from your laptop.
"""

import os, sys, json, time, math, logging, argparse
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

# ── ib_insync ────────────────────────────────────────────────────────────
try:
    from ib_insync import IB, Option, Stock, LimitOrder, MarketOrder, util
    util.startLoop()
except ImportError:
    print("Missing: pip install ib_insync")
    sys.exit(1)

# ── KAT imports ──────────────────────────────────────────────────────────
# Add pharma dir to path so we can import from orchestrator
sys.path.insert(0, str(Path(__file__).parent))
try:
    from model import load_upcoming, SignalResult
    from config import DB_PATH
except ImportError:
    # Fallback: define minimal config inline if run standalone
    DB_PATH = Path(__file__).parent / "kat_pharma.db"


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════════════════

# IBKR connection — IB Gateway or TWS
IBKR_HOST      = "127.0.0.1"
IBKR_PORT      = 4001          # IB Gateway live=4001, paper=4002 / TWS live=7496, paper=7497
IBKR_CLIENT_ID = 10

# Position sizing
MAX_TRADE_USD  = 4000          # hard cap per trade
SIGNAL_MIN     = 0.62          # only act on signals below this approval prob (KAT SHORT threshold)
MAX_ASK_SANITY = 1.50          # reject if ask > this (data error guard)
T1_SELL_FRAC   = 0.50          # sell this fraction on T-1

# Scheduler times (CET / Europe/Zurich)
T1_TIME        = "15:00"       # T-1 sell time
EXIT_TIME      = "14:35"       # PDUFA day exit time (5 min after US open)

CET = ZoneInfo("Europe/Zurich")

# State file — tracks open positions across cron runs
STATE_FILE = Path(__file__).parent / "executor_state.json"
LOG_FILE   = Path(__file__).parent / "executor.log"

# ════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ]
)
log = logging.getLogger("KAT.executor")


# ════════════════════════════════════════════════════════════════════════════
#  STATE
# ════════════════════════════════════════════════════════════════════════════

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"positions": {}}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))

def get_position(ticker: str) -> dict | None:
    return load_state()["positions"].get(ticker)

def set_position(ticker: str, data: dict):
    s = load_state()
    s["positions"][ticker] = data
    save_state(s)

def clear_position(ticker: str):
    s = load_state()
    s["positions"].pop(ticker, None)
    save_state(s)


# ════════════════════════════════════════════════════════════════════════════
#  IBKR HELPERS
# ════════════════════════════════════════════════════════════════════════════

def connect() -> IB:
    ib = IB()
    for attempt in range(1, 5):
        try:
            ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, timeout=20)
            log.info(f"Connected to IBKR  host={IBKR_HOST}  port={IBKR_PORT}")
            return ib
        except Exception as e:
            log.warning(f"Connect attempt {attempt}/4 failed: {e}")
            if attempt < 4:
                time.sleep(15)
    log.error("Cannot connect to IBKR after 4 attempts. Is IB Gateway running?")
    sys.exit(1)


def qualify_option(ib: IB, ticker: str, expiry: str, strike: float, right: str) -> Option:
    contract = Option(
        symbol=ticker,
        lastTradeDateOrContractMonth=expiry,
        strike=strike,
        right=right,
        exchange="SMART",
        currency="USD",
    )
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        raise ValueError(f"Option {ticker} {expiry} {strike}{right} not found in IBKR")
    log.info(f"Option qualified: {ticker} {expiry} ${strike}{right}  conId={qualified[0].conId}")
    return qualified[0]


def get_ask(ib: IB, contract) -> float:
    """Live ask with retry + snapshot fallback."""
    for attempt in range(4):
        ticker_data = ib.reqMktData(contract, "", False, False)
        ib.sleep(3)
        ask = ticker_data.ask if ticker_data.ask and ticker_data.ask > 0 else None
        ib.cancelMktData(contract)
        if ask:
            return ask

        snap = ib.reqMktData(contract, "", True, False)
        ib.sleep(2)
        ask = snap.ask if snap.ask and snap.ask > 0 else None
        ib.cancelMktData(contract)
        if ask:
            return ask

        log.warning(f"No ask on attempt {attempt+1}/4, waiting 10s...")
        time.sleep(10)

    raise RuntimeError("Cannot get live ask after 4 attempts — markets may be closed")


def execute_order(ib: IB, contract, action: str, qty: int, limit_px: float) -> float:
    """
    Place limit order. If unfilled after 3 min, switch to market.
    Returns avg fill price.
    """
    log.info(f"Placing {action} {qty}x {contract.symbol} ${contract.strike}{contract.right} "
             f"limit=${limit_px:.2f}")

    order = LimitOrder(action, qty, round(limit_px, 2))
    trade = ib.placeOrder(contract, order)

    deadline = time.time() + 180   # 3 min limit window
    while time.time() < deadline:
        ib.sleep(5)
        st    = trade.orderStatus.status
        filled = trade.orderStatus.filled
        avg   = trade.orderStatus.avgFillPrice

        log.info(f"  Order status: {st}  filled={filled}/{qty}  avg=${avg:.2f}")

        if st == "Filled":
            log.info(f"✓ FILLED  {action} {filled}x @ ${avg:.2f}")
            return avg
        if st in ("Cancelled", "Inactive", "ApiCancelled"):
            break

    # Upgrade to market
    log.warning("Limit order not filled in 3 min — upgrading to market order")
    ib.cancelOrder(order)
    ib.sleep(2)

    mkt = MarketOrder(action, qty)
    trade = ib.placeOrder(contract, mkt)
    ib.sleep(8)
    avg = trade.orderStatus.avgFillPrice or 0.0
    log.info(f"✓ Market fill  {action} {qty}x @ ${avg:.2f}")
    return avg


def live_positions(ib: IB, ticker: str) -> int:
    """Return current option contracts held for ticker."""
    for pos in ib.positions():
        if pos.contract.symbol == ticker and pos.contract.secType == "OPT":
            return int(pos.position)
    return 0


# ════════════════════════════════════════════════════════════════════════════
#  SIGNAL READER
#  Reads KAT Pharma signal table from SQLite
# ════════════════════════════════════════════════════════════════════════════

def read_signals() -> list[dict]:
    """Pull actionable SHORT signals from KAT Pharma signal table."""
    import sqlite3
    if not DB_PATH.exists():
        log.warning(f"DB not found at {DB_PATH} — run orchestrator.py --score first")
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get signals where KAT says SHORT (approval_prob < threshold) and PDUFA is soon
    try:
        cur.execute("""
            SELECT ticker, drug_name, pdufa_date, approval_prob, signal, signal_ts
            FROM   signals
            WHERE  signal = 'SHORT'
              AND  approval_prob <= ?
              AND  pdufa_date >= date('now')
              AND  pdufa_date <= date('now', '+10 days')
            ORDER  BY pdufa_date ASC
        """, (SIGNAL_MIN,))
        rows = [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        log.warning("Signal table not found — run orchestrator.py --score first")
        rows = []

    conn.close()
    return rows


# ════════════════════════════════════════════════════════════════════════════
#  OPTION SELECTION
#  Choose the right expiry + strike based on PDUFA date
# ════════════════════════════════════════════════════════════════════════════

def select_option_params(ticker: str, pdufa_date: str, stock_price: float) -> tuple[str, float]:
    """
    Returns (expiry_str, strike) for the put to buy.
    Expiry: first Friday at least 4 days after PDUFA.
    Strike: ~25-30% OTM (standard PDUFA put positioning).
    """
    from datetime import date, timedelta

    pdufa = date.fromisoformat(pdufa_date)

    # Find first Friday >= pdufa + 4 days
    target = pdufa + timedelta(days=4)
    while target.weekday() != 4:    # 4 = Friday
        target += timedelta(days=1)

    expiry = target.strftime("%Y%m%d")

    # Strike: round down to nearest $0.50 at ~70-72% of current price
    raw_strike = stock_price * 0.72
    strike = math.floor(raw_strike * 2) / 2    # round to nearest $0.50

    log.info(f"Option params: expiry={expiry}  strike=${strike:.2f}  "
             f"(stock=${stock_price:.2f}, ~{strike/stock_price*100:.0f}% of price)")
    return expiry, strike


def get_stock_price(ib: IB, ticker: str) -> float:
    stock = Stock(ticker, "SMART", "USD")
    ib.qualifyContracts(stock)
    tkr = ib.reqMktData(stock, "", False, False)
    ib.sleep(3)
    price = tkr.last or tkr.close or tkr.bid or 0.0
    ib.cancelMktData(stock)
    log.info(f"{ticker} stock price: ${price:.2f}")
    return price


# ════════════════════════════════════════════════════════════════════════════
#  PHASE 1 — BUY
# ════════════════════════════════════════════════════════════════════════════

def phase_buy():
    """
    Reads KAT signals. For each actionable SHORT signal with no open position,
    buys puts automatically.
    """
    log.info("═" * 60)
    log.info("KAT EXECUTOR — PHASE 1: SIGNAL SCAN + BUY")
    log.info("═" * 60)

    signals = read_signals()
    if not signals:
        log.info("No actionable SHORT signals within 10-day window. Nothing to do.")
        return

    for sig in signals:
        ticker     = sig["ticker"]
        pdufa_date = sig["pdufa_date"]
        prob       = sig["approval_prob"]
        drug       = sig["drug_name"]

        log.info(f"Signal: {ticker}  drug={drug}  pdufa={pdufa_date}  "
                 f"P(approval)={prob:.0%}  P(rejection)={1-prob:.0%}")

        # Skip if already have an open position
        if get_position(ticker):
            log.info(f"{ticker}: position already open, skipping buy")
            continue

        ib = connect()

        try:
            # Get stock price
            stock_px = get_stock_price(ib, ticker)
            if stock_px <= 0:
                log.error(f"{ticker}: could not get stock price, skipping")
                continue

            # Select option
            expiry, strike = select_option_params(ticker, pdufa_date, stock_px)

            # Qualify option contract
            contract = qualify_option(ib, ticker, expiry, strike, "P")

            # Get live ask
            ask = get_ask(ib, contract)
            log.info(f"Live ask: ${ask:.2f}/share = ${ask*100:.2f}/contract")

            # Sanity check
            if ask > MAX_ASK_SANITY:
                log.error(f"Ask ${ask:.2f} exceeds sanity limit ${MAX_ASK_SANITY}. "
                          f"Skipping {ticker}.")
                continue

            # Size position: Kelly-adjusted to max budget
            contracts = max(1, min(10, int(MAX_TRADE_USD / (ask * 100))))
            total_cost = contracts * ask * 100

            log.info(f"Sizing: {contracts} contracts @ ${ask:.2f} = ${total_cost:.2f} total")

            # Execute buy
            avg_fill = execute_order(ib, contract, "BUY", contracts, ask)

            # Save position to state
            pdufa_dt = date.fromisoformat(pdufa_date)
            t1_date  = (pdufa_dt - __import__("datetime").timedelta(days=1)).isoformat()

            set_position(ticker, {
                "ticker":          ticker,
                "drug":            drug,
                "pdufa_date":      pdufa_date,
                "t1_date":         t1_date,
                "expiry":          expiry,
                "strike":          strike,
                "right":           "P",
                "contracts_total": contracts,
                "contracts_open":  contracts,
                "avg_buy_price":   avg_fill,
                "total_cost":      round(total_cost, 2),
                "buy_ts":          datetime.now(CET).isoformat(),
                "t1_done":         False,
                "exit_done":       False,
                "kat_signal":      sig["signal"],
                "kat_prob":        prob,
            })

            log.info(f"✓ BUY COMPLETE: {ticker}  {contracts}x ${strike}P {expiry}  "
                     f"avg=${avg_fill:.2f}  total=${contracts*avg_fill*100:.2f}")

        except Exception as e:
            log.error(f"Buy phase failed for {ticker}: {e}", exc_info=True)
        finally:
            ib.disconnect()


# ════════════════════════════════════════════════════════════════════════════
#  PHASE 2 — T-1 SELL (50%)
# ════════════════════════════════════════════════════════════════════════════

def phase_t1_sell():
    """
    Sell 50% of all open positions whose T-1 date is today.
    Cron fires this at T1_TIME on T1_DATE.
    """
    log.info("═" * 60)
    log.info("KAT EXECUTOR — PHASE 2: T-1 SELL (50%)")
    log.info("═" * 60)

    today_str = date.today().isoformat()
    state     = load_state()

    targets = [
        pos for pos in state["positions"].values()
        if pos["t1_date"] == today_str and not pos["t1_done"]
    ]

    if not targets:
        log.info("No T-1 exits due today.")
        return

    for pos in targets:
        ticker = pos["ticker"]
        log.info(f"T-1 exit for {ticker}  pdufa={pos['pdufa_date']}")

        ib = connect()
        try:
            contract = qualify_option(
                ib, ticker, pos["expiry"], pos["strike"], pos["right"]
            )

            # How many contracts to sell
            qty_held  = live_positions(ib, ticker)
            qty_sell  = max(1, math.floor(qty_held * T1_SELL_FRAC))
            log.info(f"Held={qty_held}  selling={qty_sell} ({T1_SELL_FRAC*100:.0f}%)")

            # Get current bid
            ask = get_ask(ib, contract)

            avg_fill = execute_order(ib, contract, "SELL", qty_sell, ask)

            # Update state
            pos["contracts_open"] = qty_held - qty_sell
            pos["t1_done"]        = True
            pos["t1_sell_qty"]    = qty_sell
            pos["t1_sell_price"]  = avg_fill
            pos["t1_sell_ts"]     = datetime.now(CET).isoformat()

            cost_basis_sold = qty_sell * pos["avg_buy_price"] * 100
            proceeds        = qty_sell * avg_fill * 100
            pnl             = proceeds - cost_basis_sold

            set_position(ticker, pos)
            log.info(f"✓ T-1 SELL COMPLETE: {ticker}  sold {qty_sell}x @ ${avg_fill:.2f}  "
                     f"P&L on this tranche: ${pnl:+.2f}")

        except Exception as e:
            log.error(f"T-1 sell failed for {ticker}: {e}", exc_info=True)
        finally:
            ib.disconnect()


# ════════════════════════════════════════════════════════════════════════════
#  PHASE 3 — PDUFA EXIT (100% remaining)
# ════════════════════════════════════════════════════════════════════════════

def phase_pdufa_exit():
    """
    Sell ALL remaining contracts on PDUFA date at market open.
    Cron fires this at EXIT_TIME on PDUFA_DATE.
    """
    log.info("═" * 60)
    log.info("KAT EXECUTOR — PHASE 3: PDUFA DAY EXIT (ALL REMAINING)")
    log.info("═" * 60)

    today_str = date.today().isoformat()
    state     = load_state()

    targets = [
        pos for pos in state["positions"].values()
        if pos["pdufa_date"] == today_str and not pos["exit_done"]
    ]

    if not targets:
        log.info("No PDUFA exits due today.")
        return

    for pos in targets:
        ticker = pos["ticker"]
        log.info(f"PDUFA exit for {ticker}")

        ib = connect()
        try:
            contract = qualify_option(
                ib, ticker, pos["expiry"], pos["strike"], pos["right"]
            )

            qty_held = live_positions(ib, ticker)
            if qty_held <= 0:
                log.info(f"{ticker}: no contracts held, nothing to exit")
                pos["exit_done"] = True
                set_position(ticker, pos)
                continue

            log.info(f"Selling all {qty_held} remaining contracts at market")

            # PDUFA exit uses market order — we need fast fill, not price precision
            mkt = MarketOrder("SELL", qty_held)
            trade = ib.placeOrder(contract, mkt)
            ib.sleep(10)
            avg_fill = trade.orderStatus.avgFillPrice or 0.0

            # Final P&L
            total_invested  = pos["total_cost"]
            t1_proceeds     = pos.get("t1_sell_qty", 0) * pos.get("t1_sell_price", 0) * 100
            final_proceeds  = qty_held * avg_fill * 100
            total_proceeds  = t1_proceeds + final_proceeds
            total_pnl       = total_proceeds - total_invested
            pct_return      = (total_pnl / total_invested * 100) if total_invested > 0 else 0

            pos["exit_done"]         = True
            pos["exit_qty"]          = qty_held
            pos["exit_price"]        = avg_fill
            pos["exit_ts"]           = datetime.now(CET).isoformat()
            pos["total_pnl_usd"]     = round(total_pnl, 2)
            pos["total_pct_return"]  = round(pct_return, 1)
            set_position(ticker, pos)

            log.info("─" * 60)
            log.info(f"TRADE CLOSED: {ticker}")
            log.info(f"  Invested:        ${total_invested:,.2f}")
            log.info(f"  Total proceeds:  ${total_proceeds:,.2f}")
            log.info(f"  Net P&L:         ${total_pnl:+,.2f}  ({pct_return:+.1f}%)")
            log.info("─" * 60)

        except Exception as e:
            log.error(f"PDUFA exit failed for {ticker}: {e}", exc_info=True)
        finally:
            ib.disconnect()


# ════════════════════════════════════════════════════════════════════════════
#  STATUS
# ════════════════════════════════════════════════════════════════════════════

def print_status():
    state = load_state()
    if not state.get("positions"):
        print("\n  No open positions.\n")
        return

    print(f"\n{'═'*60}")
    print(f"  KAT EXECUTOR — POSITION STATUS  [{datetime.now(CET).strftime('%Y-%m-%d %H:%M CET')}]")
    print(f"{'═'*60}")

    for ticker, pos in state["positions"].items():
        print(f"\n  {ticker}  —  {pos.get('drug', '')}")
        print(f"    PDUFA:         {pos['pdufa_date']}")
        print(f"    Option:        ${pos['strike']:.2f}P  exp {pos['expiry']}")
        print(f"    Contracts:     {pos['contracts_total']} bought  /  {pos['contracts_open']} remaining")
        print(f"    Avg buy price: ${pos['avg_buy_price']:.2f}")
        print(f"    Total cost:    ${pos['total_cost']:.2f}")
        print(f"    KAT signal:    {pos['kat_signal']}  P(approval)={pos['kat_prob']:.0%}")
        print(f"    T-1 done:      {'✓' if pos['t1_done'] else '✗ fires ' + pos['t1_date'] + ' at ' + T1_TIME}")
        print(f"    Exit done:     {'✓  P&L=' + str(pos.get('total_pnl_usd','')) + ' (' + str(pos.get('total_pct_return','')) + '%)' if pos['exit_done'] else '✗ fires ' + pos['pdufa_date'] + ' at ' + EXIT_TIME}")

    print(f"\n{'═'*60}\n")


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

"""
CRON SETUP — add these 3 lines to crontab on Hetzner:

  crontab -e

  # KAT Pharma — buy scan (runs daily at 15:05 CET, Mon-Fri)
  5 15 * * 1-5  cd /root/katherina-trader/pharma && python3 executor.py --buy   >> /var/log/kat_executor.log 2>&1

  # KAT Pharma — T-1 sell (runs daily at 15:00 CET, Mon-Fri)
  0 15 * * 1-5  cd /root/katherina-trader/pharma && python3 executor.py --t1    >> /var/log/kat_executor.log 2>&1

  # KAT Pharma — PDUFA exit (runs daily at 14:35 CET, Mon-Fri)
  35 14 * * 1-5 cd /root/katherina-trader/pharma && python3 executor.py --exit  >> /var/log/kat_executor.log 2>&1

Each phase only acts if there is something to do — safe to run daily.
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KAT Pharma Trade Executor")
    parser.add_argument("--buy",       action="store_true", help="Scan signals and buy puts")
    parser.add_argument("--t1",        action="store_true", help="Run T-1 sell (50%% of position)")
    parser.add_argument("--exit",      action="store_true", help="Run PDUFA day exit (all remaining)")
    parser.add_argument("--status",    action="store_true", help="Show current positions")
    parser.add_argument("--all",       action="store_true", help="Run all phases in sequence (testing)")
    args = parser.parse_args()

    if args.status:
        print_status()
    elif args.buy:
        phase_buy()
    elif args.t1:
        phase_t1_sell()
    elif args.exit:
        phase_pdufa_exit()
    elif args.all:
        phase_buy()
        print_status()
    else:
        parser.print_help()
        print("""
Examples:
  python3 executor.py --buy       # KAT scans signals and places buy orders now
  python3 executor.py --t1        # Run T-1 sell (fires on March 15 at 15:00 CET)
  python3 executor.py --exit      # Run PDUFA exit (fires on March 16 at 14:35 CET)
  python3 executor.py --status    # Show what's open
""")
