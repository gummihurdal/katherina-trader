"""KAT — Webhook Receiver (FastAPI)"""
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from .models import SignalSource
from .normalizer import SignalNormalizer

logger = logging.getLogger(__name__)
app = FastAPI(title="KAT Signal Receiver", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://katherina.azurenexus.com"],
    allow_methods=["POST"], allow_headers=["*"],
)

normalizer = SignalNormalizer()
WEBHOOK_TOKENS: dict = {}  # token → SignalSource

@app.post("/webhook/{token}")
async def receive_webhook(token: str, request: Request):
    if token not in WEBHOOK_TOKENS:
        raise HTTPException(status_code=401, detail="Invalid token")
    source = WEBHOOK_TOKENS[token]
    payload = await request.json()
    logger.info(f"Webhook: {source.value} | {payload}")
    signal = normalizer.normalize(source, payload)
    if signal is None:
        raise HTTPException(status_code=400, detail="Parse failed")
    # TODO: Send to Guardian → Execution pipeline
    return {"status": "received", "signal_id": signal.id, "source": signal.source.value,
            "symbol": signal.symbol, "action": signal.action.value,
            "received_at": datetime.utcnow().isoformat()}

@app.get("/health")
async def health():
    return {"status": "ok", "sources": len(WEBHOOK_TOKENS)}
