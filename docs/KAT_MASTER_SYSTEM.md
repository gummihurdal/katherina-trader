# KAT — Master System Blueprint
**Version:** 1.0 | **Date:** March 2026  
**Classification:** Private — Proprietary Trading System

---

## MISSION STATEMENT

KAT is a fully autonomous, institutional-grade algorithmic trading system built for **aggressive, systematic wealth building**. It operates with zero emotional bias, lightning execution, and professional risk discipline across all major asset classes.

KAT does not guess. KAT does not hope. KAT executes.

---

## CAPITAL STRUCTURE

```
┌─────────────────────────────────────────────────────────┐
│                   KAT CAPITAL MODULES                    │
│                                                          │
│  MODULE A — STANDARD (SRM)         $100,000             │
│  ├── Primary wealth compounding engine                   │
│  ├── Diversified multi-asset deployment                  │
│  ├── Max drawdown tolerance: 15%                         │
│  └── Target return: 25–40% annually                      │
│                                                          │
│  MODULE B — HIGH RISK (HRM)         $20,000             │
│  ├── Aggressive alpha capture                            │
│  ├── High-conviction concentrated bets                   │
│  ├── Max drawdown tolerance: 30%                         │
│  └── Target return: 50–100%+ annually                    │
│                                                          │
│  TOTAL DEPLOYMENT:                 $120,000             │
│  HARD FLOOR — FULL HALT:            $84,000             │
└─────────────────────────────────────────────────────────┘
```

---

## ASSET CLASS UNIVERSE

KAT trades across **seven asset classes simultaneously**:

### 1. EQUITIES — US & Global
- S&P 500 universe (full 500 when signals justify)
- Nasdaq 100 tech leaders
- European equities (DAX, SMI components)
- **Pharmaceutical sector — specialist focus (see Section 6)**
- ETFs as tactical instruments (sector rotation, hedging)
- Small/mid cap momentum plays (trend-ahead strategy)

### 2. FUTURES
- MES — Micro E-mini S&P 500 (primary index instrument)
- MNQ — Micro Nasdaq-100
- MCL — Micro WTI Crude Oil (geopolitical plays)
- MGC — Micro Gold (risk-off, safe haven)
- ZB — US Treasury Bonds (macro positioning)
- SI — Silver (commodity momentum)
- HG — Copper (global growth indicator)

### 3. OPTIONS
- Single-name options on high-conviction positions
- Iron Condors — premium harvesting in range-bound markets
- Straddles/Strangles — pre-earnings volatility plays
- LEAPS — long-term thesis expression (pharma, energy)
- Put protection — systematic tail-risk hedging
- Covered calls on core equity positions (yield enhancement)

### 4. PHARMACEUTICALS — Specialist Domain
*(Full detail in Section 6)*
- Clinical trial event trading (Phase 2/3 readouts)
- FDA calendar — PDUFA dates, advisory committees
- Biotech M&A arbitrage
- Rare disease / orphan drug momentum
- Short plays on failed trial reversals

### 5. INDICES & MACRO
- SPX, NDX, DAX, FTSE, Nikkei exposure
- Sector rotation (tech → energy → defensive cycling)
- Yield curve positioning (2s10s spread trades)
- VIX volatility regime trading

### 6. CRYPTOCURRENCY (Selective)
- BTC and ETH as macro/risk-on indicators
- Crypto as signal for risk appetite — informs equity positioning
- Direct trading only on strong regime signals

### 7. FOREX (Non-CHF only — SNB Compliance)
- USD/EUR, USD/JPY, USD/GBP, USD/NOK
- Used primarily for hedge and macro expression
- **CHF pairs: permanently disabled — SNB compliance**

---

## SYSTEM ARCHITECTURE

```
┌──────────────────────────────────────────────────────────────┐
│                     KAT CORE ENGINE                           │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │              DATA INGESTION LAYER                    │     │
│  │  Tick data → News → Macro → Options flow →          │     │
│  │  Dark pool prints → Satellite → Shipping AIS        │     │
│  └────────────────────┬────────────────────────────────┘     │
│                       │                                       │
│  ┌────────────────────▼────────────────────────────────┐     │
│  │              SIGNAL GENERATION                       │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │     │
│  │  │  Regime  │ │Technical │ │Sentiment │ │ Event  │ │     │
│  │  │Classifier│ │  Alpha   │ │  Alpha   │ │ Alpha  │ │     │
│  │  │  (LSTM)  │ │(XGBoost) │ │  (NLP)   │ │(Pharma)│ │     │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │     │
│  │       └────────────┴────────────┴────────────┘      │     │
│  │                    ENSEMBLE COMBINER                 │     │
│  └────────────────────┬────────────────────────────────┘     │
│                       │                                       │
│  ┌────────────────────▼────────────────────────────────┐     │
│  │              RISK & SIZING ENGINE                    │     │
│  │  Kelly Criterion → Correlation Filter →              │     │
│  │  Drawdown Gate → Regime Overlay → Final Size        │     │
│  └────────────────────┬────────────────────────────────┘     │
│                       │                                       │
│  ┌────────────────────▼────────────────────────────────┐     │
│  │              EXECUTION ENGINE                        │     │
│  │  Smart Order Routing → TWAP/VWAP →                  │     │
│  │  Slippage Monitor → Fill Quality Tracker            │     │
│  └────────────────────┬────────────────────────────────┘     │
│                       │                                       │
│  ┌────────────────────▼────────────────────────────────┐     │
│  │              IBKR TWS (LIVE EXECUTION)               │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

---

## ML ENGINE — 5 LAYER INTELLIGENCE STACK

### Layer 1 — Regime Classifier (LSTM)
**Purpose:** Tell every other model what kind of market we are in  
**Inputs:** VIX term structure, yield curve slope, advance/decline, momentum factors, credit spreads  
**Outputs:** Bull Trending / Bear Trending / Sideways / High Volatility / Crisis  
**Why it matters:** A signal that works in a bull market kills you in a bear. Regime awareness is non-negotiable.

### Layer 2 — Technical Alpha (XGBoost Ensemble)
**Purpose:** Pattern recognition at institutional scale  
**Inputs:** 200+ engineered features — price action, volume profile, order flow, microstructure  
**Outputs:** Directional signal + confidence score per instrument  
**Edge:** Trained on tick data, not daily bars. Sees what retail cannot.

### Layer 3 — Price Forecasting (Temporal Fusion Transformer)
**Purpose:** Multi-horizon price and volatility prediction  
**Inputs:** Raw prices, macro features, calendar effects, cross-asset correlations  
**Outputs:** Expected price distribution 1h, 4h, 1d, 1w ahead  
**Edge:** Transformer architecture captures long-range dependencies humans miss

### Layer 4 — Sentiment & Flow Alpha (NLP + Options)
**Purpose:** Front-run institutional positioning  
**Inputs:** News wire (real-time), SEC filings, earnings transcripts, Reddit/X unusual volume, options unusual activity, dark pool prints  
**Outputs:** Sentiment score, flow direction, conviction level  
**Edge:** Spots narrative shifts 6–48 hours before price moves

### Layer 5 — Pharmaceutical Event Model (Specialist)
**Purpose:** Trade binary biotech/pharma events with edge  
**Inputs:** ClinicalTrials.gov, FDA calendar, trial design analysis, historical analog outcomes, short interest  
**Outputs:** Probability-weighted entry, sizing, and exit for every FDA event  
**Edge:** Systematic where everyone else is guessing

### Sizing Engine — Fractional Kelly Criterion
```
f* = (p × b - q) / b
where:
  p = win probability (model output)
  q = loss probability (1 - p)
  b = win/loss ratio

Apply 25% Kelly fraction for safety
Adjust for: regime confidence, current drawdown, correlation to existing book
```

---

## SIGNAL SUBSCRIPTIONS — HIGH VALUE DATA

Professional edge requires professional data. Estimated monthly investment: **$500–1,500**

| Category | Service | Monthly Cost | Signal Type |
|---|---|---|---|
| **Tick Data** | Databento | $125–200 | MES, MNQ, CL, GC full depth |
| **Equities** | Polygon.io | $79 | Sub-minute bars, full US tape |
| **Options Flow** | ORATS | $100–400 | Volatility surface, unusual activity |
| **Pharma Events** | BioPharma Catalyst | $99 | FDA calendar, trial readouts |
| **Pharma Options** | Holley Finance | $150 | Biotech event options signals |
| **Macro** | FRED API | Free | Rates, CPI, PMI, yield curve |
| **Alternative** | Nasdaq Data Link | $50–300 | COT reports, shipping rates |
| **News Wire** | Benzinga Pro API | $99 | Real-time news + event flags |
| **Dark Pool** | Unusual Whales API | $50–100 | Institutional flow |
| **Earnings** | Intrinio | $50 | Surprise data, guidance |
| **Sentiment** | StockTwits API | $49 | Retail sentiment gauge |

**Total estimated:** ~$850–1,500/month → Recoverable in a single good trade

---

## PHARMACEUTICAL TRADING MODULE — SPECIALIST EDGE

Pharma/biotech is one of the few remaining markets with true information asymmetry for systematic traders. KAT treats it as a specialist sub-system.

### Event Calendar System
- Automated scraping of ClinicalTrials.gov (daily)
- FDA PDUFA dates tracked 12 months forward
- Advisory committee (AdCom) dates flagged
- European EMA calendar integrated

### Trade Types

**1. Phase 3 Readout Plays**
- Enter 3–6 weeks before data readout
- Size based on: trial design quality, historical analogs, current valuation, short interest
- Options structure: Long straddle if IV not yet inflated, directional if edge clear
- Exit: Day before readout (sell vol) or hold through with defined risk

**2. FDA PDUFA Trades**
- Calendar-driven, fully systematic
- Historical approval rate by indication, PDUFA history for that drug
- Typical: Long calls 60 days out, close 1 week before decision

**3. Failed Trial Short**
- Identify companies with single-asset pipelines
- Binary event: If trial fails → 50–90% stock drop
- Put options before readout for defined risk

**4. M&A Arbitrage**
- Biotech acquisition targets trade at discount to deal price
- Systematic: Enter on announced deal, capture spread
- Risk: Deal break — hedge with puts

**5. Orphan Drug / Rare Disease Momentum**
- FDA grants priority review → stock re-rates
- Often 6–18 month run after designation
- LEAPS for long-duration thesis expression

---

## BACKTESTING ENGINE

No live trading without rigorous backtesting. KAT uses **three validation layers**:

### Layer 1 — Historical Simulation
- Minimum 10 years of data per strategy
- Tick-level simulation (not daily bars — too optimistic)
- Transaction costs: commissions + realistic slippage model
- Survivorship bias corrected (include delisted stocks)

### Layer 2 — Walk-Forward Validation
```
Train:     Jan 2014 – Dec 2018 (5 years)
Test:      Jan 2019 – Jun 2019 (6 months out-of-sample)
           ↓
Train:     Jul 2014 – Jun 2019
Test:      Jul 2019 – Dec 2019
           ↓
Continue rolling forward...
           ↓
Final OOS: Jan 2024 – Present
```
If a strategy doesn't survive walk-forward, it doesn't go live. Period.

### Layer 3 — Stress Testing
- Replay: 2008 Financial Crisis
- Replay: 2020 COVID crash (40% drop in 30 days)
- Replay: 2022 Bear Market (rates rising, growth collapsing)
- Replay: 2010 Flash Crash
- Monte Carlo: 10,000 simulated paths

### Backtest Performance Gate (minimum to proceed to paper trading)
- Sharpe Ratio > 1.0
- Max Drawdown < 20%
- Profit Factor > 1.3
- Positive in at least 7 of 10 years tested
- Survives all 4 stress scenarios above

---

## RISK MANAGEMENT CONSTITUTION

### SRM ($100,000) Rules
```
Max single position:        $10,000  (10%)
Max sector concentration:   $30,000  (30%)
Max daily loss:              $2,000  (2%)
Max weekly loss:             $5,000  (5%)
Drawdown halt trigger:      $15,000  (15% from peak)
Leverage — equities:            1.5x
Leverage — futures:               3x
Overnight risk limit:            60% of normal size
```

### HRM ($20,000) Rules
```
Max single position:         $4,000  (20%)
Max daily loss:                $600  (3%)
Drawdown halt trigger:       $6,000  (30% from peak)
Leverage — futures:               4x
Overnight risk limit:            40% of normal size
Earnings blackout:        -50% size 48h around events
```

### Universal Auto-Halt Triggers
1. Daily loss exceeds module limit → halt module, alert human
2. 3 consecutive losing days → reduce size 50%, human review
3. Drawdown reaches halt level → full stop, mandatory review
4. Execution slippage > 0.20% rolling average → execution audit
5. Market circuit breakers → halt all activity
6. Model confidence below threshold 4+ hours → defensive mode

### Correlation Control
- Max 2 highly correlated positions simultaneously
- If BTC drops >10% in 1h → reduce risk across book
- If VIX spikes >30% intraday → all new positions halted

---

## EXECUTION INFRASTRUCTURE

### Hardware (Current)
- **Primary server:** Hetzner EX63 (Frankfurt) — model training, signal generation
- **Execution:** Co-located as close as possible to IBKR Frankfurt gateway
- **Backup:** Local machine with manual override capability always available

### Speed Stack
- WebSocket connections for real-time data (not REST polling)
- Pre-computed signal updates every 100ms
- Order submission target latency: < 5ms from signal to wire
- Heartbeat monitoring — dead-man switch if server goes silent

### Connectivity
- IBKR TWS (primary) — stocks, options, futures
- IBKR FIX gateway for direct order routing (upgrade path)
- Redundant internet connection (primary + 4G backup)

### Data Pipeline
```
Databento/Polygon WebSocket
        ↓
  Redis (hot cache, <1ms lookup)
        ↓
  Signal Engine (Python, C extension for speed-critical paths)
        ↓
  PostgreSQL (persistent store, analytics)
        ↓
  MLflow (experiment tracking)
        ↓
  Dashboard (real-time monitoring)
```

---

## TREND-AHEAD INTELLIGENCE — SPOTTING BEFORE THE CROWD

KAT's edge is not just execution — it's **information timing**. Several modules are dedicated to finding signals before they become consensus:

### Satellite & Alternative Data
- Shipping AIS data (VLCC routes → crude supply signals)
- Port activity indicators
- Energy infrastructure satellite monitoring

### Regulatory Intelligence
- SEC 13F filings — institutional positioning (45-day lag, but useful)
- Form 4 — insider buying/selling in real time
- FDA Complete Response Letters — often market-moving, automated monitoring

### Social & Narrative
- Unusual options activity (Unusual Whales) — often precedes moves 2–5 days
- Reddit WallStreetBets unusual volume → contrarian or momentum signal
- Twitter/X financial community sentiment shift detection

### Cross-Asset Leading Indicators
- Copper as global growth leading indicator → equity positioning
- High yield credit spreads widening → reduce equity risk
- Dollar strength → emerging market pressure signal
- Yield curve inversion depth → recession probability scoring

---

## PERFORMANCE TARGETS

| Metric | Retail | Hedge Fund | **KAT Target** |
|---|---|---|---|
| Sharpe Ratio | 0.5–0.8 | > 1.5 | **> 1.3** |
| Sortino Ratio | < 1.0 | > 2.0 | **> 1.8** |
| Calmar Ratio | < 0.5 | > 2.0 | **> 1.5** |
| Max Drawdown | 20–40% | < 10% | **< 12% (SRM) / <25% (HRM)** |
| Win Rate | 45–55% | 50–60% | **> 53%** |
| Profit Factor | 1.1–1.3 | > 1.5 | **> 1.5** |
| Annualized Return | 10–20% | 15–30% | **> 35% (SRM) / >60% (HRM)** |
| Avg Hold Time | varies | varies | **Minutes to weeks (adaptive)** |

### Wealth Building Projection (Conservative)
```
Year 1:  $120,000 → $168,000  (+40%)
Year 2:  $168,000 → $243,600  (+45%)
Year 3:  $243,600 → $365,400  (+50%)
Year 5:  $365,400 → $780,000+ (compounding effect)
```
*Based on 40–50% annual return target. Not guaranteed. Based on achieving performance targets.*

---

## MONITORING DASHBOARD

### Real-Time (always visible)
- Live P&L by module and position
- Drawdown from peak (live)
- Current regime classification
- Open positions with entry, current, stop
- Slippage tracker (rolling 50 trades)
- System heartbeat and connectivity status

### Daily Report (automated, sent to phone)
- P&L vs benchmark
- Sharpe (rolling 90 days)
- Top 3 winners / losers
- Any halt triggers fired
- Tomorrow's key events (FDA dates, earnings, macro)

### Weekly Review
- Full attribution — what worked, what didn't
- Model confidence trends
- Data pipeline health
- Strategy parameter review

---

## BUILD ROADMAP — FULL SYSTEM

```
PHASE 1 — FOUNDATION          Q2 2026 (April–May)
├── Data: Databento + Polygon subscriptions
├── Pipeline: Automated tick ingestion to PostgreSQL
├── Backtest: Full engine with walk-forward harness
└── Baseline: Current KAT results as benchmark

PHASE 2 — INTELLIGENCE        Q2–Q3 2026 (May–July)
├── LSTM regime classifier
├── XGBoost technical alpha model
├── Options flow ingestion (ORATS)
├── Pharma event calendar system
└── Sentiment NLP pipeline (Benzinga + Unusual Whales)

PHASE 3 — EXECUTION           Q3 2026 (July–August)
├── WebSocket IBKR upgrade
├── Smart order routing (TWAP/VWAP)
├── Slippage tracking and reporting
└── Redundancy and failover testing

PHASE 4 — RISK ENGINE         Q3 2026 (August)
├── Kelly position sizing
├── All auto-halt triggers
├── Correlation manager
└── Stress testing harness

PHASE 5 — PAPER TRADING       Q3–Q4 2026 (Sep–Oct)
├── Full paper run: 8 weeks minimum
├── Both SRM and HRM modules
├── Daily review protocol
└── Go/no-go decision based on metrics

PHASE 6 — LIVE DEPLOYMENT     Q4 2026
├── Stage 1: $20k HRM + $25k SRM
├── Scale: Monthly review, capital added on proven metrics
├── Full: $120k deployed by end of Q4 2026
└── Ongoing: Monthly model retraining, strategy evolution
```

---

## WHAT SEPARATES KAT FROM RETAIL

| Retail Trader | KAT |
|---|---|
| Emotional decisions | Zero emotion — rules only |
| Daily bar data | Tick-level data |
| Single strategy | Ensemble of 5+ models |
| Manual execution | Sub-5ms automated execution |
| One asset class | Seven asset classes |
| No regime awareness | LSTM regime classification |
| Hope-based sizing | Kelly Criterion |
| No stress testing | 4 crash scenario replays |
| Reacts to news | Positioned before the crowd |
| No pharma expertise | Dedicated FDA event engine |

---

## SNB COMPLIANCE

- CHF currency pairs: **permanently disabled**
- 30-day holding period: applies to equity positions — documented in trade log
- Futures positions: derivatives — confirm exempt status with SNB compliance
- All positions traded via IBKR Switzerland (TWS)
- Full audit trail maintained in PostgreSQL

---

*KAT Master System Blueprint v1.0*  
*Repository: `gummihurdal/katherina-trader/docs/KAT_MASTER_SYSTEM.md`*  
*This document is the single source of truth for KAT system design.*  
*Updated as architecture evolves.*
