"""
Order Scrutiny — PDF Data Extraction
Uses PyPDF2 for text extraction and Google Gemini for structured parsing.
"""

import json
import logging
import PyPDF2
from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ── Gemini Setup ─────────────────────────────────────────────

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _ask_gemini(prompt: str) -> dict:
    """Send prompt to Gemini and parse JSON response."""
    client = _get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    return json.loads(response.text)


# ── PDF Text Extraction ─────────────────────────────────────

def _extract_pdf_text(pdf_path: str, password: str = None) -> str:
    """Extract all text from a PDF, optionally decrypting."""
    reader = PyPDF2.PdfReader(pdf_path)
    if reader.is_encrypted:
        if not password:
            raise ValueError("PDF is encrypted. Please provide the password.")
        reader.decrypt(password)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"--- Page {i+1} ---\n{text}")
    return "\n\n".join(pages)


def _extract_english_pages(pdf_path: str, password: str) -> str:
    """Extract only English pages from Intimation PDF (skip Hindi)."""
    reader = PyPDF2.PdfReader(pdf_path)
    if reader.is_encrypted:
        reader.decrypt(password)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        # English pages contain structured headers like "Sl.No.", "Particulars"
        # and the text "Intimation u/s 143(1)" in English
        if "Particulars" in text or "Reporting Heads" in text or "RETURN DETAILS" in text:
            pages.append(f"--- Page {i+1} ---\n{text}")
        elif "Mismatch between Tax Credits" in text or "Notes:" in text:
            pages.append(f"--- Page {i+1} ---\n{text}")
    return "\n\n".join(pages)


# ── Computation Sheet Extraction ─────────────────────────────

COMP_SHEET_PROMPT = """You are an Indian Income Tax expert. Extract data from this Computation Sheet PDF text.
Return a JSON object with these exact keys. Use plain numbers (no commas). Use 0 for missing/blank values.

Required JSON keys:
{
  "entity_name": "string",
  "pan": "string",
  "assessment_year": "string (e.g. 2024-25)",
  "order_date": "string (DD/MM/YYYY)",
  "order_section": "string (e.g. 143(3))",
  "income_house_property": number,
  "income_business_profession": number,
  "income_capital_gains": number,
  "income_other_sources": number,
  "gross_total_income": number,
  "deduction_part_b": number,
  "deduction_part_c": number,
  "total_deductions_via": number,
  "deduction_10aa": number,
  "total_income": number,
  "income_special_rates": number,
  "income_normal_rates": number,
  "tax_normal_rates": number,
  "tax_115bbe": number,
  "tax_special_other": number,
  "tax_on_total_income": number,
  "surcharge_total": number,
  "cess": number,
  "gross_tax_liability": number,
  "net_tax_liability": number,
  "interest_234a": number,
  "interest_234b": number,
  "interest_234c": number,
  "interest_234d": number,
  "fee_234f": number,
  "total_interest_fee": number,
  "aggregate_liability": number,
  "tds": number,
  "tcs": number,
  "advance_tax": number,
  "self_assessment_tax": number,
  "regular_tax": number,
  "total_taxes_paid": number,
  "amount_payable_refund": number,
  "interest_244a": number,
  "refund_already_issued": number,
  "balance_payable_refundable": number,
  "demand_amount": number
}

Important:
- "refund_already_issued" should be a positive number
- "amount_payable_refund": negative means refund, positive means payable
- "demand_amount": the final demand/refund from point 58 or 62
- Parse Indian number format: 2,36,77,47,375 = 2367747375

PDF Text:
"""


def extract_computation_sheet(pdf_path: str, progress_cb=None) -> dict:
    """Extract structured data from a Computation Sheet PDF."""
    if progress_cb:
        progress_cb("extracting", "Reading Computation Sheet...", 0.1)

    text = _extract_pdf_text(pdf_path)
    logger.info(f"Computation Sheet: extracted {len(text)} chars")

    if progress_cb:
        progress_cb("extracting", "Parsing Computation Sheet with AI...", 0.2)

    data = _ask_gemini(COMP_SHEET_PROMPT + text)
    logger.info(f"Computation Sheet parsed: {data.get('entity_name')}, AY {data.get('assessment_year')}")
    return data


# ── Intimation Order Extraction ──────────────────────────────

INTIMATION_PROMPT = """You are an Indian Income Tax expert. Extract data from this Intimation u/s 143(1) PDF text.
The document has two columns: "As provided by Taxpayer" (ROI) and "As Computed u/s 143(1)".
Return a JSON object. Use plain numbers (no commas). Use 0 for missing/blank/N/A values.

Required JSON keys:
{
  "entity_name": "string",
  "pan": "string",
  "assessment_year": "string",
  "filing_date": "string (DD/MM/YYYY)",
  "intimation_date": "string (DD/MM/YYYY)",
  "roi": {
    "income_house_property": number,
    "income_business_profession": number,
    "income_capital_gains": number,
    "income_other_sources": number,
    "gross_total_income": number,
    "deduction_part_b": number,
    "deduction_part_c": number,
    "total_deductions_via": number,
    "deduction_10aa": number,
    "total_income": number,
    "tax_normal_rates": number,
    "tax_on_total_income": number,
    "surcharge_total": number,
    "cess": number,
    "gross_tax_liability": number,
    "net_tax_liability": number,
    "interest_234a": number,
    "interest_234b": number,
    "interest_234c": number,
    "fee_234f": number,
    "total_interest_fee": number,
    "aggregate_liability": number,
    "tds": number,
    "tcs": number,
    "advance_tax": number,
    "self_assessment_tax": number,
    "regular_tax": number,
    "total_taxes_paid": number,
    "refund_amount": number
  },
  "computed": {
    "income_house_property": number,
    "income_business_profession": number,
    "income_capital_gains": number,
    "income_other_sources": number,
    "gross_total_income": number,
    "deduction_part_b": number,
    "deduction_part_c": number,
    "total_deductions_via": number,
    "deduction_10aa": number,
    "total_income": number,
    "tax_normal_rates": number,
    "tax_on_total_income": number,
    "surcharge_total": number,
    "cess": number,
    "gross_tax_liability": number,
    "net_tax_liability": number,
    "interest_234a": number,
    "interest_234b": number,
    "interest_234c": number,
    "fee_234f": number,
    "total_interest_fee": number,
    "aggregate_liability": number,
    "tds": number,
    "tcs": number,
    "advance_tax": number,
    "self_assessment_tax": number,
    "regular_tax": number,
    "total_taxes_paid": number,
    "refund_amount": number,
    "interest_244a": number,
    "net_refundable": number
  }
}

Important:
- "roi" = "As provided by Taxpayer" column
- "computed" = "As Computed u/s 143(1)" column
- Parse Indian numbers: 2,32,53,22,706 = 2325322706
- The intimation has detailed line items (sl.no 01 through 46)

PDF Text:
"""


def extract_intimation_order(pdf_path: str, password: str, progress_cb=None) -> dict:
    """Extract structured data from an Intimation u/s 143(1) PDF."""
    if progress_cb:
        progress_cb("extracting", "Reading Intimation Order...", 0.3)

    text = _extract_english_pages(pdf_path, password)
    if not text.strip():
        # Fallback: try all pages
        text = _extract_pdf_text(pdf_path, password)
    logger.info(f"Intimation Order: extracted {len(text)} chars (English pages)")

    if progress_cb:
        progress_cb("extracting", "Parsing Intimation Order with AI...", 0.4)

    data = _ask_gemini(INTIMATION_PROMPT + text)
    logger.info(f"Intimation parsed: {data.get('entity_name')}, AY {data.get('assessment_year')}")
    return data


# ── Assessment Order Extraction (Optional) ───────────────────

AO_PROMPT = """You are an Indian Income Tax expert. Extract the additions/disallowances made by the Assessing Officer from this Assessment Order PDF.
Return a JSON object with:
{
  "additions": [
    {"description": "string describing the addition", "amount": number, "section": "relevant IT section if any"}
  ],
  "entity_name": "string",
  "assessment_year": "string"
}

Only include actual additions/disallowances with non-zero amounts.
Parse Indian numbers: 42,24,669 = 4224669

PDF Text:
"""


def extract_assessment_order(pdf_path: str, progress_cb=None) -> dict:
    """Extract additions from Assessment Order PDF (optional)."""
    if progress_cb:
        progress_cb("extracting", "Reading Assessment Order...", 0.5)

    text = _extract_pdf_text(pdf_path)
    logger.info(f"Assessment Order: extracted {len(text)} chars")

    if progress_cb:
        progress_cb("extracting", "Parsing Assessment Order with AI...", 0.55)

    data = _ask_gemini(AO_PROMPT + text)
    logger.info(f"Assessment Order parsed: {len(data.get('additions', []))} additions found")
    return data
