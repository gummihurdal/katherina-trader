# KAT v3.0 — Pharma Module

**Autonomous PDUFA event trading system with Claude API briefing doc analysis.**

## Architecture

```
kat_pharma/
├── config.py           — All configuration & API keys (env vars)
├── pdufa_scraper.py    — PDUFA calendar (free scrape + paid API)
├── fda_briefing.py     — FDA PDF download + Claude API analysis  ← main alpha
├── features.py         — 10-feature engineering pipeline
├── model.py            — XGBoost + rule-based ensemble
├── ibkr_executor.py    — IBKR TWS options execution (SNB compliant)
├── alerts.py           — Telegram + daily digest
└── orchestrator.py     — Daily run loop
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt --break-system-packages
```

### 2. Set environment variables
```bash
export ANTHROPIC_API_KEY="sk-ant-..."       # required for briefing analysis
export TELEGRAM_TOKEN="..."                  # optional, for alerts
export TELEGRAM_CHAT_ID="..."               # optional

# When purchased:
export BIOPHARMCATALYST_API_KEY="..."       # historical data
export UNUSUAL_WHALES_KEY="..."             # options skew
export QUANDL_KEY="..."                     # short interest
```

### 3. Initialize database
```bash
python pdufa_scraper.py
```

### 4. Score upcoming events (no API keys needed)
```bash
python orchestrator.py --score
```

### 5. Train model (synthetic data until BioPharmaWatch purchased)
```bash
python model.py --train
```

### 6. Set up daily cron (run at 7am weekdays)
```bash
crontab -e
# Add: 0 7 * * 1-5 cd /path/to/kat_pharma && python orchestrator.py --daily >> logs/cron.log 2>&1
```

---

## Signal Logic

```
P(approval) >= 62%  →  LONG  (buy calls, expiry PDUFA+7 days)
P(approval) <= 38%  →  SHORT (buy puts, expiry PDUFA+7 days)
38% < P < 62%       →  NO SIGNAL
```

## Position Sizing (Kelly Criterion)
```
f* = (p*b - q) / b
b  = expected_gain / expected_loss  (IV move / 60% CRL haircut)
f* capped at 8% of portfolio
```

## SNB Compliance (CRITICAL)
- **OPTIONS ONLY** — not shares. Bypasses 30-day holding period.
- **Buy 4-6 weeks before PDUFA**
- **Sell 50% at T-1 day** (auto-managed by T1ExitScheduler)
- **No CHF pairs**
- Confirm each trade with SNB compliance officer before execution.

---

## Data Sources

| Source | Cost | Data | When to buy |
|--------|------|------|-------------|
| Seed data | Free | 13 real 2026 events | Already included |
| RTTNews | Free | Current PDUFA calendar | Already scraped |
| BioPharmaWatch | ~$500/yr | Historical outcomes 2015-2024 | **Buy first** |
| Unusual Whales | ~$500/yr | Real-time options IV/skew | Buy after validation |
| Quandl/FINRA | ~$300/yr | Daily short interest | Buy after validation |

---

## Accuracy Targets

| Model | Accuracy | Notes |
|-------|----------|-------|
| Base rate (no model) | 58% | FDA overall approval rate |
| AdCom vote only | 67% | Best single feature |
| Rule-based (all features) | ~72% | Available now |
| XGBoost (synthetic data) | ~68% | Degrades without real data |
| XGBoost (real historical) | ~74% | After BioPharmaWatch |
| XGBoost + Claude briefing | ~77% | Full system |

---

## Upgrade Path

1. **Now**: Run rule-based scorer on seed data. Paper trade 3-4 decisions.
2. **After BioPharmaWatch ($500)**: Retrain XGBoost on 2015-2024 historical data. Accuracy improves.
3. **After Unusual Whales ($500)**: Replace yfinance skew approximation with real delta-skew.
4. **Go-live criteria**: 10+ paper trades, >65% win rate, Sharpe > 1.2.

---

## Integration with KAT v3.0 Main Loop

The pharma module runs as a **separate process** alongside KAT's RL equity trader.
- Shared IBKR connection (different client ID)
- Shared MLflow experiment tracking
- Independent risk limits (max $20k allocated to PDUFA trades total)
- Nightly Claude API briefing doc analysis (~$5-15/month usage)
