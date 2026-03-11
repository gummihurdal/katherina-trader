"""
alerts.py — Telegram + email alert system for KAT Pharma module
Sends alerts for: new PDUFA signals, briefing doc releases, T-1 exits, fills
"""

import requests
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from typing import Optional

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


def send_telegram(message: str) -> bool:
    """Send message via Telegram bot."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured (set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def format_signal_alert(event: dict) -> str:
    """Format a PDUFA signal as a Telegram message."""
    p = event.get("p_approval", 0)
    signal = event.get("signal", "UNKNOWN")
    ticker = event.get("ticker", "")
    drug = event.get("drug", "")
    indication = event.get("indication", "")
    pdufa = event.get("pdufa_date", "")
    days = event.get("days_to_pdufa", 0)
    kelly = event.get("kelly_fraction", 0)
    dollar = event.get("dollar_size", 0)
    
    signal_emoji = {
        "LONG": "🟢",
        "SHORT": "🔴",
        "STRONG LONG": "🚀",
        "STRONG SHORT": "💥",
    }.get(signal, "⚪")
    
    return f"""
{signal_emoji} <b>KAT PHARMA SIGNAL</b>

<b>{ticker}</b> — {drug}
Indication: {indication}
PDUFA: {pdufa} (T-{days} days)

P(Approval): <b>{p:.0%}</b>
Signal: <b>{signal}</b>
Kelly Size: {kelly:.1%} → <b>${dollar:,.0f}</b>

Action: Buy {'calls' if signal == 'LONG' else 'puts'} expiring ~{days+7} days
SNB Note: OPTIONS ONLY (not shares)
""".strip()


def format_briefing_alert(drug: str, ticker: str, analysis: dict) -> str:
    """Format briefing doc analysis as alert."""
    signal = analysis.get("approval_signal", 0)
    tone = analysis.get("fda_tone", "unknown")
    concerns = analysis.get("fda_concern_count", 0)
    
    tone_emoji = {
        "supportive": "✅",
        "neutral": "🟡",
        "skeptical": "⚠️",
        "adversarial": "🚨",
    }.get(tone, "❓")
    
    return f"""
📄 <b>FDA BRIEFING DOC ANALYZED</b>

<b>{ticker}</b> — {drug}
FDA Tone: {tone_emoji} {tone.upper()}
Approval Signal: <b>{signal:.0%}</b>
FDA Concerns: {concerns}

{analysis.get('approval_signal_rationale', 'No rationale available')[:200]}

⏰ 48-HOUR ENTRY WINDOW OPEN
""".strip()


def format_t1_exit_alert(trade: dict) -> str:
    """Alert for T-1 automatic half-position exit."""
    return f"""
⏳ <b>T-1 AUTO-EXIT</b>

<b>{trade.get('ticker')}</b> — {trade.get('drug')}
PDUFA TOMORROW: {trade.get('pdufa_date')}

Action: Closing 50% of position
Remaining: {trade.get('contracts_remaining', 0)} contracts
P(Approval): {trade.get('p_approval', 0):.0%}
""".strip()


def format_outcome_alert(trade: dict, approved: bool) -> str:
    """Alert when FDA decision comes in."""
    ticker = trade.get("ticker")
    signal = trade.get("signal")
    correct = (approved and signal == "LONG") or (not approved and signal == "SHORT")
    
    result_emoji = "✅ WIN" if correct else "❌ LOSS"
    outcome_text = "APPROVED ✅" if approved else "CRL/REJECTED ❌"
    
    return f"""
🏁 <b>FDA DECISION</b>

<b>{ticker}</b> {outcome_text}
Our signal was: {signal}
Result: {result_emoji}

KAT P(Approval) was: {trade.get('p_approval', 0):.0%}
""".strip()


def alert_new_signal(event: dict):
    msg = format_signal_alert(event)
    log.info(f"Signal alert: {event.get('ticker')} {event.get('signal')}")
    send_telegram(msg)


def alert_briefing_released(drug: str, ticker: str, analysis: dict):
    msg = format_briefing_alert(drug, ticker, analysis)
    log.info(f"Briefing alert: {drug}, signal={analysis.get('approval_signal'):.0%}")
    send_telegram(msg)


def alert_t1_exit(trade: dict):
    msg = format_t1_exit_alert(trade)
    log.info(f"T-1 exit alert: {trade.get('ticker')}")
    send_telegram(msg)


def alert_fda_outcome(trade: dict, approved: bool):
    msg = format_outcome_alert(trade, approved)
    send_telegram(msg)


# ── Daily digest ───────────────────────────────────────────────────────────────
def send_daily_digest(scored_events: list):
    """Sends a daily summary of upcoming PDUFA signals."""
    today = date.today().strftime("%b %d, %Y")
    
    longs = [e for e in scored_events if e.get("signal") == "LONG" and e.get("days_to_pdufa", 99) >= 0]
    shorts = [e for e in scored_events if e.get("signal") == "SHORT" and e.get("days_to_pdufa", 99) >= 0]
    imminent = [e for e in scored_events if 0 <= e.get("days_to_pdufa", 99) <= 14]
    
    lines = [f"📅 <b>KAT PHARMA DAILY DIGEST — {today}</b>\n"]
    
    if imminent:
        lines.append("<b>⚡ IMMINENT (≤14 days):</b>")
        for e in imminent:
            lines.append(f"  • {e['ticker']} {e['pdufa_date']} T-{e['days_to_pdufa']} | {e['signal']} {e['p_approval']:.0%}")
    
    if longs:
        lines.append(f"\n<b>🟢 LONG SIGNALS ({len(longs)}):</b>")
        for e in longs[:5]:
            lines.append(f"  • {e['ticker']} {e['pdufa_date']} | {e['p_approval']:.0%} | ${e['dollar_size']:,.0f}")
    
    if shorts:
        lines.append(f"\n<b>🔴 SHORT SIGNALS ({len(shorts)}):</b>")
        for e in shorts[:3]:
            lines.append(f"  • {e['ticker']} {e['pdufa_date']} | {e['p_approval']:.0%} | ${e['dollar_size']:,.0f}")
    
    send_telegram("\n".join(lines))


if __name__ == "__main__":
    # Test alert formatting
    test_event = {
        "ticker": "VRDN",
        "drug": "Veligrotug",
        "indication": "Thyroid Eye Disease",
        "pdufa_date": "2026-06-30",
        "days_to_pdufa": 111,
        "signal": "LONG",
        "p_approval": 0.78,
        "kelly_fraction": 0.062,
        "dollar_size": 6200,
    }
    
    print("=== SIGNAL ALERT ===")
    print(format_signal_alert(test_event))
    
    print("\n=== T-1 EXIT ALERT ===")
    print(format_t1_exit_alert({**test_event, "contracts_remaining": 3}))
