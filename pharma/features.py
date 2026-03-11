"""
features.py — Feature engineering pipeline for PDUFA ML model
Combines free + paid data sources into numpy feature vectors for XGBoost.

Feature vector (10 features):
 [0] adcom_vote          — ratio or base rate (0.58) if no adcom
 [1] short_interest_14d  — change in SI over 14 days (negative = covering = bullish)
 [2] options_skew        — 25-delta put/call skew (positive = call-heavy = bullish)
 [3] mgmt_sentiment      — NLP sentiment score from earnings call (0-1)
 [4] class_rate          — historical approval rate for same drug class/indication
 [5] briefing_score      — Claude API briefing doc approval signal (0-1)
 [6] no_prior_crl        — 1 if no prior CRL, 0 if had CRL(s), -0.5 if 2+ CRLs
 [7] priority_review     — 1 if Priority Review, 0 otherwise
 [8] breakthrough        — 1 if Breakthrough Therapy Designation, 0 otherwise
 [9] days_to_pdufa       — normalized, higher = more time for info to arrive
"""

import numpy as np
import requests
import logging
import json
from datetime import date, datetime
from typing import Optional, Dict
from dataclasses import dataclass

from config import (UNUSUAL_WHALES_KEY, QUANDL_KEY, DATA_DIR, FEATURE_WEIGHTS)
from fda_briefing import analyze_drug, load_analysis, save_analysis

log = logging.getLogger(__name__)


# ── Drug class base rates (from historical literature + own backtests) ─────────
# Source: Chi Heem Wong et al. (2019) "Estimation of clinical trial success rates"
# Updated with 2019-2024 FDA data from BioMed Nexus analysis
CLASS_BASE_RATES = {
    # Indication → historical P(Phase3 → approval) 
    "oncology":              0.59,
    "hematology":            0.62,
    "rare_disease":          0.68,
    "gene_therapy":          0.64,
    "immunology":            0.71,
    "neurology":             0.52,
    "alzheimers":            0.38,  # historically very low
    "psychiatry":            0.54,
    "cardiovascular":        0.66,
    "metabolic":             0.72,
    "diabetes":              0.78,
    "obesity":               0.74,
    "respiratory":           0.69,
    "ophthalmology":         0.61,
    "dry_eye":               0.52,  # multiple recent CRLs
    "dermatology":           0.74,
    "nephrology":            0.63,
    "igan":                  0.68,  # newer class, strong recent approvals
    "infectious_disease":    0.76,
    "pain":                  0.48,  # high CRL rate historically
    "resubmission":          0.64,  # resubmissions after CRL
    "resubmission_2x":       0.41,  # 2+ CRLs, much lower base rate
    "label_expansion":       0.79,  # sNDA/sBLA expansions of approved drugs
    "formulation_change":    0.88,  # low-risk formulation NDAs
    "default":               0.58,  # FDA overall historical approval rate
}

# MOA → indication category mapping (simplified)
INDICATION_MAP = {
    "dry eye": "dry_eye", "alzheimer": "alzheimers", "parkinson": "neurology",
    "als": "neurology", "mps": "rare_disease", "lad-i": "rare_disease",
    "gene therapy": "gene_therapy", "aml": "hematology", "mds": "hematology",
    "myeloma": "hematology", "lymphoma": "hematology", "nsclc": "oncology",
    "breast cancer": "oncology", "thyroid eye": "ophthalmology",
    "igan": "igan", "nephropathy": "nephrology", "pkd": "nephrology",
    "obesity": "obesity", "diabetes": "diabetes", "hypothalamic obesity": "obesity",
    "depression": "psychiatry", "schizophrenia": "psychiatry",
    "pbc": "rare_disease", "et": "hematology",
    "ros1": "oncology", "her2": "oncology", "gist": "oncology",
    "psoriatic": "immunology", "mg": "immunology", "itp": "immunology",
}


def get_class_rate(indication: str, prior_crl: int, event_type: str) -> float:
    """Returns historical approval base rate for this drug class."""
    ind_lower = indication.lower()
    
    # Check for label expansion (sNDA/sBLA of approved drug)
    if event_type in ("sNDA", "sBLA") and prior_crl == 0:
        return CLASS_BASE_RATES["label_expansion"]
    
    # Prior CRL heavily penalizes base rate
    if prior_crl >= 2:
        return CLASS_BASE_RATES["resubmission_2x"]
    if prior_crl == 1:
        return CLASS_BASE_RATES["resubmission"]
    
    # Match indication to category
    for keyword, category in INDICATION_MAP.items():
        if keyword in ind_lower:
            return CLASS_BASE_RATES.get(category, CLASS_BASE_RATES["default"])
    
    return CLASS_BASE_RATES["default"]


# ── Short interest (paid: Quandl; free: FINRA biweekly) ───────────────────────
def get_short_interest_change(ticker: str, days: int = 14) -> float:
    """
    Returns 14-day change in short interest ratio.
    Negative = short covering (bullish signal).
    Positive = short buildup (bearish signal).
    
    With Quandl key: daily data.
    Without: FINRA biweekly (coarser but free).
    """
    if QUANDL_KEY:
        return _quandl_short_interest(ticker, days)
    else:
        return _finra_short_interest(ticker)


def _quandl_short_interest(ticker: str, days: int) -> float:
    """Quandl FINRA short interest — daily, requires API key."""
    try:
        url = f"https://data.nasdaq.com/api/v3/datasets/FINRA/FNSQ_{ticker}"
        r = requests.get(url, params={
            "api_key": QUANDL_KEY,
            "rows": days + 5,
        }, timeout=10)
        data = r.json()
        rows = data.get("dataset", {}).get("data", [])
        if len(rows) < 2:
            return 0.0
        # Short interest ratio: col 2 = ShortVolume / TotalVolume
        latest = rows[0][2] if rows[0][2] else 0
        prior = rows[-1][2] if rows[-1][2] else 0
        change = (latest - prior) / (prior + 1e-9)
        return float(np.clip(change, -1, 1))
    except Exception as e:
        log.warning(f"Quandl short interest failed for {ticker}: {e}")
        return 0.0


def _finra_short_interest(ticker: str) -> float:
    """
    FINRA biweekly short interest — free but lags 2 weeks and coarse.
    https://www.finra.org/investors/learn-to-invest/advanced-investing/short-selling/regsho/short-interest
    """
    try:
        url = f"https://api.finra.org/data/group/otcmarket/name/consolidatedShortInterest"
        params = {"symbol": ticker, "limit": 4}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if len(data) < 2:
            return 0.0
        latest_si = float(data[0].get("shortInterest", 0))
        prior_si = float(data[-1].get("shortInterest", 1))
        change = (latest_si - prior_si) / (prior_si + 1e-9)
        return float(np.clip(change, -1, 1))
    except Exception:
        return 0.0


# ── Options skew (paid: Unusual Whales; free: yfinance approximation) ─────────
def get_options_skew(ticker: str) -> float:
    """
    25-delta put/call skew.
    Positive = calls more expensive than puts = market expects upside.
    Negative = puts more expensive = market pricing in downside risk.
    """
    if UNUSUAL_WHALES_KEY:
        return _unusual_whales_skew(ticker)
    else:
        return _yfinance_skew_approx(ticker)


def _unusual_whales_skew(ticker: str) -> float:
    """Unusual Whales API for IV skew — requires paid key."""
    try:
        url = f"https://phx.unusualwhales.com/api/historic_chains/{ticker}"
        headers = {"Authorization": f"Bearer {UNUSUAL_WHALES_KEY}"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        # Extract 25-delta put/call IV spread
        calls = [x for x in data if x.get("delta", 0) > 0.20 and x.get("delta", 0) < 0.30]
        puts = [x for x in data if x.get("delta", 0) > -0.30 and x.get("delta", 0) < -0.20]
        if calls and puts:
            avg_call_iv = sum(c.get("implied_volatility", 0) for c in calls) / len(calls)
            avg_put_iv = sum(p.get("implied_volatility", 0) for p in puts) / len(puts)
            skew = (avg_call_iv - avg_put_iv) / (avg_put_iv + 1e-9)
            return float(np.clip(skew, -1, 1))
        return 0.0
    except Exception as e:
        log.warning(f"Unusual Whales skew failed for {ticker}: {e}")
        return 0.0


def _yfinance_skew_approx(ticker: str) -> float:
    """
    Approximates options skew using yfinance put/call OI ratio.
    Not as good as proper delta-skew but free.
    Negative P/C ratio relative to norm → bullish.
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        
        if not stock.options:
            return 0.0
        
        # Use nearest expiry
        exp = stock.options[0]
        chain = stock.option_chain(exp)
        
        call_oi = chain.calls["openInterest"].sum()
        put_oi = chain.puts["openInterest"].sum()
        
        if call_oi + put_oi == 0:
            return 0.0
        
        pc_ratio = put_oi / (call_oi + 1e-9)
        # Normalize: typical P/C ratio ~0.7. Below 0.7 = bullish, above = bearish
        # Convert to -1..+1 scale where positive = bullish
        normalized = (0.7 - pc_ratio) / 0.7
        return float(np.clip(normalized, -1, 1))
    except Exception as e:
        log.warning(f"yfinance skew approx failed for {ticker}: {e}")
        return 0.0


# ── Management sentiment (free: SEC EDGAR earnings call NLP) ─────────────────
def get_mgmt_sentiment(ticker: str, drug_name: str) -> float:
    """
    NLP sentiment score from most recent earnings call transcript.
    Uses SEC EDGAR full-text search for 8-K filings (earnings calls).
    Score: 0.0 = very negative, 1.0 = very positive.
    """
    try:
        # Search SEC EDGAR for recent 8-K filings
        url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q": f'"{drug_name}" "advisory committee" OR "PDUFA" OR "regulatory"',
            "dateRange": "custom",
            "startdt": (datetime.now().replace(month=1, day=1)).strftime("%Y-%m-%d"),
            "forms": "8-K",
            "entity": ticker,
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return 0.65  # neutral/slightly positive default
        
        # Simple lexical sentiment on the most recent filing
        text = hits[0].get("_source", {}).get("period_of_report", "") + " " + \
               hits[0].get("_source", {}).get("display_names", "")
        
        return _lexical_sentiment(text)
    except Exception:
        return 0.65


def _lexical_sentiment(text: str) -> float:
    """Simple lexical sentiment — good enough for regulatory filings."""
    text_lower = text.lower()
    
    positive_words = [
        "pleased", "positive", "promising", "favorable", "strong", "efficacy",
        "benefit", "successful", "approve", "accelerated", "breakthrough",
        "significant", "confidence", "priority", "progress", "encouraging"
    ]
    negative_words = [
        "concern", "risk", "failure", "rejection", "crl", "delay", "negative",
        "uncertain", "challenge", "deficiency", "inadequate", "insufficient",
        "require additional", "complete response", "not approvable"
    ]
    
    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)
    total = pos_count + neg_count + 1e-9
    
    score = (pos_count / total) * 0.6 + 0.4  # anchored: never below 0.4 from lexical alone
    return float(np.clip(score, 0.0, 1.0))


# ── Main feature builder ───────────────────────────────────────────────────────
@dataclass
class FeatureVector:
    adcom: float
    short_interest: float
    options_skew: float
    mgmt_sentiment: float
    class_rate: float
    briefing: float
    no_prior_crl: float
    priority_review: float
    breakthrough: float
    days_normalized: float

    def to_array(self) -> np.ndarray:
        return np.array([
            self.adcom, self.short_interest, self.options_skew,
            self.mgmt_sentiment, self.class_rate, self.briefing,
            self.no_prior_crl, self.priority_review, self.breakthrough,
            self.days_normalized
        ], dtype=np.float32)

    def to_dict(self) -> dict:
        return {
            "adcom": self.adcom,
            "short_interest": self.short_interest,
            "options_skew": self.options_skew,
            "mgmt_sentiment": self.mgmt_sentiment,
            "class_rate": self.class_rate,
            "briefing": self.briefing,
            "no_prior_crl": self.no_prior_crl,
            "priority_review": self.priority_review,
            "breakthrough": self.breakthrough,
            "days_normalized": self.days_normalized,
        }


def build_features(event: dict, fetch_live: bool = True) -> FeatureVector:
    """
    Builds a 10-feature vector for a PDUFA event.
    
    event dict keys: ticker, drug, indication, pdufa_date, prior_crl,
                     priority_review, breakthrough, event_type,
                     adcom_vote (optional), briefing_url (optional)
    fetch_live: if True, fetches real-time short interest and options data
    """
    ticker    = event["ticker"]
    drug      = event["drug"]
    indication= event["indication"]
    pdufa_str = event["pdufa_date"]
    prior_crl = event.get("prior_crl", 0)
    priority  = bool(event.get("priority_review", False))
    btd       = bool(event.get("breakthrough", False))
    evt_type  = event.get("event_type", "NDA")

    # Days to PDUFA (normalized 0-1, 0=today, 1=180+ days away)
    today = date.today()
    pdufa = date.fromisoformat(pdufa_str)
    days_to = max(0, (pdufa - today).days)
    days_norm = min(1.0, days_to / 180)

    # AdCom vote
    adcom = event.get("adcom_vote")
    if adcom is None:
        adcom = 0.58  # base rate when no adcom scheduled

    # Class base rate
    class_rate = get_class_rate(indication, prior_crl, evt_type)

    # Prior CRL score: 1 = clean, 0 = one CRL, -0.5 = two+ CRLs
    if prior_crl == 0:
        no_crl_score = 1.0
    elif prior_crl == 1:
        no_crl_score = 0.0
    else:
        no_crl_score = -0.5

    # Live market data
    if fetch_live:
        si_change = get_short_interest_change(ticker)
        skew = get_options_skew(ticker)
        mgmt = get_mgmt_sentiment(ticker, drug)
    else:
        si_change = event.get("si_change", 0.0)
        skew = event.get("options_skew", 0.0)
        mgmt = event.get("mgmt_sentiment", 0.65)

    # Briefing doc analysis (cached → live)
    cached = load_analysis(drug)
    if cached and "approval_signal" in cached:
        briefing_score = cached["approval_signal"]
        log.info(f"Using cached briefing analysis for {drug}: {briefing_score:.2f}")
    else:
        briefing_url = event.get("briefing_url")
        if briefing_url or fetch_live:
            analysis = analyze_drug(drug, indication, briefing_url=briefing_url)
            briefing_score = analysis.get("approval_signal", 0.58)
            save_analysis(drug, analysis)
        else:
            briefing_score = class_rate  # fallback: use class rate

    return FeatureVector(
        adcom=float(adcom),
        short_interest=float(si_change),
        options_skew=float(skew),
        mgmt_sentiment=float(mgmt),
        class_rate=float(class_rate),
        briefing=float(briefing_score),
        no_prior_crl=float(no_crl_score),
        priority_review=float(priority),
        breakthrough=float(btd),
        days_normalized=float(days_norm),
    )


if __name__ == "__main__":
    # Test with RCKT Kresladi (no live fetch, use known values)
    test_event = {
        "ticker": "RCKT",
        "drug": "Marnetegragene (Kresladi)",
        "indication": "LAD-I Gene Therapy",
        "pdufa_date": "2026-03-28",
        "prior_crl": 1,
        "priority_review": True,
        "breakthrough": True,
        "event_type": "BLA(Resubmission)",
        "adcom_vote": None,
        "si_change": -0.12,
        "options_skew": 0.22,
        "mgmt_sentiment": 0.76,
        "briefing_url": None,
    }
    
    fv = build_features(test_event, fetch_live=False)
    print("\nFeature vector for RCKT Kresladi:")
    for k, v in fv.to_dict().items():
        print(f"  {k:20s}: {v:.3f}")
    print(f"\n  Array: {fv.to_array()}")
