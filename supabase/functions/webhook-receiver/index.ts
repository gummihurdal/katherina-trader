// KAT v2.0 — Universal Webhook Receiver
// Handles: TradersPost, Holly AI, SignalStack, generic webhooks
// Deploy: supabase functions deploy webhook-receiver

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const supabase = createClient(supabaseUrl, supabaseKey);

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-webhook-token, content-type",
  "Content-Type": "application/json",
};

// Normalize action strings to our enum
function normalizeAction(raw: string): string {
  const map: Record<string, string> = {
    buy: "buy", long: "buy", "buy_to_open": "bto", bto: "bto",
    sell: "sell", short: "sell", "sell_to_open": "sto", sto: "sto",
    "buy_to_close": "btc", btc: "btc", cover: "btc",
    "sell_to_close": "stc", stc: "stc",
  };
  return map[raw?.toLowerCase()] || "buy";
}

// Normalize asset class
function normalizeAssetClass(raw: string): string {
  const map: Record<string, string> = {
    stock: "stock", equity: "stock", stk: "stock",
    option: "option", opt: "option", options: "option",
    future: "future", fut: "future", futures: "future",
    forex: "forex", fx: "forex",
    crypto: "crypto",
  };
  return map[raw?.toLowerCase()] || "stock";
}

// Parse TradersPost format
function parseTradersPost(body: any) {
  return {
    action: normalizeAction(body.action),
    asset_class: normalizeAssetClass(body.assetClass || body.asset_class || "stock"),
    symbol: body.ticker || body.symbol,
    quantity: body.quantity || body.qty || 1,
    limit_price: body.price || body.limit || null,
    stop_loss: body.stopLoss || body.stop || null,
    confidence: body.confidence || null,
  };
}

// Parse Holly AI format
function parseHollyAI(body: any) {
  return {
    action: normalizeAction(body.signal?.action || body.action || "buy"),
    asset_class: "stock",
    symbol: body.signal?.symbol || body.symbol || body.ticker,
    quantity: body.signal?.shares || body.quantity || 1,
    limit_price: body.signal?.price || body.price || null,
    stop_loss: body.signal?.stop || body.stopLoss || null,
    confidence: body.signal?.confidence || body.confidence || null,
  };
}

// Parse SignalStack format
function parseSignalStack(body: any) {
  return {
    action: normalizeAction(body.action),
    asset_class: normalizeAssetClass(body.secType || body.assetClass || "stock"),
    symbol: body.symbol || body.ticker,
    quantity: body.quantity || body.totalQuantity || 1,
    limit_price: body.lmtPrice || body.price || null,
    stop_loss: body.auxPrice || body.stop || null,
    confidence: null,
  };
}

// Generic fallback parser
function parseGeneric(body: any) {
  return {
    action: normalizeAction(body.action || body.side || "buy"),
    asset_class: normalizeAssetClass(body.asset_class || body.assetClass || body.type || "stock"),
    symbol: body.symbol || body.ticker || body.sym,
    quantity: body.quantity || body.qty || body.size || 1,
    limit_price: body.price || body.limit_price || body.limit || null,
    stop_loss: body.stop_loss || body.stop || body.sl || null,
    confidence: body.confidence || body.score || null,
  };
}

Deno.serve(async (req) => {
  // CORS preflight
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });

  try {
    // Auth: check webhook token
    const token = req.headers.get("x-webhook-token") || new URL(req.url).searchParams.get("token");
    if (!token) return new Response(JSON.stringify({ error: "Missing webhook token" }), { status: 401, headers: CORS });

    // Look up webhook config
    const { data: webhook, error: whErr } = await supabase
      .from("webhooks")
      .select("*, signal_sources(*)")
      .eq("endpoint_token", token)
      .single();

    if (whErr || !webhook) return new Response(JSON.stringify({ error: "Invalid token" }), { status: 403, headers: CORS });

    const body = await req.json();
    const sourceName = webhook.signal_sources?.name || "";

    // Parse based on source
    let parsed;
    switch (sourceName) {
      case "traderspost": parsed = parseTradersPost(body); break;
      case "holly_ai": parsed = parseHollyAI(body); break;
      case "signalstack": parsed = parseSignalStack(body); break;
      default: parsed = parseGeneric(body); break;
    }

    // Validate
    if (!parsed.symbol) {
      return new Response(JSON.stringify({ error: "Missing symbol" }), { status: 400, headers: CORS });
    }

    // Insert signal (Guardian checks run server-side in Python engine)
    // For now, mark as pending review
    const { data: signal, error: sigErr } = await supabase.from("signals").insert({
      user_id: webhook.user_id,
      source_id: webhook.source_id,
      action: parsed.action,
      asset_class: parsed.asset_class,
      symbol: parsed.symbol.toUpperCase(),
      quantity: parsed.quantity,
      limit_price: parsed.limit_price,
      stop_loss: parsed.stop_loss,
      confidence: parsed.confidence,
      risk_approved: false, // Pending Guardian review
      risk_checks: {},
      raw_payload: body,
      signal_time: new Date().toISOString(),
      received_at: new Date().toISOString(),
    }).select().single();

    if (sigErr) throw sigErr;

    // Update source signal count
    await supabase.rpc("increment_source_signals", { source_id: webhook.source_id });

    return new Response(JSON.stringify({
      ok: true,
      signal_id: signal.id,
      source: sourceName,
      symbol: parsed.symbol,
      action: parsed.action,
      status: "pending_guardian",
    }), { headers: CORS });

  } catch (err) {
    console.error("Webhook error:", err);
    return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: CORS });
  }
});
