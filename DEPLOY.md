# KAT v2.0 — Deployment Status

## Live URLs

| Service | URL | Status |
|---------|-----|--------|
| Dashboard | https://gummihurdal.github.io/katherina-trader/ | ✅ LIVE |
| Supabase | https://palmswzrpquwemhfrvxs.supabase.co | ✅ LIVE |
| Webhook API | `POST /rest/v1/rpc/handle_webhook` | ✅ TESTED |
| GitHub | https://github.com/gummihurdal/katherina-trader | ✅ PUBLIC |

## What's Deployed

- [x] React dashboard on GitHub Pages (auth + realtime)
- [x] Supabase PostgreSQL (11 tables, RLS, realtime, 24 indexes)
- [x] Database seeded (5 sources, 4 strategies, 15 signals, 6 positions)
- [x] Webhook handler (Postgres RPC — all 3 formats tested)
- [x] Python Guardian engine (10 checks + circuit breakers)
- [x] Signal parsers (C2, TradersPost, Holly AI, SignalStack, Telegram)

## Webhook Configuration

All webhooks use the same endpoint with source-specific tokens:

```
POST https://palmswzrpquwemhfrvxs.supabase.co/rest/v1/rpc/handle_webhook
Headers:
  apikey: <supabase_anon_key>
  Authorization: Bearer <supabase_service_role_key>
  Content-Type: application/json
```

### TradersPost
```json
{
  "webhook_token": "tp_744e6dd0bef6142a9c969eaf3ed9223e",
  "payload": {"action":"buy","ticker":"AAPL","quantity":10,"price":242.50,"stop":238.00}
}
```

### Holly AI
```json
{
  "webhook_token": "hl_a9b9997d3d95f7fe358121e905391ffc",
  "payload": {"signal":{"action":"buy","symbol":"TSLA","shares":5,"price":248.70,"stop":242.00,"confidence":0.81}}
}
```

### SignalStack
```json
{
  "webhook_token": "ss_44114c4936850c8d7e543bac9c6a36da",
  "payload": {"action":"BTO","symbol":"SPY","secType":"option","quantity":2,"lmtPrice":5.40}
}
```

## Custom Domain (Optional)

To use `katherina.azurenexus.com`:

1. Add DNS CNAME record: `katherina.azurenexus.com` → `gummihurdal.github.io`
2. In GitHub repo Settings → Pages → Custom domain: `katherina.azurenexus.com`
3. Rebuild frontend with `base: '/'` in `vite.config.js`

## Connection Details

| Key | Value |
|-----|-------|
| Supabase Project | `katherina-trader-dev` |
| Region | eu-central-1 (Frankfurt) |
| DB Password | `KAT-Guard1an-2026!` |
| Dashboard | https://supabase.com/dashboard/project/palmswzrpquwemhfrvxs |
