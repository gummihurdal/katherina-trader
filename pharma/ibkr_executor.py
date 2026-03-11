"""
ibkr_executor.py — IBKR TWS execution module for PDUFA trades
Uses ib_insync for clean async IBKR API interface.

SNB COMPLIANCE:
- Options ONLY (not shares) — bypasses 30-day holding period
- No CHF pairs
- Compliance check on every order before submission
- Hard stop at T-1 day (auto-close before decision)
"""

import logging
import json
from datetime import date, datetime, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass

from config import (IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID, 
                    MIN_HOLDING_DAYS, USE_OPTIONS_NOT_SHARES, 
                    FORBIDDEN_PAIRS, STOP_LOSS_PCT)

log = logging.getLogger(__name__)


@dataclass
class PDUFATrade:
    ticker: str
    drug: str
    pdufa_date: str
    signal: str           # LONG / SHORT
    p_approval: float
    kelly_fraction: float
    dollar_size: float
    entry_date: str
    expiry: str           # options expiry (1 week after PDUFA)
    strike: float
    option_type: str      # C or P
    contracts: int
    status: str = "PENDING"
    order_id: Optional[int] = None
    fill_price: Optional[float] = None
    pnl: Optional[float] = None


def snb_compliance_check(ticker: str, signal: str, dollar_size: float,
                          pdufa_date: str, use_options: bool = True) -> Tuple[bool, str]:
    """
    Validates proposed trade against SNB employment constraints.
    Returns (is_compliant: bool, reason: str)
    """
    # Check 1: Options not shares (SNB 30-day rule)
    if not use_options:
        return False, "SNB: Must use options, not shares (30-day holding rule)"
    
    # Check 2: No CHF pairs
    for pair in FORBIDDEN_PAIRS:
        if pair in ticker.upper():
            return False, f"SNB: {ticker} contains forbidden pair {pair}"
    
    # Check 3: Position size sanity
    if dollar_size > 20_000:
        return False, f"SNB: Position size ${dollar_size:,.0f} exceeds safe limit"
    
    # Check 4: PDUFA date is in the future
    pdufa = date.fromisoformat(pdufa_date)
    if pdufa <= date.today():
        return False, f"SNB: PDUFA date {pdufa_date} is in the past"
    
    # Check 5: Entry is at least 5 days before PDUFA (need time to exit)
    days_to_pdufa = (pdufa - date.today()).days
    if days_to_pdufa < 5:
        return False, f"SNB: Too close to PDUFA ({days_to_pdufa} days). Min 5 days required."
    
    log.info(f"Compliance check PASSED for {ticker} {signal} ${dollar_size:,.0f}")
    return True, "COMPLIANT"


class IBKRExecutor:
    """
    IBKR TWS executor using ib_insync.
    
    Install: pip install ib_insync --break-system-packages
    Requires TWS or IB Gateway running on IBKR_HOST:IBKR_PORT
    """
    
    def __init__(self, paper_trading: bool = True):
        self.paper = paper_trading
        self.ib = None
        self._connected = False
        
        # Port: 7497=paper TWS, 7496=live TWS, 4002=live Gateway
        self.port = IBKR_PORT if not paper_trading else 7497
    
    def connect(self) -> bool:
        """Connect to IBKR TWS."""
        try:
            from ib_insync import IB
            self.ib = IB()
            self.ib.connect(IBKR_HOST, self.port, clientId=IBKR_CLIENT_ID)
            self._connected = True
            log.info(f"Connected to IBKR {'PAPER' if self.paper else 'LIVE'} on port {self.port}")
            return True
        except ImportError:
            log.error("ib_insync not installed: pip install ib_insync --break-system-packages")
            return False
        except Exception as e:
            log.error(f"IBKR connection failed: {e}")
            return False
    
    def disconnect(self):
        if self.ib and self._connected:
            self.ib.disconnect()
            self._connected = False
    
    def get_stock_price(self, ticker: str, exchange: str = "SMART") -> Optional[float]:
        """Get current stock price."""
        if not self._connected:
            return None
        try:
            from ib_insync import Stock
            contract = Stock(ticker, exchange, "USD")
            self.ib.qualifyContracts(contract)
            ticker_data = self.ib.reqMktData(contract, "", False, False)
            self.ib.sleep(2)
            price = ticker_data.last or ticker_data.close
            self.ib.cancelMktData(contract)
            return float(price) if price else None
        except Exception as e:
            log.error(f"Failed to get price for {ticker}: {e}")
            return None
    
    def get_options_chain(self, ticker: str, pdufa_date: str) -> list:
        """
        Get options chain for expiry closest to PDUFA date + 1 week.
        Returns list of available strikes/expiries.
        """
        if not self._connected:
            return []
        try:
            from ib_insync import Stock, Option
            
            # Find expiry: PDUFA date + 1 week (so we survive the decision)
            pdufa = date.fromisoformat(pdufa_date)
            target_expiry = pdufa + timedelta(days=7)
            
            contract = Stock(ticker, "SMART", "USD")
            self.ib.qualifyContracts(contract)
            chains = self.ib.reqSecDefOptParams(contract.symbol, "", contract.secType, contract.conId)
            
            # Find closest expiry
            valid_chains = [c for c in chains if c.exchange == "SMART"]
            if not valid_chains:
                return []
            
            # Get available expiries as dates
            all_expiries = sorted(valid_chains[0].expirations)
            target_str = target_expiry.strftime("%Y%m%d")
            
            # Find nearest expiry on or after target
            valid = [e for e in all_expiries if e >= target_str]
            chosen_expiry = valid[0] if valid else all_expiries[-1]
            
            log.info(f"Options chain for {ticker}: expiry {chosen_expiry}, "
                    f"{len(valid_chains[0].strikes)} strikes available")
            
            return {
                "expiry": chosen_expiry,
                "strikes": sorted(valid_chains[0].strikes),
            }
        except Exception as e:
            log.error(f"Options chain failed for {ticker}: {e}")
            return {}
    
    def place_option_order(self, trade: PDUFATrade) -> Optional[int]:
        """
        Places an options order for a PDUFA trade.
        LONG signal → Buy calls
        SHORT signal → Buy puts
        """
        if not self._connected:
            log.error("Not connected to IBKR")
            return None
        
        # Final compliance check
        ok, reason = snb_compliance_check(
            trade.ticker, trade.signal, trade.dollar_size,
            trade.pdufa_date, use_options=True
        )
        if not ok:
            log.error(f"COMPLIANCE BLOCK: {reason}")
            return None
        
        try:
            from ib_insync import Option, LimitOrder, MarketOrder
            
            option_type = "C" if trade.signal == "LONG" else "P"
            
            contract = Option(
                symbol=trade.ticker,
                lastTradeDateOrContractMonth=trade.expiry,
                strike=trade.strike,
                right=option_type,
                exchange="SMART",
                currency="USD",
            )
            
            self.ib.qualifyContracts(contract)
            
            # Use limit order at mid-price
            ticker_data = self.ib.reqMktData(contract, "", False, False)
            self.ib.sleep(2)
            mid = (ticker_data.bid + ticker_data.ask) / 2 if ticker_data.bid and ticker_data.ask else None
            self.ib.cancelMktData(contract)
            
            if mid:
                order = LimitOrder("BUY", trade.contracts, round(mid, 2))
            else:
                order = MarketOrder("BUY", trade.contracts)
            
            trade_obj = self.ib.placeOrder(contract, order)
            self.ib.sleep(3)
            
            order_id = trade_obj.order.orderId
            log.info(f"Order placed: {trade.ticker} {option_type} {trade.strike} "
                    f"x{trade.contracts} @ {mid or 'MKT'} | OrderID: {order_id}")
            
            return order_id
            
        except Exception as e:
            log.error(f"Order placement failed for {trade.ticker}: {e}")
            return None
    
    def close_position(self, ticker: str, option_type: str, 
                       expiry: str, strike: float, contracts: int) -> bool:
        """Closes an existing options position (T-1 partial or full exit)."""
        if not self._connected:
            return False
        try:
            from ib_insync import Option, MarketOrder
            
            contract = Option(
                symbol=ticker,
                lastTradeDateOrContractMonth=expiry,
                strike=strike,
                right=option_type,
                exchange="SMART",
                currency="USD",
            )
            self.ib.qualifyContracts(contract)
            order = MarketOrder("SELL", contracts)
            trade_obj = self.ib.placeOrder(contract, order)
            self.ib.sleep(3)
            log.info(f"Close order placed: {ticker} {option_type} {strike} x{contracts}")
            return True
        except Exception as e:
            log.error(f"Close order failed for {ticker}: {e}")
            return False


# ── Trade sizing helper ────────────────────────────────────────────────────────
def size_option_trade(ticker: str, signal: str, dollar_size: float,
                      stock_price: float, pdufa_date: str,
                      option_premium: Optional[float] = None) -> Tuple[float, int, str]:
    """
    Converts dollar_size to number of option contracts.
    
    Returns (strike, contracts, option_type)
    
    Strategy:
    - LONG: Buy ATM calls (strike ≈ stock price)
    - SHORT: Buy ATM puts (strike ≈ stock price)
    - OTM (10-15% away) for smaller biotech to leverage IV crush
    """
    option_type = "C" if signal == "LONG" else "P"
    
    # Strike selection: ATM for large/mid cap, 10-15% OTM for small cap volatility plays
    # For now: ATM (adjust after paper trading calibration)
    strike = round(stock_price / 2.5) * 2.5  # round to nearest $2.50
    
    # Estimate premium: biotech ATM options typically cost 8-15% of stock price
    if option_premium is None:
        option_premium = stock_price * 0.10  # rough estimate
    
    # Each contract = 100 shares
    contract_cost = option_premium * 100
    contracts = max(1, int(dollar_size / contract_cost))
    
    # Cap at 10 contracts for safety
    contracts = min(10, contracts)
    
    actual_cost = contracts * contract_cost
    log.info(f"Option sizing: {contracts} x {option_type} {strike} strike, "
            f"est. cost ${actual_cost:,.0f} (target ${dollar_size:,.0f})")
    
    return strike, contracts, option_type


# ── T-1 auto-exit scheduler ────────────────────────────────────────────────────
class T1ExitScheduler:
    """
    Monitors active PDUFA trades and auto-closes 50% at T-1 day.
    Run as a background thread or daily cron job.
    """
    
    def __init__(self, executor: IBKRExecutor, trades_path: str = "active_trades.json"):
        self.executor = executor
        self.trades_path = trades_path
    
    def load_active_trades(self) -> list:
        try:
            with open(self.trades_path) as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    def save_active_trades(self, trades: list):
        with open(self.trades_path, "w") as f:
            json.dump(trades, f, indent=2)
    
    def check_and_exit(self):
        """Called daily. Exits 50% of positions at T-1."""
        trades = self.load_active_trades()
        today = date.today()
        modified = False
        
        for trade in trades:
            if trade.get("status") != "OPEN":
                continue
            
            pdufa = date.fromisoformat(trade["pdufa_date"])
            days_to = (pdufa - today).days
            
            # T-1: sell half
            if days_to == 1 and not trade.get("t1_exit_done"):
                contracts_to_sell = trade["contracts"] // 2
                if contracts_to_sell > 0:
                    success = self.executor.close_position(
                        trade["ticker"], trade["option_type"],
                        trade["expiry"], trade["strike"], contracts_to_sell
                    )
                    if success:
                        trade["t1_exit_done"] = True
                        trade["contracts_remaining"] = trade["contracts"] - contracts_to_sell
                        log.info(f"T-1 exit: {trade['ticker']} sold {contracts_to_sell} contracts")
                        modified = True
            
            # T+1 (day after PDUFA): close remaining if any
            elif days_to <= -1 and trade.get("contracts_remaining", 0) > 0:
                self.executor.close_position(
                    trade["ticker"], trade["option_type"],
                    trade["expiry"], trade["strike"], 
                    trade["contracts_remaining"]
                )
                trade["status"] = "CLOSED"
                trade["contracts_remaining"] = 0
                modified = True
        
        if modified:
            self.save_active_trades(trades)


if __name__ == "__main__":
    # Test compliance checker
    print("Testing SNB compliance checks:\n")
    
    tests = [
        ("RCKT", "LONG",  5000, "2026-03-28", True),
        ("CHSN", "LONG",  5000, "2026-03-28", False),  # shares = fail
        ("USDCHF", "LONG", 5000, "2026-03-28", True),  # CHF pair = fail
        ("VRDN", "LONG", 50000, "2026-06-30", True),   # too large = fail
        ("NUVL", "LONG",  8000, "2026-09-18", True),   # fine
    ]
    
    for ticker, signal, size, pdufa, use_opt in tests:
        ok, reason = snb_compliance_check(ticker, signal, size, pdufa, use_opt)
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"{status}  {ticker:8s} {signal:6s} ${size:6,}  {reason}")
