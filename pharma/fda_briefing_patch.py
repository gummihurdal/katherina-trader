"""
fda_briefing_patch.py — KAT Pharma Module
==========================================
Patches analyze_drug() to use Claude general knowledge when no FDA briefing
PDF is available. Without this, every drug without a briefing URL scores 0.58.

RUN:
    python3 fda_briefing_patch.py             # score all 14 events
    python3 fda_briefing_patch.py --apply     # write import into features.py
    python3 fda_briefing_patch.py RCKT        # score one ticker
"""

import anthropic
import json
import logging
import os
import sys

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")


# ── Claude knowledge scorer ───────────────────────────────────────────────────

def claude_knowledge_score(drug_name: str, indication: str, ticker: str = "") -> dict:
    """Ask Claude to estimate FDA approval probability from general knowledge."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return {"drug": drug_name, "approval_signal": 0.58, "confidence": 0.0, "error": "no_api_key"}

    prompt = f"""You are an expert FDA drug approval analyst. Assess the probability of FDA approval for:

Drug: {drug_name}
Indication: {indication}
Ticker: {ticker or "N/A"}

Use everything you know about:
- Phase 3 trial results and primary endpoint achievement
- Safety profile and serious adverse events
- Drug class historical approval rates
- FDA precedents for similar drugs
- Breakthrough/Priority Review/Orphan designations
- Prior Complete Response Letters (CRLs)
- Unmet medical need and competitive landscape
- Advisory Committee vote history if applicable

Respond ONLY with a valid JSON object, no markdown fences, no commentary:
{{
  "drug": "{drug_name}",
  "indication": "{indication}",
  "approval_signal": <float 0.0-1.0>,
  "confidence": <float 0.0-1.0>,
  "fda_tone": "supportive" or "neutral" or "skeptical",
  "fda_concern_count": <int>,
  "prior_crl_mentioned": <bool>,
  "breakthrough_designation": <bool>,
  "priority_review": <bool>,
  "key_factors": {{
    "positive": ["<factor>"],
    "negative": ["<factor>"]
  }},
  "summary": "<2-3 sentence assessment>"
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        log.info(f"[{ticker or drug_name}] approval_signal={result.get('approval_signal'):.2f} "
                 f"confidence={result.get('confidence'):.2f} tone={result.get('fda_tone')}")
        return result
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse error for {drug_name}: {e}")
        return {"drug": drug_name, "approval_signal": 0.58, "confidence": 0.0, "error": "parse_error"}
    except Exception as e:
        log.warning(f"Claude API error for {drug_name}: {e}")
        return {"drug": drug_name, "approval_signal": 0.58, "confidence": 0.0, "error": str(e)}


# ── Patch fda_briefing.analyze_drug ──────────────────────────────────────────

def apply_patch():
    """Monkey-patch fda_briefing.analyze_drug to use Claude fallback."""
    try:
        import fda_briefing as _fb

        def _patched(drug_name, indication, briefing_url=None, briefing_text=None):
            if briefing_text is None and briefing_url:
                pdf_path = _fb.download_briefing_pdf(briefing_url, drug_name)
                if pdf_path:
                    briefing_text = _fb.extract_pdf_text(pdf_path)

            if briefing_text:
                return _fb.analyze_briefing_text(briefing_text, drug_name, indication)

            # No briefing doc — use Claude general knowledge
            log.info(f"No briefing doc for {drug_name} — using Claude general knowledge")
            result = claude_knowledge_score(drug_name, indication)
            try:
                _fb.save_analysis(drug_name, result)
            except Exception:
                pass
            return result

        _fb.analyze_drug = _patched
        log.info("fda_briefing_patch applied: Claude knowledge fallback active")
    except ImportError:
        log.warning("fda_briefing not found — run from pharma/ directory")


# Auto-apply on import
apply_patch()


# ── 2026 PDUFA Event List ─────────────────────────────────────────────────────

EVENTS_2026 = [
    ("ALDX", "Reproxalap",                "Dry Eye Disease"),
    ("RYTM", "IMCIVREE (setmelanotide)",   "Hypothalamic Obesity"),
    ("GSK",  "Linerixibat",               "PBC Pruritus"),
    ("RCKT", "Marnetegragene autotemcel", "LAD-I Gene Therapy"),
    ("DNLI", "Tividenofusp alfa",         "MPS II / Hunter Syndrome"),
    ("ORCA", "Orca-T",                    "AML/ALL/MDS"),
    ("SNY",  "Sarclisa (isatuximab)",      "Multiple Myeloma"),
    ("ARGX", "Vyvgart (efgartigimod)",    "Seroneg. Generalized MG"),
    ("AZN",  "Enhertu + THP",             "HER2+ Breast Cancer"),
    ("VRDN", "Veligrotug",                "Thyroid Eye Disease"),
    ("VERA", "Atacicept",                 "IgA Nephropathy"),
    ("PESI", "Besremi (ropeg.)",           "Essential Thrombocythemia"),
    ("NUVL", "Zidesamtinib",              "ROS1+ NSCLC"),
    ("INO",  "INO-3107",                  "HPV-Related Recurrent Resp. Papillomatosis"),
]


# ── CLI Modes ────────────────────────────────────────────────────────────────

def score_all():
    print(f"\n{'='*80}")
    print(f"KAT PHARMA — CLAUDE KNOWLEDGE SCORES")
    print(f"{'='*80}")
    print(f"{'TICK':<6}  {'P(APP)':>6}  {'CONF':>5}  {'TONE':<12}  {'DRUG'}")
    print(f"{'-'*80}")

    results = []
    for ticker, drug, indication in EVENTS_2026:
        result = claude_knowledge_score(drug, indication, ticker)
        signal = result.get("approval_signal", 0.58)
        conf   = result.get("confidence", 0.0)
        tone   = result.get("fda_tone", "unknown")
        print(f"{ticker:<6}  {signal*100:>5.0f}%  {conf*100:>4.0f}%  {tone:<12}  {drug}")
        results.append((ticker, drug, signal, result))

    print(f"{'='*80}")
    print(f"\nLONG  signals (>62%): {[r[0] for r in results if r[2] > 0.62]}")
    print(f"SHORT signals (<38%): {[r[0] for r in results if r[2] < 0.38]}")

    output = {e[0]: e[3] for e in results}
    with open("claude_scores_2026.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nFull results saved to claude_scores_2026.json\n")


def score_one(ticker: str):
    match = next((e for e in EVENTS_2026 if e[0].upper() == ticker.upper()), None)
    if not match:
        print(f"Ticker {ticker} not in 2026 event list")
        sys.exit(1)
    ticker, drug, indication = match
    result = claude_knowledge_score(drug, indication, ticker)
    print(json.dumps(result, indent=2))


def write_import_to_features():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "features.py")
    if not os.path.exists(path):
        print(f"features.py not found at {path}")
        return
    with open(path) as f:
        content = f.read()
    if "fda_briefing_patch" in content:
        print("features.py already imports fda_briefing_patch — nothing to do")
        return
    lines = content.split("\n")
    lines.insert(1, "import fda_briefing_patch  # noqa: Claude knowledge fallback")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print("✓ Added 'import fda_briefing_patch' to features.py line 2")


if __name__ == "__main__":
    if "--apply" in sys.argv:
        write_import_to_features()
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        score_one(sys.argv[1])
    else:
        score_all()
