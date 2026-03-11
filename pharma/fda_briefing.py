"""
fda_briefing.py — Download FDA briefing docs + analyze with Claude API
This is the highest-alpha module. The 48hr window after briefing doc release
is the best entry point in the entire PDUFA trade lifecycle.
"""

import os
import re
import json
import time
import logging
import hashlib
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import anthropic

from config import BRIEFING_DIR, ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS

log = logging.getLogger(__name__)

BRIEFING_DIR.mkdir(exist_ok=True)

# ── FDA AdCom calendar scraper ────────────────────────────────────────────────
FDA_ADCOM_URL = "https://www.fda.gov/advisory-committees/advisory-committee-calendar"

SYSTEM_PROMPT = """You are a senior FDA regulatory analyst specializing in drug approval probability assessment. 
You analyze FDA briefing documents and advisory committee materials to assess approval likelihood.
You output only structured JSON — no preamble, no markdown, no explanation outside the JSON object."""

ANALYSIS_PROMPT = """Analyze this FDA briefing document for {drug_name} ({indication}).

Extract and score the following, returning ONLY a JSON object:

{{
  "drug": "{drug_name}",
  "indication": "{indication}",
  "primary_endpoint_met": true/false/null,
  "primary_endpoint_pvalue": "e.g. p=0.0023 or null",
  "key_efficacy_data": "1-2 sentence summary of main efficacy finding",
  
  "fda_concern_count": integer (count of distinct FDA concerns/questions),
  "fda_concern_severity": "low/medium/high",
  "fda_concerns_list": ["concern 1", "concern 2", ...],
  
  "safety_flags": ["flag 1", ...],
  "safety_severity": "low/medium/high",
  "deaths_in_trial": true/false/null,
  "serious_adverse_events_pct": float or null,
  
  "manufacturing_cmc_issues": true/false,
  "rems_likely": true/false,
  "label_restriction_risk": "none/moderate/severe",
  
  "fda_tone": "supportive/neutral/skeptical/adversarial",
  "fda_tone_score": float between 0.0 (adversarial) and 1.0 (supportive),
  
  "comparator_advantage": "none/marginal/clear/substantial",
  "unmet_medical_need": "low/medium/high/critical",
  
  "prior_class_crl_risk": true/false,
  "novel_mechanism": true/false,
  
  "approval_signal": float between 0.0 and 1.0,
  "approval_signal_rationale": "2-3 sentence explanation",
  
  "key_questions_to_committee": ["question 1", "question 2", ...],
  "analyst_notes": "any important nuances not captured above"
}}

Document text:
{text}"""


# ── PDF downloader ─────────────────────────────────────────────────────────────
def download_briefing_pdf(url: str, drug_name: str) -> Optional[Path]:
    """Downloads FDA briefing doc PDF to local cache."""
    cache_name = hashlib.md5(url.encode()).hexdigest()[:12] + ".pdf"
    cache_path = BRIEFING_DIR / cache_name
    
    if cache_path.exists():
        log.info(f"Briefing doc cached: {cache_path}")
        return cache_path
    
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; KAT-Pharma/1.0)"}
        r = requests.get(url, headers=headers, timeout=60, stream=True)
        r.raise_for_status()
        with open(cache_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        log.info(f"Downloaded briefing doc: {cache_path} ({cache_path.stat().st_size // 1024}KB)")
        return cache_path
    except Exception as e:
        log.error(f"Failed to download briefing doc for {drug_name}: {e}")
        return None


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF using pypdf2."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        full_text = "\n".join(texts)
        log.info(f"Extracted {len(full_text)} chars from {pdf_path.name}")
        return full_text
    except ImportError:
        log.warning("pypdf not installed. Run: pip install pypdf --break-system-packages")
        return ""
    except Exception as e:
        log.error(f"PDF extraction failed: {e}")
        return ""


# ── Claude API analyzer ────────────────────────────────────────────────────────
def analyze_briefing_text(text: str, drug_name: str, indication: str) -> dict:
    """
    Sends briefing doc text to Claude API and returns structured JSON analysis.
    This is the core alpha-generating function of the pharma module.
    
    Token budget: briefing docs are 80-120 pages.
    We truncate to 80k chars (~20k tokens) to stay within context limits.
    The most critical content is in the Executive Summary and FDA Questions sections.
    """
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY not set")
        return {"error": "no_api_key", "approval_signal": 0.5}

    # Smart truncation: prioritize executive summary + FDA questions sections
    text_lower = text.lower()
    truncated = _smart_truncate(text, text_lower, max_chars=80_000)
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    prompt = ANALYSIS_PROMPT.format(
        drug_name=drug_name,
        indication=indication,
        text=truncated
    )
    
    try:
        log.info(f"Sending briefing doc to Claude API for {drug_name} ({len(truncated)} chars)...")
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw = response.content[0].text.strip()
        # Strip any accidental markdown fences
        raw = re.sub(r"```json|```", "", raw).strip()
        
        result = json.loads(raw)
        result["analyzed_at"] = datetime.utcnow().isoformat()
        result["chars_analyzed"] = len(truncated)
        
        log.info(f"Briefing analysis complete: approval_signal={result.get('approval_signal')}, tone={result.get('fda_tone')}")
        return result
        
    except json.JSONDecodeError as e:
        log.error(f"Claude returned invalid JSON: {e}\nRaw: {raw[:500]}")
        return {"error": "json_parse_error", "approval_signal": 0.5, "raw": raw}
    except Exception as e:
        log.error(f"Claude API error: {e}")
        return {"error": str(e), "approval_signal": 0.5}


def _smart_truncate(text: str, text_lower: str, max_chars: int) -> str:
    """
    Prioritizes high-signal sections of FDA briefing docs:
    1. Executive Summary (usually first 15k chars)
    2. FDA Questions to Advisory Committee (usually last 10k chars)
    3. Safety section
    4. Primary endpoint results
    """
    if len(text) <= max_chars:
        return text
    
    # Always include: first 20k (intro/executive summary)
    head = text[:20_000]
    # Always include: last 15k (FDA questions to committee, usually at end)
    tail = text[-15_000:]
    
    # Try to find and include safety and efficacy sections
    sections = []
    for keyword in ["primary endpoint", "efficacy results", "safety results", 
                    "questions for committee", "discussion questions", "risk-benefit"]:
        idx = text_lower.find(keyword)
        if idx > 0:
            sections.append(text[max(0, idx-500):min(len(text), idx+5000)])
    
    middle = "\n\n[...TRUNCATED...]\n\n".join(sections[:3])
    combined = head + "\n\n[...]\n\n" + middle + "\n\n[...]\n\n" + tail
    
    return combined[:max_chars]


# ── Full pipeline for one drug ────────────────────────────────────────────────
def analyze_drug(drug_name: str, indication: str, 
                 briefing_url: Optional[str] = None,
                 briefing_text: Optional[str] = None) -> dict:
    """
    Full briefing document analysis pipeline.
    Pass either briefing_url (PDF to download) or briefing_text (already extracted).
    Returns structured analysis dict.
    """
    if briefing_text is None and briefing_url:
        pdf_path = download_briefing_pdf(briefing_url, drug_name)
        if pdf_path:
            briefing_text = extract_pdf_text(pdf_path)
    
    if not briefing_text:
        log.warning(f"No briefing text available for {drug_name}. Returning neutral score.")
        return {
            "drug": drug_name,
            "indication": indication,
            "approval_signal": 0.58,  # base rate fallback
            "fda_tone": "unknown",
            "fda_concern_count": 0,
            "error": "no_briefing_available"
        }
    
    return analyze_briefing_text(briefing_text, drug_name, indication)


# ── AdCom vote monitor ────────────────────────────────────────────────────────
def monitor_adcom_releases():
    """
    Checks FDA AdCom calendar for newly posted briefing documents.
    Run daily. When a new briefing doc appears, triggers analyze_drug().
    Returns list of newly discovered briefing docs.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    new_docs = []
    
    try:
        r = requests.get(FDA_ADCOM_URL, headers=headers, timeout=15)
        soup = __import__("bs4").BeautifulSoup(r.text, "html.parser")
        
        # Find all PDF links on the page
        for link in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)):
            href = link.get("href", "")
            if not href.startswith("http"):
                href = "https://www.fda.gov" + href
            
            # Check if we've already processed this URL
            cache_name = hashlib.md5(href.encode()).hexdigest()[:12] + ".pdf"
            if not (BRIEFING_DIR / cache_name).exists():
                log.info(f"New briefing doc found: {href}")
                new_docs.append(href)
        
        log.info(f"AdCom monitor: found {len(new_docs)} new briefing docs")
        return new_docs
    except Exception as e:
        log.error(f"AdCom monitor failed: {e}")
        return []


# ── Cache management ──────────────────────────────────────────────────────────
def save_analysis(drug_name: str, analysis: dict):
    """Saves analysis result to JSON cache."""
    fname = re.sub(r"[^\w]", "_", drug_name.lower()) + "_analysis.json"
    path = BRIEFING_DIR / fname
    with open(path, "w") as f:
        json.dump(analysis, f, indent=2)
    log.info(f"Analysis saved: {path}")
    return path


def load_analysis(drug_name: str) -> Optional[dict]:
    """Loads cached analysis if available and fresh (<7 days old)."""
    fname = re.sub(r"[^\w]", "_", drug_name.lower()) + "_analysis.json"
    path = BRIEFING_DIR / fname
    if not path.exists():
        return None
    
    # Check freshness
    age_days = (time.time() - path.stat().st_mtime) / 86400
    if age_days > 7:
        log.info(f"Stale analysis for {drug_name} ({age_days:.1f} days old)")
        return None
    
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    # Test with a simple text snippet (no real briefing doc needed)
    test_text = """
    EXECUTIVE SUMMARY
    The applicant submitted a New Drug Application for reproxalap ophthalmic solution 
    0.25% for the treatment of signs and symptoms of dry eye disease (DED).
    
    PRIMARY ENDPOINT RESULTS
    The primary endpoint of Schirmer's test score was not met in Study 1 (p=0.087).
    The primary symptom endpoint (OPSS) showed a numerical improvement but did not 
    reach statistical significance (p=0.12).
    
    FDA CONCERNS
    1. The two adequate and well-controlled trials required were not completed.
    2. The mechanism of action supporting efficacy remains unclear.
    3. Reproducibility of clinical benefit has not been demonstrated.
    
    QUESTIONS FOR THE ADVISORY COMMITTEE
    1. Has the applicant provided substantial evidence of effectiveness from at least
       two adequate and well-controlled trials?
    2. Does the benefit-risk profile support approval?
    """
    
    result = analyze_briefing_text(test_text, "Reproxalap", "Dry Eye Disease")
    print(json.dumps(result, indent=2))
