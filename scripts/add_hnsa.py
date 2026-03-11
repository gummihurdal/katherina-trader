#!/usr/bin/env python3
"""
add_hnsa.py — Add Hansa Biopharma (HNSA) to KAT PDUFA seed list
Patches pdufa_scraper.py to include HNSA PDUFA Dec 19, 2026

RUN:
    cd /root/katherina-trader
    python3 scripts/add_hnsa.py          # apply
    python3 scripts/add_hnsa.py --check  # verify
"""

import sys
from pathlib import Path

PHARMA_DIR = Path(__file__).parent.parent / "pharma"
TARGET = PHARMA_DIR / "pdufa_scraper.py"

HNSA_LINE = (
    '    PDUFAEvent("HNSA",    "Hansa Biopharma",        "Imlifidase",             '
    '"Kidney Transplant Desensitization","2026-12-19", "BLA",              '
    '0, False, False, "small", 0.55, None, None, None, '
    '"EU-approved as Idefirix. Phase 3 met primary endpoint. FDA BLA accepted Feb 2026. '
    'Run-up trade: enter Oct 2026, exit T-1. Trade HNSBF options (OTC US) for SNB compliance.", "seed"),'
)

# Anchor: insert after the last seed event (INO line)
ANCHOR = '    PDUFAEvent("INO",'


def check():
    content = TARGET.read_text()
    if "HNSA" in content:
        print("✓ HNSA is already in pdufa_scraper.py")
    else:
        print("✗ HNSA not found in pdufa_scraper.py — run without --check to add")


def apply():
    if not TARGET.exists():
        print(f"✗ File not found: {TARGET}")
        sys.exit(1)

    content = TARGET.read_text()

    if "HNSA" in content:
        print("✓ HNSA already present — nothing to do")
        return

    # Find the INO line and insert HNSA after it
    lines = content.split("\n")
    insert_idx = None
    for i, line in enumerate(lines):
        if ANCHOR in line:
            insert_idx = i + 1  # insert after INO line
            break

    if insert_idx is None:
        print("✗ Could not find INO anchor line in pdufa_scraper.py")
        sys.exit(1)

    lines.insert(insert_idx, HNSA_LINE)
    TARGET.write_text("\n".join(lines))
    print(f"✓ HNSA added to pdufa_scraper.py at line {insert_idx + 1}")
    print()
    print("Run next:")
    print("  cd /root/katherina-trader/pharma && python3 orchestrator.py --score")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        apply()
