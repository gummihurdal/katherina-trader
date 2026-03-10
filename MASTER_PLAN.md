# KAT v3 Master Plan
*Central reference document — read this at the start of every KAT session.*
*Repo: gummihurdal/katherina-trader*
*Credentials stored in: /root/kat_secrets.txt on the server*

---

## System Overview
KAT v3 is a fully autonomous AI trading system built on a Hetzner EX63 dedicated server.
- **Server IP:** 157.180.104.136
- **SSH:** `ssh -i C:\Users\breka\.ssh\kat-hetzner_key root@157.180.104.136`
- **Repo:** `gummihurdal/katherina-trader`
- **DB:** PostgreSQL 16 @ `127.0.0.1:5432/kat_production` (credentials in kat_secrets.txt)
- **IBKR:** Interactive Brokers Switzerland (TWS desktop, paper trading port 7496)
- **Capital:** 20,000 CHF core + 20,000 USD HRM allocation
- **Compliance:** SNB employee — 30-day minimum holding period, no CHF currency pairs

---

## Architecture

### KAT Core (Conservative)
- Instruments: US stocks, ETFs, futures, indices, FX, European stocks
- Leverage: 1x
- Reward: Sharpe ratio based
- Drawdown limit: 15%
- Position sizing: Kelly criterion

### KAT-HRM (High Risk Module)
- Instruments: Micro futures — MES, MNQ, MCL, MGC
- Capital: $20,000 USD fixed allocation
- Leverage: 3x max
- Reward: Sortino + momentum
- Drawdown limit: 25% hard stop
- **Hard risk controls (non-negotiable):**
  - Stop loss per trade: 2% of $20k = $400
  - Daily loss limit: 5% = $1,000
  - Weekly loss limit: 10% = $2,000
  - Account floor: If balance drops to $14k → full stop, human review required
  - Max open positions: 3 simultaneously
- Profits stay in HRM up to $40k cap — excess transfers to core
- Full audit log of every decision

---

## Data Sources
| Source | Coverage | Cost | Status |
|---|---|---|---|
| Massive.com (Polygon) | US stocks historical | Cancelled Apr 8 2026 | Data ingested |
| Databento | Futures, options, indices, FX | Pay-as-you-go ($125 free credit) | Pending signup |
| yfinance | European stocks | Free | Pending ingest |
| FRED | Macro economic indicators | Free | Future phase |

### Data in PostgreSQL (price_bars table)
- 14,958 bars ingested
- Symbols: SPY, QQQ, AAPL, MSFT, NVDA, TSLA, AMZN, GOOGL, META, JPM, GS, BAC, XLE, XLF, XLK, TLT, GLD, USO
- Date range: 2022-01-01 to 2025-03-01

---

## Quality Optimization Plan

### Phase 1 — Evaluate Stage 1 Baseline
- Check: Total return vs buy-and-hold SPY
- Check: Sharpe ratio (target > 0.5 to proceed)
- Check: Max drawdown (must be < 30%)
- Check: Win rate, average holding period
- If metrics poor → fix architecture before expanding data

### Phase 2 — Data Overhaul
- Extend history to 2000–2025 via Databento
- Add futures (ES, NQ, CL, GC, ZB), indices, FX, European stocks
- Hourly bars instead of daily (10x more signal)
- Remove survivorship bias (include delisted symbols)
- Proper dividend/split adjustments

### Phase 3 — Reward Function Rewrite
Replace raw PnL×10 with:
```python
reward = Sharpe(window=20)
       - 2.0 × max_drawdown
       - 0.001 × num_trades   # overtrading penalty
       + 0.5 × win_rate_bonus
```

### Phase 3b — KAT-HRM Module
- Build after Phase 3 core reward rewrite
- Separate model, separate reward, separate risk parameters
- Shared environment base code — different configuration
- Estimated: 2 weeks additional work on top of core
- HRM reward:
```python
reward = Sortino(window=10)
       - 5.0 × drawdown_beyond_threshold
       + 1.5 × momentum_capture
       - 0.002 × num_trades
```

### Phase 4 — Training Methodology
- Walk-forward validation: train 2000–2020, test 2020–2025
- Lookahead bias audit
- Hyperparameter tuning (learning rate, entropy, clip range)
- Ensemble of 5 models, vote on final signal

### Phase 5 — Risk Controls
- Kelly criterion position sizing
- Max 5% per position
- Sector concentration limits
- Volatility-adjusted sizing
- Hard stop loss built into environment

### Phase 6 — Paper Trading Validation
- 8 weeks minimum before live trading
- Benchmark against SPY weekly
- Sharpe > 1.0 required to go live
- Max drawdown < 15% required to go live
- Must perform across bull + bear + sideways regimes

---

## Go-Live Criteria (Non-Negotiable)
| Metric | Minimum Threshold |
|---|---|
| Sharpe ratio | > 1.0 |
| Max drawdown | < 15% |
| Win rate | > 52% |
| Paper trading period | 8 weeks |
| Market regimes tested | Bull + Bear + Sideways |

---

## Current Training Status
- **Stage 1:** Running — 50M steps, stocks only, DummyVecEnv
- **Screen session:** `screen -r 4105.kat-training`
- **MLflow:** file-based @ `/data/kat/models/mlflow`
- **Est. completion:** ~4 days from Mar 8 2026

---

## Monthly Costs
| Item | Cost | Status |
|---|---|---|
| Hetzner EX63 | €78.54/mo | Active |
| Massive.com | $79/mo | Cancelled Apr 8 |
| Supabase | $0 | Free tier |
| Databento | Pay-as-you-go | Pending |
| Collective2 signals | ~$60/mo | Pending Phase 2 |
| **Total current** | **€78.54/mo** | |

---

## Key File Paths on Server
- Repo: `/opt/kat/app/`
- Backend: `/opt/kat/app/backend/`
- Venv: `/opt/kat/venv/`
- Env file: `/opt/kat/.env`
- Models: `/data/kat/models/`
- Secrets: `/root/kat_secrets.txt`

---

## Pending Tasks
- [ ] Stage 1 training complete — evaluate results
- [ ] Sign up Databento — download futures + indices + FX history
- [ ] Ingest European stocks via yfinance
- [ ] Rewrite reward function (Phase 3)
- [ ] Build KAT-HRM module (Phase 3b)
- [ ] Retrain with full dataset
- [ ] Set up IBKR paper trading connection (port 7496)
- [ ] Reboot server (pending Intel microcode update)
- [ ] Set up email notification system
- [ ] Push all server-side fixes back to GitHub

---
*Last updated: March 10, 2026*
