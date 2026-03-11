"""
KAT v3.0 — Pharma Module Configuration
All secrets via environment variables. Never hardcode keys.
"""

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
DATA_DIR       = BASE_DIR / "data"
MODEL_DIR      = BASE_DIR / "models"
LOG_DIR        = BASE_DIR / "logs"
BRIEFING_DIR   = BASE_DIR / "briefings"

# ── API Keys (set in environment) ────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
IBKR_HOST           = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT           = int(os.getenv("IBKR_PORT", "7497"))   # 7497=paper, 7496=live
IBKR_CLIENT_ID      = int(os.getenv("IBKR_CLIENT_ID", "1"))
TELEGRAM_TOKEN      = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Paid data (fill when purchased) ──────────────────────────────────────────
BIOPHARMCATALYST_API_KEY = os.getenv("BIOPHARMCATALYST_API_KEY", "")  # buy first
UNUSUAL_WHALES_KEY       = os.getenv("UNUSUAL_WHALES_KEY", "")        # options skew
QUANDL_KEY               = os.getenv("QUANDL_KEY", "")                # short interest

# ── Model parameters ─────────────────────────────────────────────────────────
SIGNAL_THRESHOLD      = 0.62   # P(approval) >= this → LONG
SHORT_THRESHOLD       = 0.38   # P(approval) <= this → SHORT
KELLY_CAP             = 0.08   # max fraction of portfolio per trade
MAX_CONCURRENT_TRADES = 3      # max open PDUFA positions simultaneously
T1_PARTIAL_EXIT_PCT   = 0.50   # sell this fraction at T-1 day
STOP_LOSS_PCT         = 0.25   # hard stop on position (options decay buffer)
PORTFOLIO_SIZE        = 100_000  # USD

# ── Compliance (SNB rules) ────────────────────────────────────────────────────
MIN_HOLDING_DAYS      = 30     # SNB: 30-day minimum hold
USE_OPTIONS_NOT_SHARES = True  # SNB: options bypass holding period
FORBIDDEN_PAIRS       = ["CHF"]  # no CHF currency pairs

# ── Anthropic model ──────────────────────────────────────────────────────────
CLAUDE_MODEL          = "claude-opus-4-6"  # briefing doc analysis
CLAUDE_MAX_TOKENS     = 2000

# ── Feature weights (tuned on synthetic data; retune after buying real data) ─
FEATURE_WEIGHTS = {
    "adcom":          2.8,
    "short_interest": 1.2,
    "options_skew":   1.1,
    "mgmt_sentiment": 0.9,
    "class_rate":     1.4,
    "briefing":       2.2,
    "no_prior_crl":   0.8,
}

# ── Free data sources ─────────────────────────────────────────────────────────
FDA_BRIEFINGS_BASE = "https://www.fda.gov/advisory-committees/advisory-committee-calendar"
CLINICALTRIALS_API = "https://clinicaltrials.gov/api/v2/studies"
PUBMED_API         = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
SEC_EDGAR_API      = "https://efts.sec.gov/LATEST/search-index"
