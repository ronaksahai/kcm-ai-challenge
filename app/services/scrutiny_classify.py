"""
Order Scrutiny — Document Classification Service
Identifies document types from filenames (fast) with AI fallback (for unrecognized files).
"""

import os
import re
import json
import logging

import pdfplumber

logger = logging.getLogger(__name__)

# ── Document Types ───────────────────────────────────────────
DOC_TYPES = {
    "computation_sheet":  "Computation Sheet",
    "intimation_order":   "Intimation Order / ITR",
    "assessment_order":   "Assessment Order",
    "cita_order":         "CIT(A) Order u/s 250",
    "cita_comp_sheet":    "CIT(A) Computation Sheet",
}

# ── Filename Pattern Rules ───────────────────────────────────
# Each rule: (doc_type, compiled_regex, priority)
# Higher priority wins when multiple patterns match.
_RULES = [
    # CIT(A) computation / OGE — must come before generic computation
    ("cita_comp_sheet", re.compile(
        r"(giving\s*effect|OGE).*(computation|comp)",
        re.IGNORECASE), 100),
    ("cita_comp_sheet", re.compile(
        r"(computation|comp).*(giving\s*effect|OGE)",
        re.IGNORECASE), 100),

    # CIT(A) order — must come before generic order patterns
    ("cita_order", re.compile(
        r"CIT\s*[\(\-]?\s*A\s*\)?",
        re.IGNORECASE), 90),
    ("cita_order", re.compile(
        r"(order|appeal).*(u/?s\s*250|section\s*250)",
        re.IGNORECASE), 90),
    ("cita_order", re.compile(
        r"(u/?s\s*250|section\s*250).*(order|appeal)",
        re.IGNORECASE), 90),

    # Computation Sheet
    ("computation_sheet", re.compile(
        r"computation\s*sheet",
        re.IGNORECASE), 80),
    ("computation_sheet", re.compile(
        r"comp[\s_]sheet",
        re.IGNORECASE), 80),
    ("computation_sheet", re.compile(
        r"Computation\s*Sheet\s*for\s*ITR",
        re.IGNORECASE), 85),

    # Intimation Order / ITR / ROI
    ("intimation_order", re.compile(
        r"143\s*\(\s*1\s*\)",
        re.IGNORECASE), 95),
    ("intimation_order", re.compile(
        r"intimation",
        re.IGNORECASE), 85),
    ("intimation_order", re.compile(
        r"IntimationOrder",
        re.IGNORECASE), 85),
    ("intimation_order", re.compile(
        r"\bITR\b",
        re.IGNORECASE), 60),
    ("intimation_order", re.compile(
        r"\bROI\b",
        re.IGNORECASE), 60),

    # Assessment Order — various sections
    ("assessment_order", re.compile(
        r"order\s*u/?s\s*(143\s*\(\s*3\s*\)|147|144|153[A-C]?|92CA)",
        re.IGNORECASE), 80),
    ("assessment_order", re.compile(
        r"(u/?s\s*(143\s*\(\s*3\s*\)|147|144|153[A-C]?|92CA)).*order",
        re.IGNORECASE), 80),
    ("assessment_order", re.compile(
        r"assessment\s*order",
        re.IGNORECASE), 70),
    ("assessment_order", re.compile(
        r"Order\s*us\s*(143|147|144|153|92)",
        re.IGNORECASE), 80),
]

# ── Date Extraction from Filename ────────────────────────────
_DATE_PATTERNS = [
    # DD_MM_YYYY
    re.compile(r"(\d{2})_(\d{2})_(\d{4})"),
    # DD-MM-YYYY or DD/MM/YYYY
    re.compile(r"(\d{2})[-/](\d{2})[-/](\d{4})"),
    # DDMMYYYY (e.g., _28092022) with boundary to avoid matching inside PAN+DOB
    re.compile(r"(?:^|[_ -])(\d{2})(\d{2})(\d{4})(?:$|[_ -])"),
]

def _extract_date_from_filename(filename: str) -> str | None:
    """Try to extract a date (DD/MM/YYYY) from the filename."""
    base = os.path.splitext(os.path.basename(filename))[0]
    
    best_date = None
    best_pos = -1

    for pat in _DATE_PATTERNS:
        for m in pat.finditer(base):
            dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
            # Basic sanity check
            if 1 <= int(dd) <= 31 and 1 <= int(mm) <= 12 and 1900 <= int(yyyy) <= 2100:
                # Prefer dates appearing later in the filename
                if m.start() > best_pos:
                    best_date = f"{dd}/{mm}/{yyyy}"
                    best_pos = m.start()
                    
    return best_date


def classify_by_filename(filename: str) -> dict:
    """
    Classify a document by its filename using pattern matching.
    Returns: {type, label, confidence, date}
    """
    base = os.path.splitext(os.path.basename(filename))[0]
    best_type = None
    best_priority = -1

    for doc_type, pattern, priority in _RULES:
        if pattern.search(base) and priority > best_priority:
            best_type = doc_type
            best_priority = priority

    date = _extract_date_from_filename(filename)

    if best_type:
        return {
            "type": best_type,
            "label": DOC_TYPES[best_type],
            "confidence": "high",
            "date": date,
            "method": "filename",
        }

    return {
        "type": None,
        "label": "Unknown",
        "confidence": "none",
        "date": date,
        "method": "filename",
    }


def classify_by_ai(pdf_path: str) -> dict:
    """
    Classify a document using AI by extracting the first 2 pages of text
    and sending them to Gemini.
    Returns: {type, label, confidence, date}
    """
    import time
    from google import genai
    from google.genai import types, errors
    from app.config import GEMINI_MODEL
    from app.services.scrutiny_extract import _get_client

    # Extract first 2 pages of text
    text = ""
    try:
        with pdfplumber.open(pdf_path) as doc:
            for i, page in enumerate(doc.pages[:2]):
                page_text = page.extract_text() or ""
                text += f"--- Page {i+1} ---\n{page_text}\n\n"
    except Exception as e:
        logger.warning(f"Could not extract text from {pdf_path}: {e}")
        # Try without password
        text = ""

    if not text.strip():
        return {
            "type": None,
            "label": "Unknown (no text)",
            "confidence": "none",
            "date": None,
            "method": "ai",
        }

    prompt = f"""Classify this Indian Income Tax document into one of these types:
- computation_sheet: Computation sheet as given by the AO
- intimation_order: Intimation u/s 143(1) or ITR (Return of Income)
- assessment_order: Assessment order u/s 143(3), 147, 144, 153A/B/C, or 92CA
- cita_order: CIT(A) appeal order u/s 250
- cita_comp_sheet: Order Giving Effect (OGE) computation after CIT(A)

Also extract the order/filing date if visible.

Return JSON: {{"type": "one_of_above_or_null", "date": "DD/MM/YYYY or null"}}

DOCUMENT TEXT (first 2 pages):
{text[:5000]}"""

    client = _get_client()

    models_to_try = [GEMINI_MODEL]
    for fallback in ["gemini-3.5-flash", "gemini-2.5-pro", "gemini-2.5-flash"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    for model_name in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                result = json.loads(response.text)
                doc_type = result.get("type")
                if doc_type and doc_type in DOC_TYPES:
                    return {
                        "type": doc_type,
                        "label": DOC_TYPES[doc_type],
                        "confidence": "medium",
                        "date": result.get("date"),
                        "method": "ai",
                    }
                return {
                    "type": None,
                    "label": "Unknown",
                    "confidence": "low",
                    "date": result.get("date"),
                    "method": "ai",
                }
            except errors.APIError as e:
                if "503" in str(e) or getattr(e, 'code', None) == 503:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    else:
                        break
                else:
                    logger.error(f"AI classify error with {model_name}: {e}")
                    break
            except Exception as e:
                logger.error(f"AI classify unexpected error: {e}")
                break

    return {
        "type": None,
        "label": "Unknown",
        "confidence": "none",
        "date": None,
        "method": "ai_failed",
    }


def classify_files(file_paths: list[tuple[str, str]]) -> list[dict]:
    """
    Classify a list of (original_filename, saved_path) tuples.
    Uses filename matching first, AI fallback for unknowns.
    Returns list of {filename, type, label, confidence, date, method}.
    """
    results = []
    ai_needed = []

    for original_name, saved_path in file_paths:
        result = classify_by_filename(original_name)
        result["filename"] = original_name
        result["saved_path"] = saved_path

        if result["type"] is None:
            ai_needed.append((len(results), saved_path))

        results.append(result)

    # Run AI classification for unknowns
    for idx, saved_path in ai_needed:
        logger.info(f"AI classifying: {results[idx]['filename']}")
        ai_result = classify_by_ai(saved_path)
        results[idx].update({
            "type": ai_result["type"],
            "label": ai_result["label"],
            "confidence": ai_result["confidence"],
            "date": ai_result.get("date") or results[idx].get("date"),
            "method": ai_result["method"],
        })

    return results
