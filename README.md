# KAT — Katherina's Autonomous Trader

**Signal Aggregation Platform** · v2.0

---

## What is KAT?

KAT aggregates trading signals from 5 verified sources, passes every signal through a 10-check risk engine (Guardian), and executes approved trades via Interactive Brokers.

No signal — external or internal — bypasses the Guardian.

```
Collective2 ──┐                  ┌── Iron Condor
TradersPost ──┤                  ├── Momentum
Holly AI ─────┤──→ NORMALIZER ←──┤── Covered Calls
SignalStack ──┤                  ├── Dividend Capture
Telegram ─────┘    │             └── [Plugins]
                   ▼
              ┌─────────┐
              │ GUARDIAN │  ← 10 checks · Circuit breakers · ABSOLUTE VETO
              └────┬────┘
                   ▼
              ┌─────────┐
              │  IBKR    │  ← Paper or Live
              └─────────┘
```

## Architecture

| Layer | Stack |
|-------|-------|
| Frontend | React + Vite · Bloomberg Terminal aesthetic |
| API | Supabase Edge Functions (Deno) |
| Backend | Python · FastAPI webhooks · Signal parsers |
| Risk | Guardian engine · 10 checks · Circuit breakers |
| Database | Supabase PostgreSQL · RLS · 11 tables |
| Broker | Interactive Brokers TWS API |
| Hosting | GitHub Pages (UI) · Hetzner VPS (engine) |

## Guardian Risk Engine

Every signal passes through 10 sequential checks:

1. Capital available
2. Position size ≤ 2%
3. Portfolio heat < 10%
4. Correlation < 0.70
5. Concentration < 15% per underlying
6. Daily P&L (auto-halt at 3% loss)
7. Cash reserve ≥ 20%
8. Stop-loss present (auto-adds if missing)
9. Source allocation within limits
10. Compliance (restricted stocks, holding periods)

**Circuit breakers:** Daily loss >3% → global halt · Weekly >5% → 48h pause · Source loss >2%/day → source halt · Signal flood >20/src/day → source block

## Setup

```bash
# Clone
git clone https://github.com/gummihurdal/katherina-trader.git
cd katherina-trader

# Python backend
pip install -r backend/requirements.txt

# Environment
cp .env.example .env
# Fill in Supabase URL, IBKR port, API keys

# Supabase migration
# SQL Editor → paste supabase/migrations/001_initial_schema.sql

# Start
uvicorn backend.signals.webhook_server:app --port 8000
```

## Non-Negotiable Rules

1. NEVER store API keys in frontend
2. NEVER deploy live without 30 days paper testing
3. NEVER trade without a stop-loss
4. GUARDIAN HAS FINAL SAY — no source bypasses

---

*katherina.azurenexus.com*
