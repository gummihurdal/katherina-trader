# KAT — Katherina's Autonomous Trader
## System Architecture v2.0 — Signal Aggregator Edition

---

## 1. DESIGN PRINCIPLES

```
MODULAR    → Every component is independent, testable, replaceable
SECURE     → Zero trust. Encrypted at rest + transit. No secrets in code
RESILIENT  → Graceful degradation. If one API/signal fails, others continue
AUDITABLE  → Every decision logged. Full trade history. Compliance-ready
OBSERVABLE → Real-time health metrics. Alert on anomalies
EXTENSIBLE → New strategies AND signal sources plug in without refactoring
SOVEREIGN  → Guardian risk engine has absolute veto over ALL signal sources
```

---

## 2. CORE CONCEPT: SIGNAL AGGREGATOR

KAT is NOT just a strategy runner. It is a **signal aggregation platform** that:

1. Receives signals from multiple verified external providers
2. Receives signals from our own internal strategies
3. Normalizes ALL signals to a unified format
4. Passes EVERY signal through the Guardian risk engine
5. Executes approved signals via IBKR (paper or live)
6. Logs everything for audit and performance tracking

**No signal source — external or internal — can bypass the Guardian.**

```
EXTERNAL SIGNALS                    INTERNAL STRATEGIES
                                    
  Collective2 ──┐                  ┌── Iron Condor (Mihail)
  TradersPost ──┤                  ├── Momentum (MACD+RSI)
  Trade Ideas ──┤    ┌──────────┐  ├── Covered Calls
  SignalStack ──┼───→│NORMALIZER│←─┤── Dividend Capture
  Telegram ─────┤    └────┬─────┘  └── [Future plugins]
  Custom API ───┘         │
                          │
                   ┌──────┴──────┐
                   │  GUARDIAN   │  ← 10 risk checks
                   │  RISK ENGINE│  ← Circuit breakers
                   │             │  ← ABSOLUTE VETO
                   └──────┬──────┘
                          │
                   ┌──────┴──────┐
                   │  EXECUTION  │
                   │  MANAGER    │
                   └──────┬──────┘
                          │
                   ┌──────┴──────┐
                   │    IBKR     │
                   │ TWS/Gateway │
                   └─────────────┘
```

---

## 3. THE 5 SIGNAL SOURCES

### Source 1: Collective2 — Verified Copy Trading
```
Asset Classes:  Futures, Options, Stocks, Forex
Delivery:       C2 AutoTrade API (REST + real-time polling)
Integration:    C2 API v3 → KAT Normalizer → Guardian → IBKR
Track Records:  Audited. Real fills. Public Sharpe/drawdown/win rate.
IBKR Support:   Official — signed IB Agreement for signal reception
Cost:           $20-200/mo per strategy subscribed
Why:            12,000+ strategies with verified performance.
                Gold standard for signal authenticity.
```

**C2 API signal format:**
```json
{
  "apikey": "YOUR_C2_API_KEY",
  "systemid": "94679653",
  "signal": {
    "action": "BTO",
    "quant": 2,
    "symbol": "@ESM6",
    "typeofsymbol": "future",
    "limit": 5420.25,
    "duration": "DAY"
  }
}
```

**How KAT consumes C2:**
```
C2 API (poll every 5s for new signals)
  → Parse signal JSON
  → Convert to KAT unified Signal object
  → Tag source="collective2", strategy_id="c2_94679653"
  → Send to Guardian for risk checks
  → If approved → Execute via IBKR
  → Log result to Supabase
```

---

### Source 2: TradersPost — Webhook Signal Router
```
Asset Classes:  Stocks, Options, Futures, Crypto
Delivery:       Webhook (JSON POST)
Integration:    TradingView/TrendSpider → TradersPost → Webhook → KAT
Track Records:  Depends on underlying strategy
IBKR Support:   Native integration
Cost:           Free tier available, Pro $49/mo
Why:            Universal webhook router. Any TradingView Pine Script
                strategy or TrendSpider alert can fire into KAT.
```

**Webhook JSON format (TradersPost standard):**
```json
{
  "ticker": "TSLA",
  "action": "buy",
  "sentiment": "bullish",
  "quantity": 10,
  "price": 245.50,
  "stop": 238.00,
  "target": 260.00
}
```

**Pine Script strategies we can subscribe to:**
- TradingView community strategies (free)
- Premium Pine Script signals (paid subscriptions)
- Our own Pine Scripts running on TradingView

---

### Source 3: Trade Ideas Holly AI — Institutional Stock Signals
```
Asset Classes:  US Equities (stocks + ETFs)
Delivery:       API alerts / webhook integration via SignalStack
Integration:    Holly AI → SignalStack webhook → KAT Normalizer
Track Records:  Audited. 68% win rate backtested. Daily retraining.
IBKR Support:   Via SignalStack or Brokerage Plus
Cost:           $228/mo (Premium with Holly AI)
Why:            AI retrains every night on ALL US stocks.
                Selects highest-probability setups for next day.
                Institutional-grade scanning (500+ filters).
```

**Holly signal characteristics:**
```
- 5-8 curated signals per day
- Specific entry, stop-loss, and target levels
- Strategy name (e.g., "Holly Grail", "Holly 2.0")
- Primarily day trades (hold minutes to hours)
- US market hours only (9:30 AM - 4:00 PM ET)
```

---

### Source 4: SignalStack — Direct Webhook-to-IBKR Bridge
```
Asset Classes:  Stocks, Futures, Options, Forex, CFDs, Crypto
Delivery:       Webhook (JSON POST) → IBKR Client Portal API
Integration:    Any signal source → Webhook → SignalStack → IBKR
Track Records:  N/A (router, not signal provider)
IBKR Support:   Native. Full options + futures symbol formatting.
Cost:           Free tier (limited), Pro ~$30/mo
Why:            Fastest execution (0.45s). 33+ broker support.
                Backup routing path if TradersPost is down.
                1000+ pages of documentation for order formatting.
```

**SignalStack IBKR options format:**
```json
{
  "symbol": "TSLA260320C00250000",
  "action": "buy",
  "quantity": 5,
  "limit_price": 12.50,
  "class": "option"
}
```

**SignalStack IBKR futures format:**
```json
{
  "symbol": "ESM6",
  "action": "buy",
  "quantity": 2,
  "class": "future"
}
```

---

### Source 5: Our Own Strategies — Full Control
```
Asset Classes:  Options (Iron Condor), Stocks (Momentum), Dividends
Delivery:       Direct Python → IBKR TWS API
Integration:    Strategy Engine → Signal → Guardian → Execution Manager
Track Records:  Our backtests. Paper trading results. Full transparency.
IBKR Support:   Direct API (ibapi Python SDK)
Cost:           $0 (our code)
Why:            Total control. Tune parameters. No third-party dependency.
```

**Built-in strategies:**

| Strategy | Asset | Logic | Hold Period |
|----------|-------|-------|-------------|
| Iron Condor | Options (TSLA/META) | Mihail's 40-DTE, delta-based strikes, sell premium | ~40 days |
| Momentum | Stocks | MACD + RSI crossover, volume confirmation | 2-10 days |
| Covered Calls | Options | Sell OTM calls on long positions, IV-optimized | Until expiry |
| Dividend Capture | Stocks | Buy before ex-date, hold through payment | 3-10 days |

---

## 4. HIGH-LEVEL ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                          │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │               KAT DASHBOARD (React + Vite + TS)             │   │
│   │            katherina.azurenexus.com (GitHub Pages)           │   │
│   │                                                             │   │
│   │  ┌───────────┐ ┌───────────┐ ┌─────────┐ ┌─────────────┐  │   │
│   │  │ Portfolio  │ │ Signal    │ │ Trade   │ │ Risk        │  │   │
│   │  │ Overview   │ │ Hub       │ │ Journal │ │ Dashboard   │  │   │
│   │  └───────────┘ └───────────┘ └─────────┘ └─────────────┘  │   │
│   │  ┌───────────┐ ┌───────────┐ ┌─────────┐ ┌─────────────┐  │   │
│   │  │ Strategy  │ │ Backtest  │ │ Alerts  │ │ Settings &  │  │   │
│   │  │ Control   │ │ Lab       │ │ Center  │ │ Auth        │  │   │
│   │  └───────────┘ └───────────┘ └─────────┘ └─────────────┘  │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                               │                                     │
│                     REST + WebSocket (Supabase Realtime)            │
│                               │                                     │
├───────────────────────────────┼─────────────────────────────────────┤
│                         API GATEWAY                                 │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │            Supabase Edge Functions (Deno)                   │   │
│   │                                                             │   │
│   │  • JWT Authentication and RBAC                              │   │
│   │  • Rate Limiting (100 req/min per user)                     │   │
│   │  • Request Validation (Zod schemas)                         │   │
│   │  • API Key Vault (AES-256 encrypted)                        │   │
│   │  • Webhook receiver endpoints (for external signals)        │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                               │                                     │
├───────────────────────────────┼─────────────────────────────────────┤
│                    SIGNAL AGGREGATION LAYER                         │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    SIGNAL INGESTION                          │   │
│   │                                                             │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │   │
│   │  │Collective│ │Traders   │ │Trade     │ │Signal        │  │   │
│   │  │2 Poller  │ │Post Hook │ │Ideas Hook│ │Stack Hook    │  │   │
│   │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘  │   │
│   │       │             │            │              │           │   │
│   │       └─────────────┼────────────┼──────────────┘           │   │
│   │                     │            │                          │   │
│   │              ┌──────┴────────────┴──────┐                   │   │
│   │              │      NORMALIZER          │                   │   │
│   │              │                          │                   │   │
│   │              │  All formats → unified   │                   │   │
│   │              │  Signal object with      │                   │   │
│   │              │  source attribution      │                   │   │
│   │              └──────────┬───────────────┘                   │   │
│   └─────────────────────────┼───────────────────────────────────┘   │
│                             │                                       │
├─────────────────────────────┼───────────────────────────────────────┤
│                       SERVICE LAYER                                 │
│                             │                                       │
│   ┌──────────────┐  ┌──────┴────────┐  ┌─────────────────────┐     │
│   │  STRATEGY    │  │   GUARDIAN     │  │   DATA              │     │
│   │  ENGINE      │  │   RISK ENGINE │  │   AGGREGATOR        │     │
│   │  (Internal)  │  │               │  │                     │     │
│   │              │  │ • 10 Checks   │  │ • Market Data       │     │
│   │ • IronCondor │  │ • Breakers    │  │   Normalizer        │     │
│   │ • Momentum   │──│ • Kill Switch │  │ • Multi-source      │     │
│   │ • CovCalls   │  │ • VETO POWER  │  │   Failover          │     │
│   │ • DivCapture │  │ • Compliance  │  │ • Cache Layer       │     │
│   │ • [Plugin]   │  │               │  │ • WebSocket Fan-out │     │
│   └──────────────┘  └──────┬────────┘  └─────────────────────┘     │
│                            │                                        │
│                     ┌──────┴───────┐                                │
│                     │  EXECUTION   │                                │
│                     │  MANAGER     │                                │
│                     │              │                                │
│                     │ • Order Queue│                                │
│                     │ • Paper/Live │                                │
│                     │ • Fill Track │                                │
│                     │ • Retry/Fail │                                │
│                     └──────┬───────┘                                │
│                            │                                        │
├────────────────────────────┼────────────────────────────────────────┤
│                      BROKER LAYER                                   │
│                            │                                        │
│               ┌────────────┴────────────┐                          │
│      ┌────────┴────────┐    ┌──────────┴──────────┐               │
│      │  IBKR Gateway   │    │  Paper Simulator     │               │
│      │  (TWS API)      │    │  (Internal Engine)   │               │
│      │  Port 7497 LIVE │    │  Port 7496 PAPER     │               │
│      └─────────────────┘    └──────────────────────┘               │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                      DATA LAYER                                     │
│                                                                     │
│   ┌───────────────┐  ┌───────────────┐  ┌─────────────────────┐    │
│   │  Supabase     │  │  Redis        │  │  External APIs      │    │
│   │  PostgreSQL   │  │  (Upstash)    │  │                     │    │
│   │               │  │               │  │  • IBKR TWS API     │    │
│   │  • Users      │  │  • Price      │  │  • Polygon.io       │    │
│   │  • Trades     │  │    Cache      │  │  • Alpha Vantage    │    │
│   │  • Positions  │  │  • Signal     │  │  • ORATS            │    │
│   │  • Signals    │  │    Queue      │  │  • FMP              │    │
│   │  • Strategies │  │  • Rate       │  │  • Finnhub          │    │
│   │  • Audit Log  │  │    Limits     │  │  • Collective2 API  │    │
│   │  • Settings   │  │  • Session    │  │  • TradersPost API  │    │
│   │  • Alerts     │  │    State      │  │  • Trade Ideas API  │    │
│   └───────────────┘  └───────────────┘  └─────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. SIGNAL NORMALIZER — Unified Signal Object

Every signal from every source is converted to this format before hitting the Guardian:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime

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

@dataclass
class UnifiedSignal:
    # Identity
    id: str                            # UUID
    source: SignalSource               # Where did this come from?
    source_strategy_id: str            # e.g., "c2_94679653" or "holly_grail"
    source_strategy_name: str          # Human-readable name
    
    # Trade details
    action: ActionType                 # buy, sell, bto, sto, btc, stc
    asset_class: AssetClass            # stock, option, future, forex
    symbol: str                        # "TSLA", "@ESM6", "TSLA260320C250"
    quantity: int                      # Number of shares/contracts
    
    # Pricing
    order_type: str                    # "market", "limit", "stop", "stop_limit"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    
    # Risk management
    stop_loss: Optional[float] = None  # Where to cut losses
    take_profit: Optional[float] = None # Where to take gains
    
    # Options-specific
    expiry: Optional[str] = None       # "2026-03-20"
    strike: Optional[float] = None     # 250.00
    put_call: Optional[str] = None     # "call" or "put"
    
    # Multi-leg (Iron Condors, spreads)
    legs: list = field(default_factory=list)
    
    # Metadata
    confidence: float = 0.0            # 0.0 - 1.0 (from source)
    urgency: str = "normal"            # "immediate", "normal", "low"
    notes: str = ""                    # Strategy reasoning
    raw_payload: dict = field(default_factory=dict)  # Original signal JSON
    
    # Timestamps
    signal_time: datetime = field(default_factory=datetime.utcnow)
    received_time: datetime = field(default_factory=datetime.utcnow)
    
    # Risk engine will populate these
    risk_approved: Optional[bool] = None
    risk_checks: dict = field(default_factory=dict)
    risk_rejection_reason: Optional[str] = None
```

**Source-specific parsers:**

```python
# parsers/collective2.py
class C2Parser:
    def parse(self, c2_signal: dict) -> UnifiedSignal:
        """Convert Collective2 API signal to UnifiedSignal."""
        ...

# parsers/traderspost.py
class TradersPostParser:
    def parse(self, webhook_payload: dict) -> UnifiedSignal:
        """Convert TradersPost webhook JSON to UnifiedSignal."""
        ...

# parsers/trade_ideas.py  
class TradeIdeasParser:
    def parse(self, holly_alert: dict) -> UnifiedSignal:
        """Convert Trade Ideas Holly AI alert to UnifiedSignal."""
        ...

# parsers/signalstack.py
class SignalStackParser:
    def parse(self, webhook_payload: dict) -> UnifiedSignal:
        """Convert SignalStack webhook JSON to UnifiedSignal."""
        ...

# parsers/telegram.py
class TelegramParser:
    def parse(self, message: str) -> UnifiedSignal:
        """Parse structured Telegram signal messages."""
        ...
```

---

## 6. GUARDIAN RISK ENGINE — Absolute Veto

The Guardian does NOT care where a signal came from. Collective2, Holly AI, our own code, or a manual entry — ALL pass through the same 10 checks.

```python
@dataclass
class RiskConfig:
    max_position_pct: float = 0.02       # Max 2% of capital per trade
    max_portfolio_risk_pct: float = 0.10  # Max 10% total portfolio at risk
    max_daily_loss_pct: float = 0.03      # 3% daily loss -> auto-shutdown
    max_weekly_loss_pct: float = 0.05     # 5% weekly loss -> pause 48h
    max_correlation: float = 0.70         # Block trades correlated >70%
    max_single_stock_pct: float = 0.15    # Max 15% in one underlying
    max_options_pct: float = 0.30         # Max 30% in options
    max_futures_margin_pct: float = 0.25  # Max 25% margin used for futures
    min_cash_reserve_pct: float = 0.20    # Always keep 20% cash
    require_stop_loss: bool = True        # Every trade MUST have stop-loss
    max_concurrent_positions: int = 15    # Position count limit (up from 10)
    max_signals_per_source_day: int = 20  # Prevent runaway signal sources
    
    # Source-specific limits
    max_c2_allocation_pct: float = 0.30   # Max 30% to Collective2 signals
    max_holly_allocation_pct: float = 0.20 # Max 20% to Holly AI signals
    max_internal_allocation_pct: float = 0.40  # Max 40% to our strategies
    max_other_allocation_pct: float = 0.10 # Max 10% to other sources
```

**10 Sequential Checks (every signal, every source):**

```
CHECK  1: Capital available?
          -> Reject if insufficient buying power

CHECK  2: Position size within limits?
          -> Auto-resize if over 2% risk per trade

CHECK  3: Portfolio heat check
          -> Reject if total risk exceeds 10%

CHECK  4: Correlation check
          -> Reject if >70% correlated with existing positions

CHECK  5: Concentration check
          -> Reject if >15% in single underlying

CHECK  6: Daily/weekly P&L check
          -> AUTO-SHUTDOWN if daily >3% or weekly >5% loss

CHECK  7: Cash reserve check
          -> Reject if would drop below 20% cash

CHECK  8: Stop-loss present?
          -> Reject any signal without stop-loss
          -> Auto-add stop-loss if source didn't provide one

CHECK  9: Source allocation check (NEW)
          -> Reject if source has exceeded its allocation limit
          -> Prevent any single source from dominating portfolio

CHECK 10: Compliance check
          -> SNB holding period (if applicable)
          -> Restricted stock list
          -> Max signals per source per day (prevent runaway)
```

**Circuit Breakers:**

| Trigger | Action | Recovery |
|---------|--------|----------|
| Daily loss > 3% | Halt ALL sources, cancel open orders | Manual reset next day |
| Weekly loss > 5% | Pause ALL sources 48 hours | Auto-resume after cooldown |
| Single source loss > 2% in a day | Pause THAT source only | Manual review required |
| Signal flood (>20 from one source/day) | Block source, alert admin | Manual investigation |
| API connection lost | Queue orders, use cached data | Auto-retry with backoff |
| Data feed stale > 60s | Flag positions, alert user | Resume when feed restores |
| Single trade loss > 1.5% | Auto-exit position | Log and alert |
| IBKR connection lost | Halt all new trades immediately | Resume when reconnected |

---

## 7. SIGNAL HUB — New Dashboard Module

The Signal Hub is a new page on the dashboard showing ALL incoming signals from ALL sources in real-time:

```
┌─────────────────────────────────────────────────────────────────┐
│  SIGNAL HUB                                            LIVE [●] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  SOURCE HEALTH                                                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│  │ Collective2  │ │ TradersPost │ │ Holly AI    │              │
│  │ ● Connected  │ │ ● Connected │ │ ● Connected │              │
│  │ 3 signals/d  │ │ 1 signal/d  │ │ 5 signals/d │              │
│  │ 72% win rate │ │ 65% win rate│ │ 68% win rate│              │
│  │ $+1,240 MTD  │ │ $+380 MTD   │ │ $+890 MTD   │              │
│  └─────────────┘ └─────────────┘ └─────────────┘              │
│  ┌─────────────┐ ┌─────────────┐                               │
│  │ SignalStack  │ │ Internal    │                               │
│  │ ● Standby   │ │ ● Active    │                               │
│  │ Backup route │ │ 2 signals/d │                               │
│  │ N/A         │ │ 71% win rate│                               │
│  │ N/A         │ │ $+560 MTD   │                               │
│  └─────────────┘ └─────────────┘                               │
│                                                                 │
│  SIGNAL FEED (Live)                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 14:23:05 │ C2   │ BUY  │ @ESH6  │ 2 ct │ APPROVED ✓  │   │
│  │ 14:21:30 │ Holly│ BUY  │ NVDA   │ 15sh │ APPROVED ✓  │   │
│  │ 14:18:45 │ Own  │ STO  │ TSLA IC│ 1 ct │ APPROVED ✓  │   │
│  │ 14:15:12 │ C2   │ SELL │ META   │ 20sh │ REJECTED ✗  │   │
│  │          │      │      │        │      │ >15% conc.  │   │
│  │ 14:10:00 │ TPst │ BUY  │ AMD    │ 25sh │ APPROVED ✓  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  SOURCE ALLOCATION                                              │
│  Collective2  ████████░░░░░  23% / 30% max                     │
│  Holly AI     █████░░░░░░░░  15% / 20% max                     │
│  Internal     ██████████░░░  32% / 40% max                     │
│  Other        ██░░░░░░░░░░░   5% / 10% max                     │
│  Cash         █████░░░░░░░░  25% / 20% min ✓                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. DATABASE SCHEMA v2 (additions for signal aggregation)

```sql
-- ================================================================
-- NEW: Signal sources table
-- ================================================================

CREATE TABLE signal_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                -- 'collective2', 'traderspost', etc.
    display_name TEXT,                 -- 'Collective2 - ES Momentum Pro'
    source_type TEXT NOT NULL,         -- 'api_poll', 'webhook', 'internal'
    config JSONB NOT NULL,             -- API keys, endpoints, strategy IDs
    is_active BOOLEAN DEFAULT false,
    max_allocation_pct DECIMAL DEFAULT 0.20,
    current_allocation_pct DECIMAL DEFAULT 0.00,
    total_signals INT DEFAULT 0,
    approved_signals INT DEFAULT 0,
    rejected_signals INT DEFAULT 0,
    total_pnl DECIMAL DEFAULT 0.00,
    win_rate DECIMAL DEFAULT 0.00,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ================================================================
-- NEW: Incoming signals log (every signal, approved or rejected)
-- ================================================================

CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    source_id UUID REFERENCES signal_sources(id),
    source_strategy_id TEXT,           -- external strategy identifier
    source_strategy_name TEXT,
    
    -- Signal details
    action TEXT NOT NULL,              -- 'buy', 'sell', 'bto', 'sto', etc.
    asset_class TEXT NOT NULL,         -- 'stock', 'option', 'future'
    symbol TEXT NOT NULL,
    quantity INT NOT NULL,
    order_type TEXT DEFAULT 'market',
    limit_price DECIMAL,
    stop_price DECIMAL,
    stop_loss DECIMAL,
    take_profit DECIMAL,
    
    -- Options/Futures specific
    expiry DATE,
    strike DECIMAL,
    put_call TEXT,
    legs JSONB,
    
    -- Risk engine results
    risk_approved BOOLEAN,
    risk_checks JSONB,                 -- detailed check results
    risk_rejection_reason TEXT,
    
    -- Execution result
    trade_id UUID REFERENCES trades(id),  -- linked trade if executed
    
    -- Raw data
    raw_payload JSONB,                 -- original signal as received
    confidence DECIMAL,
    
    -- Timestamps
    signal_time TIMESTAMPTZ,           -- when source generated it
    received_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ================================================================
-- NEW: Webhook endpoints table
-- ================================================================

CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    source_id UUID REFERENCES signal_sources(id),
    endpoint_token TEXT UNIQUE NOT NULL,  -- unique URL token
    is_active BOOLEAN DEFAULT true,
    last_received_at TIMESTAMPTZ,
    total_received INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ================================================================
-- UPDATED: Trades table (add source tracking)
-- ================================================================

ALTER TABLE trades ADD COLUMN source_id UUID REFERENCES signal_sources(id);
ALTER TABLE trades ADD COLUMN signal_id UUID REFERENCES signals(id);
ALTER TABLE trades ADD COLUMN asset_class TEXT DEFAULT 'stock';

-- ================================================================
-- INDEXES
-- ================================================================

CREATE INDEX idx_signals_user ON signals(user_id, received_at DESC);
CREATE INDEX idx_signals_source ON signals(source_id, received_at DESC);
CREATE INDEX idx_signals_approved ON signals(user_id, risk_approved, received_at DESC);
CREATE INDEX idx_sources_user ON signal_sources(user_id, is_active);
CREATE INDEX idx_webhooks_token ON webhooks(endpoint_token);
CREATE INDEX idx_trades_source ON trades(source_id, created_at DESC);

-- ================================================================
-- RLS for new tables
-- ================================================================

ALTER TABLE signal_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_data" ON signal_sources FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON signals FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON webhooks FOR ALL USING (auth.uid() = user_id);
```

---

## 9. API GATEWAY v2 — New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/signals` | GET | All signals (with source filter) |
| `/api/signals/feed` | WS | Real-time signal feed (WebSocket) |
| `/api/sources` | GET/POST | Manage signal sources |
| `/api/sources/:id/toggle` | PATCH | Enable/disable a source |
| `/api/sources/:id/stats` | GET | Source performance stats |
| `/api/webhook/:token` | POST | Receive external webhook signals |
| `/api/portfolio` | GET | Current positions + P&L by source |
| `/api/trades` | GET/POST | Trade history (filterable by source) |
| `/api/strategies` | GET/PATCH | Internal strategy config |
| `/api/risk` | GET | Current risk metrics |
| `/api/risk/allocation` | GET | Source allocation breakdown |
| `/api/market/quote/:symbol` | GET | Real-time quote (cached) |
| `/api/market/options/:symbol` | GET | Options chain + Greeks |
| `/api/execute` | POST | Submit order (paper/live) |
| `/api/kill-switch` | POST | Emergency halt ALL activity |
| `/api/kill-switch/:source` | POST | Halt specific source only |

---

## 10. HOSTING ARCHITECTURE

```
FRONTEND (Static)
├── katherina.azurenexus.com        (GitHub Pages)
├── React 18 + Vite + TypeScript
└── Cost: FREE

BACKEND — API + DB (Serverless)
├── Supabase Cloud (PostgreSQL + Edge Functions + Auth + Realtime)
├── Upstash Redis (signal queue + cache)
└── Cost: FREE tier (up to paid if needed ~$25/mo)

TRADING ENGINE (Always-On VPS)
├── Hetzner Cloud CPX21 (Ashburn, VA)
│   ├── 3 AMD vCPUs, 4GB RAM, 80GB NVMe
│   ├── Ubuntu 24.04 LTS
│   ├── IBKR Gateway (headless via IBC)
│   ├── Python trading engine (systemd)
│   │   ├── Signal poller (Collective2 API)
│   │   ├── Webhook listener (Flask/FastAPI)
│   │   ├── Strategy engine (internal strategies)
│   │   ├── Guardian risk engine
│   │   ├── Execution manager
│   │   └── Notification service (Telegram + email)
│   ├── UFW firewall (whitelist IPs only)
│   ├── SSH key auth only
│   └── Automated daily backups
└── Cost: ~$7/mo

SIGNAL PROVIDERS (External SaaS)
├── Collective2          $40-400/mo (2 strategies)
├── TradersPost          $0-49/mo
├── Trade Ideas Premium  $228/mo
├── SignalStack           $0-30/mo (backup)
└── ORATS + data APIs    $99-230/mo
```

**Total monthly cost breakdown:**

| Component | Phase 1 (Paper) | Phase 2 (Pre-Live) | Phase 3 (Production) |
|-----------|-----------------|--------------------|--------------------|
| Hetzner VPS | $0 (local) | $7 | $7 |
| Supabase | $0 | $0 | $25 |
| Collective2 (2 strategies) | $0 (paper) | $100 | $200 |
| TradersPost | $0 | $0 | $49 |
| Trade Ideas | $0 | $0 | $228 |
| SignalStack | $0 | $0 | $30 |
| ORATS | $0 | $99 | $99 |
| Alpha Vantage | $0 | $50 | $50 |
| FMP | $14 | $14 | $49 |
| **TOTAL** | **$14/mo** | **$270/mo** | **$737/mo** |

vs Bloomberg Terminal: **$2,000-2,500/mo**
vs Perplexity Finance: **$200/mo** (can't trade)

---

## 11. PROJECT FILE STRUCTURE v2

```
katherina-trader/
│
├── frontend/                         # React app
│   ├── src/
│   │   ├── components/
│   │   │   ├── dashboard/            # Portfolio, P&L widgets
│   │   │   ├── signal-hub/           # NEW: Signal feed, source health
│   │   │   ├── strategies/           # Strategy cards, toggles
│   │   │   ├── sources/              # NEW: Signal source management
│   │   │   ├── trades/               # Trade journal (filterable by source)
│   │   │   ├── risk/                 # Risk dashboard + allocation bars
│   │   │   ├── market/               # Scanner, charts
│   │   │   ├── backtest/             # Backtest lab
│   │   │   ├── alerts/               # Alert center
│   │   │   └── shared/               # Layout, buttons, modals
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── lib/
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── ...
│
├── backend/                          # Python trading engine
│   ├── signals/                      # NEW: Signal aggregation
│   │   ├── normalizer.py             # All formats → UnifiedSignal
│   │   ├── parsers/
│   │   │   ├── collective2.py        # C2 API signal parser
│   │   │   ├── traderspost.py        # TradersPost webhook parser
│   │   │   ├── trade_ideas.py        # Holly AI alert parser
│   │   │   ├── signalstack.py        # SignalStack webhook parser
│   │   │   └── telegram.py           # Telegram message parser
│   │   ├── pollers/
│   │   │   └── c2_poller.py          # Poll C2 API every 5s
│   │   └── webhook_server.py         # FastAPI webhook receiver
│   │
│   ├── strategies/                   # Internal strategies
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── iron_condor.py
│   │   ├── momentum.py
│   │   ├── covered_calls.py
│   │   └── dividend_capture.py
│   │
│   ├── risk/                         # Guardian risk engine
│   │   ├── engine.py                 # 10 checks + source allocation
│   │   ├── position_sizer.py
│   │   ├── circuit_breaker.py
│   │   └── source_limiter.py         # NEW: Per-source allocation limits
│   │
│   ├── execution/
│   │   ├── manager.py
│   │   ├── ibkr_client.py
│   │   └── paper_sim.py
│   │
│   ├── data/
│   │   ├── aggregator.py
│   │   ├── providers/
│   │   │   ├── ibkr.py
│   │   │   ├── polygon.py
│   │   │   ├── alpha_vantage.py
│   │   │   ├── orats.py
│   │   │   └── fmp.py
│   │   └── cache.py
│   │
│   ├── notifications/
│   │   ├── telegram.py
│   │   └── email.py
│   │
│   ├── config/
│   │   ├── settings.py
│   │   └── risk_defaults.py
│   │
│   ├── tests/
│   │   ├── test_signals/             # NEW: Signal parser tests
│   │   ├── test_strategies/
│   │   ├── test_risk/
│   │   └── test_execution/
│   │
│   ├── requirements.txt
│   └── main.py
│
├── supabase/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql
│   │   ├── 002_rls_policies.sql
│   │   ├── 003_indexes.sql
│   │   ├── 004_signal_sources.sql    # NEW
│   │   ├── 005_signals_table.sql     # NEW
│   │   └── 006_webhooks_table.sql    # NEW
│   ├── functions/
│   │   ├── portfolio/
│   │   ├── trades/
│   │   ├── strategies/
│   │   ├── signals/                  # NEW
│   │   ├── sources/                  # NEW
│   │   ├── webhook/                  # NEW: Webhook receiver
│   │   ├── execute/
│   │   ├── market/
│   │   ├── alerts/
│   │   └── kill-switch/
│   └── seed.sql
│
├── .github/workflows/
│   ├── deploy-frontend.yml
│   └── run-tests.yml
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SIGNALS.md                    # NEW: Signal source documentation
│   ├── STRATEGIES.md
│   ├── API.md
│   └── RUNBOOK.md
│
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## 12. DEVELOPMENT ROADMAP v2

### Phase 1: Skeleton + Signal Framework (Week 1-2)
- [ ] Create GitHub repo `gummihurdal/katherina-trader`
- [ ] Supabase project + schema migration (including signal tables)
- [ ] React scaffold: auth, dashboard, signal hub, settings
- [ ] Python: UnifiedSignal dataclass + normalizer
- [ ] Python: Webhook receiver (FastAPI)
- [ ] Python: IBKR paper connection test
- [ ] Dashboard with mock signal feed

### Phase 2: First Signal Source — Collective2 (Week 3)
- [ ] C2 API integration (poller + parser)
- [ ] Guardian risk engine (all 10 checks)
- [ ] Paper execution via IBKR
- [ ] Signal Hub showing live C2 signals
- [ ] Source health monitoring
- [ ] Telegram notifications

### Phase 3: Internal Strategies (Week 4-5)
- [ ] Iron Condor strategy (Mihail's approach)
- [ ] Momentum strategy (MACD + RSI)
- [ ] Strategy control panel
- [ ] Backtest engine
- [ ] TradingView Lightweight Charts on dashboard

### Phase 4: More Signal Sources (Week 6-7)
- [ ] TradersPost webhook integration
- [ ] Trade Ideas / Holly AI integration
- [ ] SignalStack as backup router
- [ ] Source allocation limits in Guardian
- [ ] Source performance comparison dashboard

### Phase 5: Polish + Risk (Week 8)
- [ ] Full trade journal with source filtering
- [ ] Risk dashboard with allocation bars
- [ ] Circuit breakers (per-source + global)
- [ ] Daily summary emails
- [ ] Kill switch (global + per-source)

### Phase 6: Go Live (Week 9+)
- [ ] 30 days paper with all sources running
- [ ] Performance review per source
- [ ] Separate Supabase PROD project
- [ ] 2FA for live mode activation
- [ ] IBKR port 7496 → 7497
- [ ] Start with minimum positions
- [ ] Weekly reviews with Katherina

---

## 13. NON-NEGOTIABLE RULES

```
 1. NEVER store API keys in frontend code
 2. NEVER deploy to live without 30 days paper testing
 3. NEVER trade without a stop-loss (auto-add if source omits one)
 4. NEVER exceed risk limits — no override for trader role
 5. NEVER let any single signal source exceed its allocation limit
 6. ALWAYS log EVERY signal (approved AND rejected) with full context
 7. ALWAYS have kill switch accessible (global + per-source)
 8. ALWAYS separate dev/prod Supabase environments
 9. ALWAYS validate every incoming webhook (token + schema)
10. GUARDIAN HAS FINAL SAY — no source bypasses risk checks
11. PAPER FIRST — every new source does 30 days paper before live
12. NO BLIND TRUST — even audited sources get risk-checked
```

---

## 14. SECURITY ADDITIONS FOR SIGNAL AGGREGATION

```
WEBHOOK SECURITY
├── Unique endpoint token per source (UUID)
├── IP whitelist for known signal providers
├── Zod schema validation on all webhook payloads
├── Rate limiting per webhook endpoint
├── HMAC signature verification (where provider supports it)
└── All webhook payloads logged to signals table

SOURCE ISOLATION
├── Per-source allocation limits (cannot exceed assigned %)
├── Per-source daily signal limits (prevent flood attacks)
├── Per-source kill switch (disable without affecting others)
├── Source performance tracked independently
└── Underperforming sources auto-flagged for review

API KEY MANAGEMENT
├── C2 API key: encrypted in Supabase Vault
├── TradersPost API key: encrypted in Supabase Vault
├── Trade Ideas API key: encrypted in Supabase Vault
├── SignalStack API key: encrypted in Supabase Vault
├── All keys rotatable without code changes
└── Keys NEVER in environment variables on frontend
```

---

*Architecture v2.0 — Signal Aggregator Edition*
*Designed for katherina.azurenexus.com*
*Last updated: March 3, 2026*
