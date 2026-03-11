"""
orchestrator.py — KAT Pharma Module Main Loop
Runs daily (cron: 0 7 * * 1-5) to:
1. Refresh PDUFA calendar
2. Check for new FDA briefing docs
3. Score all upcoming events
4. Generate signals and alerts
5. Check T-1 exits on active trades
6. Log everything to MLflow

Usage:
  python orchestrator.py --daily     # full daily run
  python orchestrator.py --score     # just score + print, no trades
  python orchestrator.py --monitor   # check for new briefing docs only
"""

import logging
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from config import DATA_DIR, LOG_DIR
from pdufa_scraper import refresh_calendar, init_db
from fda_briefing import monitor_adcom_releases, analyze_drug, save_analysis
from model import score_upcoming_events, train_xgboost, prepare_training_data
from alerts import alert_new_signal, alert_briefing_released, send_daily_digest

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"pharma_{date.today().isoformat()}.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

SIGNALS_PATH = DATA_DIR / "latest_signals.json"
PREV_SIGNALS_PATH = DATA_DIR / "prev_signals.json"


def load_prev_signals() -> dict:
    """Load previous signal state to detect new signals."""
    if PREV_SIGNALS_PATH.exists():
        with open(PREV_SIGNALS_PATH) as f:
            return {e["ticker"]: e for e in json.load(f)}
    return {}


def save_signals(signals: list):
    """Save current signals to disk."""
    if SIGNALS_PATH.exists():
        SIGNALS_PATH.rename(PREV_SIGNALS_PATH)
    with open(SIGNALS_PATH, "w") as f:
        json.dump(signals, f, indent=2, default=str)


def detect_new_signals(current: list, prev: dict) -> list:
    """Returns signals that are new or changed from last run."""
    new = []
    for event in current:
        ticker = event["ticker"]
        prev_event = prev.get(ticker)
        
        # New ticker or signal changed
        if prev_event is None:
            new.append(event)
        elif prev_event.get("signal") != event.get("signal"):
            log.info(f"Signal change: {ticker} {prev_event.get('signal')} → {event.get('signal')}")
            new.append(event)
    
    return [e for e in new if e.get("signal") not in ("NO SIGNAL", None)]


def run_daily():
    """Full daily orchestration run."""
    log.info("=" * 60)
    log.info(f"KAT PHARMA DAILY RUN — {datetime.now().isoformat()}")
    log.info("=" * 60)
    
    # 1. Refresh PDUFA calendar
    log.info("Step 1: Refreshing PDUFA calendar...")
    refresh_calendar()
    
    # 2. Check for new FDA briefing docs
    log.info("Step 2: Checking for new FDA briefing documents...")
    new_docs = monitor_adcom_releases()
    for doc_url in new_docs[:3]:  # process max 3 new docs per day
        # Try to extract drug info from URL
        drug_name = doc_url.split("/")[-1].replace(".pdf", "").replace("-", " ").title()
        log.info(f"Processing new briefing: {drug_name}")
        analysis = analyze_drug(drug_name, "Unknown", briefing_url=doc_url)
        if analysis and "approval_signal" in analysis:
            save_analysis(drug_name, analysis)
            # Find matching ticker
            # TODO: match drug_name to event in DB
            log.info(f"Briefing analysis complete: {drug_name} signal={analysis.get('approval_signal'):.2f}")
    
    # 3. Score all upcoming events
    log.info("Step 3: Scoring upcoming PDUFA events...")
    scored = score_upcoming_events(fetch_live=False)  # set True when API keys configured
    
    # 4. Detect new/changed signals
    prev_signals = load_prev_signals()
    new_signals = detect_new_signals(scored, prev_signals)
    
    if new_signals:
        log.info(f"Step 4: {len(new_signals)} new/changed signals detected")
        for event in new_signals:
            log.info(f"  NEW SIGNAL: {event['ticker']} {event['signal']} P={event['p_approval']:.0%}")
            alert_new_signal(event)
    else:
        log.info("Step 4: No new signals")
    
    # 5. Save current signals
    save_signals(scored)
    
    # 6. Send daily digest
    log.info("Step 5: Sending daily digest...")
    send_daily_digest(scored)
    
    # 7. Print summary to console
    print_signal_table(scored)
    
    log.info("Daily run complete.")
    return scored


def run_score_only():
    """Score and print upcoming events without trading or alerts."""
    scored = score_upcoming_events(fetch_live=False)
    print_signal_table(scored)
    return scored


def print_signal_table(scored: list):
    """Pretty-print signal table to console."""
    print(f"\n{'='*90}")
    print(f"KAT PHARMA SIGNALS — {date.today()}")
    print(f"{'='*90}")
    print(f"{'DATE':<12} {'TICK':<6} {'P(APP)':<8} {'SIGNAL':<14} {'KELLY':<7} {'$SIZE':<9} {'T-':<6} DRUG")
    print(f"{'-'*90}")
    
    for e in scored:
        days = e.get("days_to_pdufa", 0)
        urgency = "🔴" if days <= 7 else "🟡" if days <= 21 else " "
        signal_str = e.get("signal", "")
        color_map = {"LONG": "📈", "SHORT": "📉", "NO SIGNAL": "  "}
        sig_icon = color_map.get(signal_str, "  ")
        
        print(f"{e.get('pdufa_date',''):<12} {e.get('ticker',''):<6} "
              f"{e.get('p_approval',0):<8.0%} {sig_icon}{signal_str:<12} "
              f"{e.get('kelly_fraction',0):<7.1%} ${e.get('dollar_size',0):<8,} "
              f"{urgency}T-{days:<4} {e.get('drug','')[:28]}")
    
    print(f"\nLong signals: {sum(1 for e in scored if e.get('signal')=='LONG')}")
    print(f"Short signals: {sum(1 for e in scored if e.get('signal')=='SHORT')}")
    print(f"Next PDUFA: {scored[0].get('pdufa_date')} ({scored[0].get('ticker')}) in T-{scored[0].get('days_to_pdufa')} days")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KAT Pharma Module Orchestrator")
    parser.add_argument("--daily",   action="store_true", help="Full daily run")
    parser.add_argument("--score",   action="store_true", help="Score only, no alerts/trades")
    parser.add_argument("--monitor", action="store_true", help="Check for new briefing docs")
    parser.add_argument("--train",   action="store_true", help="Retrain XGBoost model")
    args = parser.parse_args()
    
    if args.daily:
        run_daily()
    elif args.score:
        run_score_only()
    elif args.monitor:
        docs = monitor_adcom_releases()
        print(f"Found {len(docs)} new briefing docs")
    elif args.train:
        X, y = prepare_training_data()
        train_xgboost(X, y)
    else:
        # Default: just score
        run_score_only()
