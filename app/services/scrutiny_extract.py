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
    """Send prompt to Gemini and parse JSON response, with retry and fallback."""
    import time
    from google.genai import errors
    client = _get_client()
    
    models_to_try = [GEMINI_MODEL]
    if GEMINI_MODEL != "gemini-2.5-flash":
        models_to_try.append("gemini-2.5-flash")

    max_retries = 3
    
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                return json.loads(response.text)
            except errors.APIError as e:
                if "503" in str(e) or getattr(e, 'code', None) == 503:
                    if attempt < max_retries - 1:
                        sleep_time = 2 ** attempt
                        logger.warning(f"Model {model_name} overloaded (503). Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        logger.error(f"Model {model_name} overloaded (503). Exhausted retries.")
                        break  # Fall back to next model
                else:
                    logger.error(f"API Error with model {model_name}: {e}")
                    break  # Fall back on other API errors (like 404)
            except Exception as e:
                logger.error(f"Unexpected error with model {model_name}: {e}")
                break
                
    raise RuntimeError(f"Failed to generate content with Gemini API. Please try again later.")


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
        if not password:
            raise ValueError("PDF is encrypted. Please provide the password.")
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
  "current_year_loss_setoff": number,
  "brought_forward_loss_setoff": number,
  "gross_total_income": number,
  "deduction_part_b": number,
  "deduction_part_c": number,
  "total_deductions_via": number,
  "deduction_10aa": number,
  "total_income": number,
  "loss_carried_forward": number,
  "income_special_rates": number,
  "income_normal_rates": number,
  "tax_normal_rates": number,
  "tax_115bbe": number,
  "tax_special_other": number,
  "tax_on_total_income": number,
  "income_115jb": number,
  "tax_115jb": number,
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

INTIMATION_PROMPT = """You are an Indian Income Tax expert. Extract data from this Intimation u/s 143(1) OR Income Tax Return (ITR) PDF text.
If the document is an Intimation Order, it has two columns: "As provided by Taxpayer" (ROI) and "As Computed u/s 143(1)".
If the document is an ITR, it only has the return of income details. In this case, set "is_itr" to true, populate the "roi" object, and leave "computed" as null or empty.
Return a JSON object. Use plain numbers (no commas). Use 0 for missing/blank/N/A values.

Required JSON keys:
{
  "is_itr": "boolean (true if this is an ITR, false if it's an Intimation)",
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
    "current_year_loss_setoff": number,
    "brought_forward_loss_setoff": number,
    "gross_total_income": number,
    "deduction_part_b": number,
    "deduction_part_c": number,
    "total_deductions_via": number,
    "deduction_10aa": number,
    "total_income": number,
    "loss_carried_forward": number,
    "tax_normal_rates": number,
    "tax_on_total_income": number,
    "income_115jb": number,
    "tax_115jb": number,
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
    "refund_amount": number
  },
  "computed": {
    "income_house_property": number,
    "income_business_profession": number,
    "income_capital_gains": number,
    "income_other_sources": number,
    "current_year_loss_setoff": number,
    "brought_forward_loss_setoff": number,
    "gross_total_income": number,
    "deduction_part_b": number,
    "deduction_part_c": number,
    "total_deductions_via": number,
    "deduction_10aa": number,
    "total_income": number,
    "loss_carried_forward": number,
    "tax_normal_rates": number,
    "tax_on_total_income": number,
    "income_115jb": number,
    "tax_115jb": number,
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

    # Extract all text to check if it's an ITR
    full_text = _extract_pdf_text(pdf_path, password)
    
    if "INDIAN INCOME TAX RETURN" in full_text.upper()[:2000] or "ITR" in full_text[:1000] or "PART A-GEN" in full_text.upper()[:1000]:
        text = full_text
        logger.info(f"ITR detected: extracted {len(text)} chars")
    else:
        text = _extract_english_pages(pdf_path, password)
        if not text.strip():
            # Fallback: try all pages
            text = full_text
        logger.info(f"Intimation Order: extracted {len(text)} chars (English pages)")

    if progress_cb:
        progress_cb("extracting", "Parsing Intimation Order with AI...", 0.4)

    data = _ask_gemini(INTIMATION_PROMPT + text)
    logger.info(f"Intimation parsed: {data.get('entity_name')}, AY {data.get('assessment_year')}")
    return data


# ── Assessment Order Extraction (Required) ───────────────────

AO_PROMPT = """You are an Indian Income Tax expert. Extract structured data from this Assessment Order PDF.

The Assessment Order typically contains a "Final Table of Taxable Computation" or similar computation sheet at the end.
This table lists the income as per return, adjustments, and the total assessed income.

Return a JSON object with:
{
  "entity_name": "string",
  "assessment_year": "string (e.g. 2016-17)",
  "order_date": "string (DD/MM/YYYY)",
  "order_section": "string (e.g. 143(3))",
  "total_assessed_income": number,
  "income_as_per_return": number,
  "additions": [
    {
      "description": "string - the exact description of the addition/variation as stated in the order",
      "amount": number,
      "section": "relevant IT section if mentioned (e.g. 43B, 40(a)(ia), 32, etc.)",
      "head_of_income": "which head of income this addition falls under: House Property / Business or Profession / Capital Gains / Other Sources"
    }
  ]
}

Instructions:
- In "additions", include EVERY addition/variation/disallowance listed in the computation table of the order, with non-zero amounts.
- "description" should capture the exact wording (e.g. "Variation in respect of issue of Disallowance u/s 43B")
- "head_of_income" should be the income head under which this addition falls. Most additions fall under "Business or Profession".
- "amount" should be a plain number without commas
- Parse Indian number format: 1,02,25,077 = 10225077, 1,85,20,733 = 18520733
- Do NOT include totals or sub-totals as additions — only individual items

PDF Text:
"""


def extract_assessment_order(pdf_path: str, progress_cb=None) -> dict:
    """Extract additions and computation table from Assessment Order PDF."""
    if progress_cb:
        progress_cb("extracting", "Reading Assessment Order...", 0.45)

    text = _extract_pdf_text(pdf_path)
    logger.info(f"Assessment Order: extracted {len(text)} chars")

    if progress_cb:
        progress_cb("extracting", "Parsing Assessment Order with AI...", 0.50)

    data = _ask_gemini(AO_PROMPT + text)
    logger.info(f"Assessment Order parsed: {len(data.get('additions', []))} additions found")
    return data


# ── CIT(A) Order Extraction (Optional) ──────────────────────

CITA_PROMPT = """You are an Indian Income Tax expert. Analyze this CIT(A) order passed under section 250 of the Income Tax Act.

The CIT(A) order addresses an appeal filed by the Assessee against the Assessment Order. The order discusses each ground of appeal raised by the Assessee and gives a decision on each.

IMPORTANT CONCEPTS:
- "Allowed" or "Allowed in favour of assessee" = The addition made by the AO is DELETED. The assessee gets full relief.
- "Dismissed" = The addition made by the AO is UPHELD. No relief to assessee.
- "Partly allowed" = The addition is partially reduced. The assessee gets partial relief.
- "Allowed for statistical purpose" or "Set aside" or "Remanded back to AO" = The issue is sent back to the Assessing Officer for fresh examination. The addition STAYS AS-IS until the AO completes the fresh proceedings. Relief amount is 0.

Return a JSON object with:
{
  "entity_name": "string",
  "assessment_year": "string (e.g. 2016-17)",
  "order_date": "string (DD/MM/YYYY)",
  "appeal_number": "string",
  "grounds": [
    {
      "ground_no": "string (e.g. 1, 2, 3, or 1.1, 1.2 etc.)",
      "description": "string - concise description of the ground/issue",
      "addition_description": "string - the corresponding addition from the assessment order that this ground relates to",
      "addition_amount": number (the original addition amount by AO),
      "status": "allowed" | "dismissed" | "partly_allowed" | "allowed_for_statistical_purpose",
      "relief_amount": number (amount of relief granted; 0 if dismissed or set aside; full amount if allowed; partial if partly_allowed),
      "section": "relevant IT section if mentioned (e.g. 43B, 40(a)(ia), 32, etc.)",
      "remarks": "Brief 1-2 line summary of CIT(A)'s reasoning/decision"
    }
  ],
  "total_relief": number (sum of all relief_amount),
  "total_additions_by_ao": number (sum of all addition_amount),
  "assessed_income_after_cita": number (if determinable from the order)
}

Instructions:
- Read the ENTIRE order thoroughly. Each ground must be analyzed individually.
- General grounds (like "The order of the AO is erroneous" or "The CIT(A) erred in...") that don't relate to a specific monetary addition should be EXCLUDED.
- For "allowed for statistical purpose" or "set aside" grounds, relief_amount MUST be 0 (the addition stays pending further proceedings).
- Parse Indian number format: 42,24,669 = 4224669
- If the order mentions that a ground is "not pressed" or "withdrawn", treat status as "dismissed" with relief_amount 0.
- addition_amount should be a plain number without commas

PDF Text:
"""


def extract_cita_order(pdf_path: str, progress_cb=None) -> dict:
    """Extract appeal grounds and decisions from CIT(A) order u/s 250."""
    if progress_cb:
        progress_cb("extracting", "Reading CIT(A) Order...", 0.55)

    text = _extract_pdf_text(pdf_path)
    logger.info(f"CIT(A) Order: extracted {len(text)} chars")

    if progress_cb:
        progress_cb("extracting", "Analyzing CIT(A) Order with AI...", 0.60)

    data = _ask_gemini(CITA_PROMPT + text)
    grounds = data.get("grounds", [])
    logger.info(
        f"CIT(A) Order parsed: {len(grounds)} grounds, "
        f"total relief={data.get('total_relief', 0)}"
    )
    return data
