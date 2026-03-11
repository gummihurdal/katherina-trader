# KAT PHARMA — MASTER ARCHITECTURE PLAN
# ════════════════════════════════════════════════════════════════════
# One system. Built in stages. No live trading until paper is proven.
# ════════════════════════════════════════════════════════════════════

## PHILOSOPHY

  No live capital until:
    ✓ Training AUC > 0.72 on held-out historical data
    ✓ Paper trading Sharpe > 1.2 over minimum 20 PDUFA events
    ✓ Paper trading win rate > 60% on SHORT signals
    ✓ Max drawdown < 20% in paper account
    ✓ Signal subscription validated for 30 days before adding next one

  One data subscription at a time.
  Validate each one. Then add the next.
  If it doesn't improve model AUC — drop it.


## STAGE MAP

  Stage 0 — Foundation (NOW)          ← we are here
  Stage 1 — Data + Training (Week 1-2)
  Stage 2 — Paper Trading (Month 1-3)
  Stage 3 — Live Trading (When paper proves it)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STAGE 0 — FOUNDATION  ✓ DONE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✓ Hetzner EX63 server running
  ✓ IB Gateway (Docker) connected
  ✓ executor.py — full lifecycle (buy / T-1 sell / PDUFA exit)
  ✓ orchestrator.py — signal generation
  ✓ feature_pipeline.py — real feature extraction
  ✓ PDUFA calendar — 15 events seeded
  ✓ Systemd timers — buy/t1/exit automated
  ✓ GitHub: gummihurdal/katherina-trader


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STAGE 1 — DATA + TRAINING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  GOAL: Build the best possible training dataset.
        Train XGBoost ensemble on vast.ai.
        Target AUC > 0.72.

  ── DATA SUBSCRIPTIONS (one at a time) ─────────────────────────────

  Subscription 1 — BioPharmCatalyst Elite Plus  $55/month  ← START HERE
  ─────────────────────────────────────────────────────────────────
  What we get:
    - Historical FDA Catalyst Calendar (2015-2024) — ~2,000 PDUFA outcomes
    - Catalyst Impact Table — stock move on decision day
    - Options Data — IV before/after, implied move
    - Historical P(approval) — market consensus scores
  
  Download on Day 1:
    1. Historical FDA Catalyst Calendar CSV
    2. Catalyst Impact Table CSV  
    3. Options Data CSV
  
  Validate after 30 days:
    - Did it improve model AUC vs formula baseline?
    - Yes → keep. No → evaluate alternatives.

  Subscription 2 — Market Chameleon  ~$40/month  ← ADD AFTER BPC VALIDATED
  ─────────────────────────────────────────────────────────────────
  What we get:
    - Live IV skew before PDUFA (call vs put implied vol)
    - Historical options data per ticker
    - Earnings/event implied move history
    - P(approval) derived from options pricing
  
  This is the single highest-value live feature.
  Options market prices in real-time crowd wisdom.
  Adds +3-5% AUC on top of BPC data alone.

  Subscription 3 — Evaluate after Stage 2 paper trading
  ─────────────────────────────────────────────────────────────────
  Candidates (pick one based on what's still missing):
    - Evaluate short interest data quality
    - Evaluate insider transaction feeds  
    - Evaluate SEC EDGAR real-time alerts
    - Evaluate clinical trial registry feeds

  Free data we use regardless:
    - FDA.gov — designations, AdCom votes, review letters
    - SEC EDGAR — Form 4 insider filings, 10-Q cash position
    - ClinicalTrials.gov — trial outcomes, endpoint data
    - Yahoo Finance — stock price, short interest, options chain
    - PubMed — published trial data for scientific context

  ── FEATURE SET (target ~25 features) ──────────────────────────────

  Regulatory (highest importance):
    crl_count                  # 0/1/2/3+ prior rejections
    resubmission_class         # Class 1 vs Class 2
    draft_label_shared         # FDA sent draft label ← most predictive
    no_major_deficiencies      # FDA stated clean review
    pdufa_extension            # extended? why?
    review_type                # standard/priority/accelerated

  Clinical (second highest):
    primary_endpoint_met       # 1/0/-1
    phase3_trials_positive     # N of M positive
    p_value_best               # best p-value reported
    surrogate_endpoint         # surrogate vs clinical
    adcom_pct_yes              # advisory committee vote %

  Designations:
    breakthrough_therapy       # BTD = 85% approval historically
    fast_track                 # FTD = 75%
    orphan_drug                # ODD = slight boost
    accelerated_approval       # surrogate pathway

  Market signals (real-time):
    options_implied_prob       # call/(call+put) at ATM
    iv_skew                    # put IV vs call IV
    short_interest_pct         # % float short
    short_change_30d           # direction of short interest
    call_put_ratio             # OI ratio

  Company signals:
    insider_net_30d            # Form 4 net shares bought/sold
    cash_months_runway         # months of cash left
    market_cap_m               # company size

  Base rates:
    indication_approval_rate   # indication-specific historical rate
    division_approval_rate     # FDA division-specific rate

  ── TRAINING ON VAST.AI ─────────────────────────────────────────────

  Why vast.ai:
    - Hetzner EX63 has no GPU
    - XGBoost trains in minutes on CPU but hyperparameter search needs GPU
    - vast.ai: RTX 4090 ~$0.35/hour — full training run < $2

  Training approach:
    1. Baseline: XGBoost on BPC historical (~2,000 events)
    2. Feature validation: SHAP values — which features actually matter
    3. Hyperparameter search: Optuna (Bayesian optimization)
    4. Ensemble: XGBoost + LightGBM + Logistic Regression → stacking
    5. Calibration: Platt scaling — raw model output → calibrated probability
    6. Walk-forward validation: retrain on 2015-2020, test 2021-2024

  Target metrics:
    AUC-ROC    > 0.72   (random = 0.50, excellent = 0.75+)
    Brier score < 0.20  (probability calibration)
    Log loss    < 0.55

  Training script: train_vast.py (to be built)
  Model output: kat_xgb_model.json → deploy to Hetzner

  ── FILES TO BUILD IN STAGE 1 ───────────────────────────────────────

  data/
    bpc_historical.csv          ← download from BPC Day 1
    bpc_impact.csv              ← price moves on decision day
    bpc_options.csv             ← historical options data
    fda_designations.csv        ← scraped from FDA.gov
    features_train.csv          ← assembled training matrix
    features_live.csv           ← current event features

  scripts/
    download_bpc.py             ← BPC data downloader + cleaner
    build_training_matrix.py    ← combines all sources → features_train.csv
    train_vast.py               ← vast.ai training script
    validate_model.py           ← walk-forward backtest + SHAP analysis
    deploy_model.py             ← push trained model to Hetzner


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STAGE 2 — PAPER TRADING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  GOAL: Validate the full pipeline on IBKR paper account.
        20+ real PDUFA events. No capital at risk.
        Prove Sharpe > 1.2 before touching live money.

  ── PAPER ACCOUNT SETUP ─────────────────────────────────────────────

  IBKR paper account:
    - Separate from live account
    - $100,000 simulated starting balance
    - Same executor.py — just port 7497 instead of 4001
    - Full lifecycle: buy → T-1 sell → PDUFA exit

  Paper trading config:
    IBKR_PORT = 4002    # IB Gateway paper port
    MAX_TRADE_USD = 4000
    Signal threshold: approval_prob <= 0.38 for SHORT

  ── PERFORMANCE TRACKING ────────────────────────────────────────────

  Every trade logged to PostgreSQL:
    - Entry price, exit price, P&L
    - Which features drove the signal
    - Actual FDA outcome (approved/rejected)
    - Model predicted probability vs actual outcome
    - Calibration error

  Monthly report auto-generated:
    - Win rate
    - Average P&L per trade
    - Sharpe ratio
    - Max drawdown
    - Feature importance drift
    - Model calibration drift

  Go-live criteria (ALL must pass):
    ✓ Minimum 20 PDUFA events traded on paper
    ✓ Win rate > 60% on SHORT signals
    ✓ Sharpe ratio > 1.2
    ✓ Max drawdown < 20%
    ✓ Model AUC still > 0.70 on recent events
    ✓ No single trade > 10% of portfolio

  ── FILES TO BUILD IN STAGE 2 ───────────────────────────────────────

  paper_trader.py              ← identical to executor.py but paper port
  performance_tracker.py       ← logs all trades, computes metrics
  monthly_report.py            ← auto-generates PDF performance report
  dashboard/                   ← trading.azurenexus.com integration


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STAGE 3 — LIVE TRADING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  GOAL: Deploy live only after paper proves it works.
        Start small. Scale with conviction.

  ── POSITION SIZING EVOLUTION ───────────────────────────────────────

  Phase A (first 10 live trades):   $2,000 max per trade
  Phase B (if Sharpe > 1.5):        $4,000 max per trade
  Phase C (if Sharpe > 2.0):        Kelly-sized, max $8,000

  ── RISK CONTROLS ───────────────────────────────────────────────────

  Hard stops (cannot be overridden by code):
    - Max $4,000 per single trade
    - Max 3 open positions simultaneously
    - Max $10,000 total capital at risk
    - Stop trading if monthly drawdown > 15%
    - Stop trading if 3 consecutive losses

  SNB compliance:
    - Options only (no 30-day hold restriction)
    - No CHF pairs
    - All positions documented for SNB reporting

  ── MONITORING ──────────────────────────────────────────────────────

  Real-time:
    - Telegram alerts on every order (buy/sell/fill/error)
    - Dashboard at trading.azurenexus.com
    - Hetzner: tail -f /var/log/kat_executor.log

  Daily:
    - Morning briefing: upcoming PDUFAs, open positions, P&L
    - Evening: any FDA announcements, model re-score if new info

  Monthly:
    - Full performance report
    - Model retraining if AUC drifts below 0.70
    - Subscription ROI review — is each data source adding value?


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  INFRASTRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Hetzner EX63 (~€78/month):
    - IB Gateway (Docker) — always running
    - PostgreSQL — trade log, feature history, model metrics
    - orchestrator.py — daily signal scan
    - feature_pipeline.py — feature extraction
    - executor.py — paper trading (Stage 2) / live (Stage 3)
    - systemd timers — fully autonomous

  vast.ai (pay per use, ~$2/training run):
    - XGBoost + LightGBM + ensemble training
    - Hyperparameter optimization (Optuna)
    - SHAP feature analysis
    - Walk-forward backtesting

  GitHub (gummihurdal/katherina-trader):
    - All code versioned
    - Model artifacts stored
    - Deployment via git pull on Hetzner


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  IMMEDIATE NEXT STEPS  (in order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1.  Fix IBKR 2FA → get paper port 4002 working
  2.  Download BPC historical CSV (already subscribed)
  3.  Build download_bpc.py — clean and normalize BPC data
  4.  Build build_training_matrix.py — assemble feature matrix
  5.  Run first training on vast.ai — get baseline AUC
  6.  Deploy model to Hetzner — replace formula scorer
  7.  Configure paper_trader.py on port 4002
  8.  Start paper trading — track every event
  9.  Add Market Chameleon after 30 days BPC validation
  10. Go live when paper trading criteria all pass


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  COST SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Fixed monthly:
    Hetzner EX63          €78/month
    BPC Elite Plus        $55/month    ← Stage 1
    Claude API            ~$20/month

  Variable:
    vast.ai training      ~$2/run      (once per month or after new data)
    Market Chameleon      $40/month    ← add after BPC validated

  Total Stage 1:          ~$175/month
  Total Stage 2:          ~$175/month  (same — no additional subs yet)
  Total Stage 3:          ~$215/month  (+ Market Chameleon)

  Break-even on live trading:
    At $4,000/trade, 1 winning trade/month covers all costs.
