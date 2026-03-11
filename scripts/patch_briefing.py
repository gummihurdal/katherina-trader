#!/usr/bin/env python3
"""
patch_briefing.py — KAT Pharma
================================
Patches fda_briefing.py to call Claude general knowledge
when no FDA briefing PDF is available (instead of returning 0.58).

USAGE (run from anywhere on Hetzner):
    cd /root/katherina-trader
    python3 scripts/patch_briefing.py          # apply patch
    python3 scripts/patch_briefing.py --check  # verify patch status
    python3 scripts/patch_briefing.py --revert # restore original
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

PHARMA_DIR = Path(__file__).parent.parent / "pharma"
TARGET = PHARMA_DIR / "fda_briefing.py"
BACKUP = PHARMA_DIR / "fda_briefing.py.bak"

OLD_BLOCK = '''    if not briefing_text:
        log.warning(f"No briefing text available for {drug_name}. Returning neutral score.")
        return {
            "drug": drug_name,
            "indication": indication,
            "approval_signal": 0.58,  # base rate fallback
            "fda_tone": "unknown",
            "fda_concern_count": 0,
            "error": "no_briefing_available"
        }'''

NEW_BLOCK = '''    if not briefing_text:
        log.info(f"No briefing doc for {drug_name} — using Claude general knowledge")
        import os as _os, json as _json
        _api_key = _os.environ.get("ANTHROPIC_API_KEY")
        if not _api_key:
            log.warning("ANTHROPIC_API_KEY not set — returning base rate")
            return {"drug": drug_name, "indication": indication,
                    "approval_signal": 0.58, "error": "no_api_key"}
        try:
            import anthropic as _anthropic
            _client = _anthropic.Anthropic(api_key=_api_key)
            _prompt = (
                f"You are an expert FDA drug approval analyst.\\n"
                f"Assess the probability of FDA approval for {drug_name} ({indication}).\\n"
                f"Use your knowledge of: trial results, safety, drug class precedents, "
                f"designations (BTD/Priority/Orphan), prior CRLs, unmet medical need.\\n"
                f"Respond ONLY with valid JSON, no markdown fences:\\n"
                f'{{"drug":"{drug_name}","indication":"{indication}",'
                f'"approval_signal":<float 0-1>,"confidence":<float 0-1>,'
                f'"fda_tone":"supportive/neutral/skeptical","fda_concern_count":<int>,'
                f'"prior_crl_mentioned":<bool>,"breakthrough_designation":<bool>,'
                f'"priority_review":<bool>,'
                f'"key_factors":{{"positive":[],"negative":[]}},'
                f'"summary":"<2-3 sentence assessment>"}}'
            )
            _msg = _client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                messages=[{"role": "user", "content": _prompt}]
            )
            _raw = _msg.content[0].text.strip()
            if "```" in _raw:
                _raw = _raw.split("```")[1]
                if _raw.startswith("json"):
                    _raw = _raw[4:]
            _result = _json.loads(_raw.strip())
            log.info(f"Claude knowledge score for {drug_name}: {_result.get('approval_signal')}")
            return _result
        except Exception as _e:
            log.warning(f"Claude knowledge fallback failed for {drug_name}: {_e}")
            return {"drug": drug_name, "indication": indication,
                    "approval_signal": 0.58, "error": str(_e)}'''


def check():
    content = TARGET.read_text()
    if "Claude general knowledge" in content:
        print("✓ Patch is ACTIVE — Claude knowledge fallback is live")
    elif "Returning neutral score" in content:
        print("✗ Patch NOT applied — fda_briefing.py still returns 0.58 base rate")
    else:
        print("? Unknown state — inspect fda_briefing.py manually")


def apply():
    if not TARGET.exists():
        print(f"✗ Target not found: {TARGET}")
        sys.exit(1)

    content = TARGET.read_text()

    if "Claude general knowledge" in content:
        print("✓ Patch already applied — nothing to do")
        return

    if OLD_BLOCK not in content:
        print("✗ Could not find target block in fda_briefing.py")
        print("  The file may have changed — inspect manually")
        sys.exit(1)

    # Backup original
    shutil.copy(TARGET, BACKUP)
    print(f"  Backup saved to {BACKUP}")

    # Apply patch
    new_content = content.replace(OLD_BLOCK, NEW_BLOCK)
    TARGET.write_text(new_content)
    print(f"✓ Patch applied to {TARGET}")

    # Clear stale briefing cache
    briefings_dir = PHARMA_DIR / "briefings"
    cleared = 0
    if briefings_dir.exists():
        for f in briefings_dir.glob("*.json"):
            f.unlink()
            cleared += 1
    print(f"  Cleared {cleared} cached briefing files")
    print()
    print("Run next:")
    print("  cd /root/katherina-trader/pharma && python3 orchestrator.py --score")


def revert():
    if not BACKUP.exists():
        print(f"✗ No backup found at {BACKUP}")
        sys.exit(1)
    shutil.copy(BACKUP, TARGET)
    print(f"✓ Reverted {TARGET} from backup")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    elif "--revert" in sys.argv:
        revert()
    else:
        apply()
