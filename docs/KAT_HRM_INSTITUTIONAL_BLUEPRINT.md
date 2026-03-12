# KAT-HRM — Institutional Quality Blueprint
**Status:** Architecture Phase | **Date:** March 2026  
**Allocation:** $20,000 USD | **Target:** Professional Hedge Fund-Grade System

---

## Vision

KAT-HRM (High Risk Module) is designed to operate at institutional quality — not as a retail system that "tries to beat the market," but as a disciplined, data-driven autonomous system with a clear mandate: **compound wealth systematically with controlled risk.**

The $20,000 allocation is real capital. Every architectural decision must reflect that.

---

## 1. HISTORICAL DATA ARCHITECTURE

> *The quality of your data ceiling determines the quality of your alpha.*

| Layer | Source | Est. Monthly Cost | What It Provides |
|---|---|---|---|
| Futures tick data | [Databento](https://databento.com) | $50–200 | MES, MNQ, CL, GC — real bid/ask spreads, full depth |
| Equities (sub-minute) | [Polygon.io](https://polygon.io) | $79 | Full tape, all US equities |
| Alternative data | [Nasdaq Data Link](https://data.nasdaq.com) | $50–500 | Shipping rates, commodities, COT reports |
| Macro indicators | [FRED API](https://fred.stlouisfed.org) | Free | Interest rates, CPI, PMI, yield curve |
| Earnings / events | [Intrinio](https://intrinio.com) | ~$50 | Earnings surprise, guidance, analyst revisions |

**Minimum viable stack:** Databento + Polygon = ~$130/month. Institutional-grade tick data from day one.

### Data Storage
- PostgreSQL (existing) — tick data partitioned by symbol/date
- TimescaleDB extension recommended for time-series performance
- 5-year backfill target on all primary instruments
- Daily automated ingestion pipeline via Hetzner cron

---

## 2. ML ARCHITECTURE — Upgrade Path

### Current State
- Single PPO agent (Stable-Baselines3)
- 18 symbols, 14,958 bars
- DummyVecEnv, MLflow tracking

### Target Architecture (Institutional)

```
┌─────────────────────────────────────────────────────────┐
│                    SIGNAL PIPELINE                       │
│                                                          │
│  Layer 1 — REGIME DETECTION                             │
│    └── LSTM Classifier                                   │
│         Inputs: VIX, yield curve, momentum, breadth     │
│         Output: Bull / Bear / Sideways / High-Vol        │
│                                                          │
│  Layer 2 — SIGNAL ENSEMBLE                              │
│    ├── PPO Agent (current — improve, don't replace)     │
│    ├── XGBoost (pattern features, tabular alpha)        │
│    ├── Temporal Fusion Transformer (price forecasting)  │
│    └── Sentiment Signal (news flow + options skew)      │
│                                                          │
│  Layer 3 — POSITION SIZING                              │
│    └── Kelly Criterion (fractional, dynamic)            │
│         f* = (edge × odds - loss_prob) / odds           │
│         Capped at 25% Kelly (conservative fraction)     │
│                                                          │
│  Layer 4 — RISK GATE (hard veto layer)                  │
│    ├── Max drawdown breach → halt                       │
│    ├── Correlation limit → reject new positions         │
│    ├── Overnight exposure cap                           │
│    └── Earnings blackout enforcement                    │
└─────────────────────────────────────────────────────────┘
```

### Training Protocol
- **Walk-forward validation** (not just backtesting) — train on N years, validate on next 6 months, roll forward
- Minimum 3 market regime cycles in training data
- Out-of-sample test set held sacred — never touched during development
- Hyperparameter tuning via Optuna

---

## 3. EXECUTION QUALITY

> Retail loses to institutions primarily on execution, not alpha.

### Latency Target
- Hetzner Frankfurt → IBKR Frankfurt gateway: ~1ms round trip
- Never deploy from a location outside same city as exchange gateway

### Execution Upgrades
| Current | Target |
|---|---|
| REST API polling | WebSocket streaming (real-time fills) |
| Market orders | Limit-first → TWAP for large fills |
| No slippage tracking | Every fill logged: expected vs actual |
| Fixed order size | Smart sizing based on liquidity |

### Fill Quality KPI
- Target: <0.05% average slippage per trade
- Alert threshold: >0.15% slippage on any single fill
- Weekly slippage report — if drifting up, execution algo needs tuning

---

## 4. HRM CAPITAL CONSTITUTION

> The $20,000 needs a constitution — hard rules that cannot be overridden by the model.

```
CAPITAL STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Allocation:          $20,000
Hard Floor (auto-halt):    $14,000   (30% max drawdown from peak)
Max Single Position:        $4,000   (20% of capital)
Max Correlated Exposure:    $8,000   (40% in any one direction)

DAILY LIMITS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Max Daily Loss:               $600   (3% of capital)
Max Daily Trades:               20   (prevents overtrading)
Position Review if loss >$300:       (human in loop)

LEVERAGE (Futures only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Max Leverage:                   3x   → $60,000 buying power
Overnight leverage:             1x   → reduce before close
Earnings window:            Reduce to 0.5x 48h around major events

INSTRUMENT UNIVERSE (HRM)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Primary:   MES  — Micro E-mini S&P 500
Secondary: MNQ  — Micro Nasdaq-100
Tertiary:  MCL  — Micro WTI Crude (geo-event plays)
Hedge:     MGC  — Micro Gold (risk-off / safe haven)
```

### Auto-Halt Triggers (system pauses, human reviews)
1. Daily loss > $600
2. Equity < $14,000
3. 3 consecutive losing days
4. Slippage > 0.20% average over past 50 trades
5. Model confidence score below threshold for >4 hours

---

## 5. PERFORMANCE TARGETS

| Metric | Retail Average | Hedge Fund Standard | **KAT-HRM Target** |
|---|---|---|---|
| Sharpe Ratio | 0.5 – 0.8 | > 1.5 | **> 1.2** |
| Max Drawdown | 20 – 40% | < 10% | **< 12%** |
| Win Rate | 45 – 55% | 50 – 60% | **> 52%** |
| Profit Factor | 1.1 – 1.3 | > 1.5 | **> 1.4** |
| Annualized Return | 10 – 20% | 15 – 30% | **> 25%** |
| Calmar Ratio | < 1.0 | > 2.0 | **> 1.5** |

### Go-Live Criteria (all must be met)
- [ ] Sharpe > 1.0 on paper trading
- [ ] Max drawdown < 15% over 8-week paper period
- [ ] 8 full weeks of paper trading completed
- [ ] Execution pipeline tested with 500+ simulated fills
- [ ] Auto-halt triggers tested and verified

---

## 6. BUILD ROADMAP

```
PHASE 1 — DATA FOUNDATION            (Weeks 1–2)
├── Subscribe: Databento + Polygon.io
├── Backfill: 5 years MES, MNQ, MCL, MGC tick data
├── Build: Automated daily ingestion pipeline
└── Validate: Data integrity checks, gap detection

PHASE 2 — MODEL UPGRADE              (Weeks 2–4)
├── Implement: LSTM regime classifier
├── Add: XGBoost ensemble layer
├── Retrain: Full PPO on expanded tick dataset
├── Implement: Walk-forward validation harness
└── Baseline: Establish out-of-sample benchmark

PHASE 3 — EXECUTION ENGINE           (Weeks 4–6)
├── Upgrade: REST → WebSocket IBKR connection
├── Build: Smart order routing (limit-first, TWAP)
├── Build: Slippage tracking + reporting
└── Test: 500+ simulated fills for quality

PHASE 4 — RISK INFRASTRUCTURE        (Weeks 5–7)
├── Implement: All auto-halt triggers
├── Build: Daily performance dashboard
├── Build: Regime-aware position sizing (Kelly)
└── Stress test: Replay 2020 COVID crash, 2022 bear

PHASE 5 — PAPER TRADING HRM          (Weeks 7–15)
├── Full paper run: 8 weeks minimum
├── Daily log: P&L, drawdown, Sharpe, slippage
├── Human review: Weekly, any halt trigger event
└── Red flag protocol: 3 consecutive losses → full review

PHASE 6 — LIVE HRM DEPLOYMENT
├── Start: $5,000 allocation (25% of target)
├── Scale to $10,000 at: 4 weeks proven metrics
├── Scale to $20,000 at: 8 weeks proven metrics
└── Review: Monthly — capital can be pulled anytime
```

---

## 7. MONITORING & REPORTING

### Daily (automated)
- P&L vs benchmark (SPY)
- Drawdown from peak
- Slippage report
- Regime classification log
- Fill quality summary

### Weekly (human review)
- Full performance attribution
- Model confidence trends
- Any halt events reviewed
- Data pipeline health check

### Monthly
- Sharpe, Calmar, Sortino recalculated on rolling window
- Walk-forward model retraining
- Capital allocation review

---

## 8. NEXT IMMEDIATE STEPS

When Stage 1 training completes:

1. **Evaluate results** — Sharpe, max drawdown, win rate from MLflow
2. **Identify biggest gap** — Is it data quality, model capacity, or overfitting?
3. **Subscribe Databento** — Start with $125 free credit already available
4. **Begin LSTM regime classifier** — This alone should improve performance 15–25%

---

## Notes

- SNB compliance: KAT-HRM operates only on non-CHF instruments. Futures (MES, MNQ, MCL, MGC) are USD-denominated. Compliant by design.
- The 30-day holding period applies to equity positions, not futures (futures are exempt as derivatives). Confirm with SNB compliance team.
- All capital deployed through IBKR Switzerland (TWS).

---

*Document maintained in: `gummihurdal/katherina-trader/docs/KAT_HRM_INSTITUTIONAL_BLUEPRINT.md`*  
*Last updated: March 2026*
