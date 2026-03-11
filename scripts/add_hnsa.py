#!/usr/bin/env python3
"""
add_hnsa.py — Add Hansa Biopharma (HNSA.ST) to KAT PDUFA database
PDUFA date: December 19, 2026 — Imlifidase (kidney transplant desensitization)

RUN:
    cd /root/katherina-trader/pharma
    python3 ../scripts/add_hnsa.py
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

PHARMA_DIR = Path(__file__).parent.parent / "pharma"
DB_PATH = PHARMA_DIR / "pdufa_events.db"

EVENT = {
    "ticker":           "HNSA",
    "drug_name":        "Imlifidase",
    "indication":       "Kidney Transplant Desensitization (sensitized patients, positive crossmatch)",
    "pdufa_date":       "2026-12-19",
    "exchange":         "STO",          # Stockholm, also trades OTC as HNSBF
    "currency":         "SEK",
    "event_type":       "BLA",
    "priority_review":  0,
    "breakthrough":     0,
    "orphan":           1,              # Rare disease — sensitized transplant patients
    "prior_crl":        0,              # No prior CRL, EU approved (Idefirix)
    "adcom_vote":       None,           # No AdCom scheduled yet
    "adcom_date":       None,
    "briefing_url":     None,
    "class_rate":       0.82,           # Enzyme/biologics for rare transplant — high class rate
    "notes":            (
        "BLA accepted by FDA ~Feb 2026. Imlifidase already EU-approved as Idefirix. "
        "Phase 3 trial met primary endpoint. Run-up trade: enter ~Oct 2026, exit T-1 (Dec 18). "
        "SNB 30-day hold: use call options on HNSBF (OTC US-listed ADR). "
        "Wedbush Outperform initiated Feb 2026. Cash SEK 701M, well-funded. "
        "Collaboration with Sarepta (DMD), AskBio (Pompe) adds optionality."
    ),
}

def main():
    if not DB_PATH.exists():
        print(f"✗ Database not found at {DB_PATH}")
        print("  Run: cd /root/katherina-trader/pharma && python3 pdufa_scraper.py first")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check table schema
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    print(f"Tables found: {table_names}")

    # Find the events table
    events_table = None
    for name in table_names:
        if "event" in name.lower() or "pdufa" in name.lower():
            events_table = name
            break

    if not events_table:
        print("✗ No events table found. Tables:", table_names)
        sys.exit(1)

    print(f"Using table: {events_table}")

    # Get column names
    cols = [c[1] for c in cursor.execute(f"PRAGMA table_info({events_table})").fetchall()]
    print(f"Columns: {cols}")

    # Check if HNSA already exists
    existing = cursor.execute(
        f"SELECT * FROM {events_table} WHERE ticker = 'HNSA'"
    ).fetchone()

    if existing:
        print("ℹ HNSA already in database — updating...")
        cursor.execute(f"DELETE FROM {events_table} WHERE ticker = 'HNSA'")

    # Build insert with only columns that exist in the table
    insert_data = {k: v for k, v in EVENT.items() if k in cols}

    placeholders = ", ".join(["?" for _ in insert_data])
    col_names = ", ".join(insert_data.keys())
    values = list(insert_data.values())

    cursor.execute(
        f"INSERT INTO {events_table} ({col_names}) VALUES ({placeholders})",
        values
    )
    conn.commit()

    # Verify
    row = cursor.execute(
        f"SELECT ticker, drug_name, pdufa_date FROM {events_table} WHERE ticker = 'HNSA'"
    ).fetchone()
    total = cursor.execute(f"SELECT COUNT(*) FROM {events_table}").fetchone()[0]

    conn.close()

    print(f"\n✓ Added: {row}")
    print(f"  Total events in DB: {total}")
    print(f"\nRun next:")
    print(f"  cd /root/katherina-trader/pharma && python3 orchestrator.py --score")

if __name__ == "__main__":
    main()
