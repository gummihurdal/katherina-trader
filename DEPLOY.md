# KAT v2.0 — Deployment Guide

## What's Already Done

- [x] GitHub repo: `gummihurdal/katherina-trader` (private)
- [x] Supabase project: `katherina-trader-dev` (eu-central-1)
- [x] 11 tables created with RLS + 24 indexes
- [x] Realtime enabled on signals, positions, signal_sources
- [x] RLS policies for authenticated users
- [x] Database seeded (5 sources, 4 strategies, 12 signals, 6 positions)
- [x] Webhook tokens generated for TradersPost, Holly AI, SignalStack
- [x] Edge Function code ready (webhook-receiver)

## Remaining Steps

### 1. Create Your Account
Sign up at: `https://palmswzrpquwemhfrvxs.supabase.co`
Use the Auth screen in the dashboard.

### 2. Deploy Frontend (GitHub Pages)
```bash
cd frontend
npm install
npm run build

# In GitHub: Settings → Pages → Source: GitHub Actions
# Or manually deploy the dist/ folder
```

### 3. Deploy Webhook Edge Function
```bash
# Install Supabase CLI
npm install -g supabase

# Login
supabase login

# Link project
supabase link --project-ref palmswzrpquwemhfrvxs

# Deploy
supabase functions deploy webhook-receiver --no-verify-jwt
```

### 4. Configure Webhook Sources

**TradersPost:**
```
URL: https://palmswzrpquwemhfrvxs.supabase.co/functions/v1/webhook-receiver
Header: x-webhook-token: tp_744e6dd0bef6142a9c969eaf3ed9223e
```

**Holly AI:**
```
URL: https://palmswzrpquwemhfrvxs.supabase.co/functions/v1/webhook-receiver
Header: x-webhook-token: hl_a9b9997d3d95f7fe358121e905391ffc
```

**SignalStack:**
```
URL: https://palmswzrpquwemhfrvxs.supabase.co/functions/v1/webhook-receiver
Header: x-webhook-token: ss_44114c4936850c8d7e543bac9c6a36da
```

### 5. Custom Domain (Optional)
Point `katherina.azurenexus.com` to GitHub Pages deployment.

## Connection Details

| Key | Value |
|-----|-------|
| Supabase URL | `https://palmswzrpquwemhfrvxs.supabase.co` |
| Dashboard | `https://supabase.com/dashboard/project/palmswzrpquwemhfrvxs` |
| Region | eu-central-1 (Frankfurt) |
| DB Password | `KAT-Guard1an-2026!` |

## Testing Webhooks

```bash
# Test TradersPost signal
curl -X POST https://palmswzrpquwemhfrvxs.supabase.co/functions/v1/webhook-receiver \
  -H "x-webhook-token: tp_744e6dd0bef6142a9c969eaf3ed9223e" \
  -H "Content-Type: application/json" \
  -d '{"action": "buy", "ticker": "AAPL", "quantity": 10, "price": 242.50, "stop": 238.00}'
```
