"""
Order Scrutiny — PDF Data Extraction
Uses PyPDF2 for text extraction and Google Gemini for structured parsing.
"""

import os
import tempfile
import json
import logging
import PyPDF2
import pymupdf  # PyMuPDF
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


def _ask_gemini(prompt: str, pdf_path: str = None) -> dict:
    """Send prompt to Gemini and parse JSON response, with retry and fallback.
    If pdf_path is provided, uploads the PDF natively (useful for scanned/image PDFs).
    """
    import time
    from google.genai import errors, types
    client = _get_client()
    
    models_to_try = [GEMINI_MODEL]
    if GEMINI_MODEL != "gemini-2.5-flash":
        models_to_try.append("gemini-2.5-flash")

    max_retries = 3
    uploaded_file = None
    
    try:
        if pdf_path:
            logger.info("Uploading PDF natively to Gemini...")
            uploaded_file = client.files.upload(file=pdf_path)
            contents = [prompt, uploaded_file]
        else:
            contents = prompt

        for model_name in models_to_try:
            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
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
    finally:
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as e:
                logger.error(f"Failed to clean up uploaded file: {e}")


# ── PDF Text Extraction ─────────────────────────────────────

def _extract_pdf_text(pdf_path: str, password: str = None) -> str:
    """Extract all text from a PDF, optionally decrypting."""
    try:
        doc = pymupdf.open(pdf_path)
        if doc.needs_pass:
            if not password:
                raise ValueError("PDF is encrypted. Please provide the password.")
            if not doc.authenticate(password):
                raise ValueError("Incorrect password for PDF.")
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text() or ""
            pages.append(f"--- Page {i+1} ---\n{text}")
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        logger.error(f"Failed to extract PDF text with PyMuPDF: {e}")
        return ""


def _extract_english_pages(pdf_path: str, password: str) -> str:
    """Extract only English pages from Intimation PDF (skip Hindi)."""
    try:
        doc = pymupdf.open(pdf_path)
        if doc.needs_pass:
            if not password:
                raise ValueError("PDF is encrypted. Please provide the password.")
            if not doc.authenticate(password):
                raise ValueError("Incorrect password for PDF.")
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text() or ""
            # English pages contain structured headers like "Sl.No.", "Particulars"
            # and the text "Intimation u/s 143(1)" in English
            if "Particulars" in text or "Reporting Heads" in text or "RETURN DETAILS" in text:
                pages.append(f"--- Page {i+1} ---\n{text}")
            elif "Mismatch between Tax Credits" in text or "Notes:" in text:
                pages.append(f"--- Page {i+1} ---\n{text}")
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        logger.error(f"Failed to extract English pages with PyMuPDF: {e}")
        return ""


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
- EXTREMELY IMPORTANT: Pay close attention to the column headers. Do NOT copy values from the "As Computed u/s 143(1)" column into the "As provided by Taxpayer" (ROI) column. They are often DIFFERENT (especially for TDS and Total Taxes Paid). Look carefully at the horizontal alignment. If the ROI column is blank for a row, use 0.

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

    if len(text.strip()) < 500:
        logger.warning(f"Computation Sheet text is too short ({len(text)} chars). Falling back to native PDF upload.")
        reader = PyPDF2.PdfReader(pdf_path)
        if reader.is_encrypted:
            reader.decrypt("")
        writer = PyPDF2.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        import tempfile, os
        temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(temp_fd, 'wb') as f:
            writer.write(f)
        data = _ask_gemini(COMP_SHEET_PROMPT, pdf_path=temp_path)
        os.remove(temp_path)
    else:
        data = _ask_gemini(COMP_SHEET_PROMPT + text)

    if not isinstance(data, dict):
        data = {}
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
    "income_normal_rates": number,
    "income_special_rates": number,
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
    "interest_244a": number
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
    "income_normal_rates": number,
    "income_special_rates": number,
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

CRITICAL COLUMN MAPPING RULES:
- The Intimation has exactly TWO data columns per line item.
- The FIRST/LEFT column is "As provided by Taxpayer" (ROI). Map it to the "roi" object.
- The SECOND/RIGHT column is "As Computed u/s 143(1)". Map it to the "computed" object.
- DO NOT swap them. The LEFT column value goes into "roi" and the RIGHT column value goes into "computed".

Important:
- Parse Indian numbers: 2,32,53,22,706 = 2325322706
- The intimation has detailed line items (sl.no 01 through ~50)
- "income_normal_rates" = the INCOME CHARGEABLE TO TAX AT NORMAL RATES (sl.no ~15). THIS WILL BE EXACTLY 0 if the document shows 0. Do not confuse it with "TAX AT NORMAL RATES".
- "income_special_rates" = the INCOME CHARGEABLE TO TAX AT SPECIAL RATES (sl.no ~14).
- "tax_normal_rates" = TAX AT NORMAL RATES (sl.no ~16 or ~24).
- "surcharge_total" = SURCHARGE (sl.no ~26).
- "cess" = EDUCATION CESS (sl.no ~27).
- "interest_234b" = INTEREST U/S 234B (sl.no ~35).
- "tds" = TDS / Tax Deducted at Source (sl.no ~42).
- "tcs" = TCS / Tax Collected at Source (sl.no ~43).
- "advance_tax" = ADVANCE TAX (sl.no ~44). DO NOT confuse this with REFUND AMOUNT. If the line item says "Refund" or "Amount Refundable/Payable", that is NOT advance tax.
- "self_assessment_tax" = SELF ASSESSMENT TAX (sl.no ~44).
- "total_taxes_paid" = TOTAL TAXES PAID (sl.no ~45). Extract the EXACT number written on the document. DO NOT try to recalculate it yourself.
- "interest_244a" = INTEREST U/S 244A ON REFUND (sl.no ~49).
- CAUTION: In the PDF text, the numeric values (like Surcharge, Cess, Interest) are often printed in a separate block FAR below their text labels. The order of numbers typically matches the order of labels. Use contextual clues to map them correctly!
- The PDF text may have Hindi characters mixed in. Focus on the English text and numbers to extract values.

PDF Text:
"""


def extract_intimation_order(pdf_path: str, password: str, progress_cb=None) -> dict:
    """Extract structured data from an Intimation u/s 143(1) PDF."""
    if progress_cb:
        progress_cb("extracting", "Reading Intimation Order...", 0.3)

    # Detect whether this is an Intimation Order vs an ITR filing.
    # Intimation orders contain "Intimation u/s" and "Document Identification No."
    full_text = _extract_pdf_text(pdf_path, password)
    first_text = full_text.upper()[:2000]
    
    is_intimation = (
        "INTIMATION U/S" in first_text
        or "DOCUMENT IDENTIFICATION NO" in first_text
    )
    
    if is_intimation:
        text = _extract_english_pages(pdf_path, password)
        if not text.strip():
            # Fallback: try all pages
            text = full_text
        logger.info(f"Intimation Order detected: extracted {len(text)} chars (English pages)")
    else:
        text = full_text
        logger.info(f"ITR detected: extracted {len(text)} chars")

    if progress_cb:
        progress_cb("extracting", "Parsing Intimation Order with AI...", 0.4)

    if len(text.strip()) < 500:
        logger.warning(f"Intimation Order text is too short ({len(text)} chars). Falling back to native PDF upload.")
        # Create an unencrypted copy if necessary
        reader = PyPDF2.PdfReader(pdf_path)
        if reader.is_encrypted:
            reader.decrypt(password)
            writer = PyPDF2.PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            import tempfile, os
            temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            with os.fdopen(temp_fd, 'wb') as f:
                writer.write(f)
            data = _ask_gemini(INTIMATION_PROMPT, pdf_path=temp_path)
            os.remove(temp_path)
        else:
            data = _ask_gemini(INTIMATION_PROMPT, pdf_path=pdf_path)
    else:
        data = _ask_gemini(INTIMATION_PROMPT + text)
        
    if not isinstance(data, dict):
        data = {}
    logger.info(f"Intimation parsed: {data.get('entity_name')}, AY {data.get('assessment_year')}")

    # --- Robust Text Parsing Fallback for TDS ---
    # Due to complex right-aligned columnar layouts in Intimations, Gemini often misses TDS.
    # We parse the text explicitly by anchoring to the Gross Tax Liability label.
    def _fallback_extract_tds(full_pdf_text):
        lines = [line.strip() for line in full_pdf_text.split('\n') if line.strip()]
        for i, line in enumerate(lines):
            if "GROSS TAX LIABILITY" in line.upper():
                nums = []
                for j in range(i-1, max(0, i-20), -1):
                    val = lines[j].replace(',', '')
                    if val.isdigit() or (val.startswith('-') and val[1:].isdigit()):
                        nums.append(int(val))
                
                if len(nums) >= 5:
                    if nums[0] in (26, 27, 28, 29):
                        return nums[4], nums[3]
                    elif any(x in line.replace(" ", "") for x in ("28=", "26=", "29=")):
                        return nums[3], nums[2]
        return None, None

    tds_roi_override, tds_c1_override = _fallback_extract_tds(full_text)
    if tds_roi_override is not None:
        if data.get("roi") and isinstance(data["roi"], dict):
            logger.info(f"Regex override for ROI TDS: {data['roi'].get('tds')} -> {tds_roi_override}")
            data["roi"]["tds"] = tds_roi_override
    if tds_c1_override is not None:
        if data.get("computed") and isinstance(data["computed"], dict):
            logger.info(f"Regex override for 143(1) TDS: {data['computed'].get('tds')} -> {tds_c1_override}")
            data["computed"]["tds"] = tds_c1_override

    # Post-processing: auto-correct TDS if total_taxes_paid doesn't match components
    for section_key in ("roi", "computed"):
        section = data.get(section_key)
        if not section or not isinstance(section, dict):
            continue
        ttp = section.get("total_taxes_paid", 0) or 0
        tds = section.get("tds", 0) or 0
        tcs = section.get("tcs", 0) or 0
        adv = section.get("advance_tax", 0) or 0
        sat = section.get("self_assessment_tax", 0) or 0
        
        parts_sum = tds + tcs + adv + sat
        if ttp > 0 and parts_sum != ttp:
            # AI often misattributes the Refund Amount to Self Assessment Tax due to PDF layout.
            # If removing SAT leaves a clean gap that fits a missing TDS, fix the hallucination.
            gap_without_sat = ttp - (tcs + adv)
            if gap_without_sat > 0 and tds == 0 and sat > gap_without_sat:
                logger.info(f"Zeroing hallucinated SAT: {sat} for {section_key}")
                sat = 0
                section["self_assessment_tax"] = 0

            gap = ttp - (tcs + adv + sat)
            if gap > 0 and tds == 0:
                section["tds"] = gap
                logger.info(f"Auto-corrected {section_key} TDS: {gap} (total_taxes_paid={ttp}, advance_tax={adv})")

        # Sanity check: advance_tax cannot exceed total_taxes_paid - tds - tcs - sat
        if ttp > 0 and adv > 0:
            max_adv = ttp - tds - tcs - sat
            if adv > max_adv:
                logger.info(f"advance_tax {adv} exceeds max possible {max_adv} for {section_key} — zeroing")
                section["advance_tax"] = 0
                adv = 0

        # Mathematical fallback for Surcharge and Cess based on Gross Tax Liability
        gtl = section.get("gross_tax_liability", 0) or 0
        tax_base = max(
            section.get("tax_normal_rates", 0) or section.get("tax_on_total_income", 0) or 0,
            section.get("tax_115jb", 0) or 0
        )
        sur = section.get("surcharge_total", 0) or 0
        ces = section.get("cess", 0) or 0
        
        # Detect surcharge/cess swap: Gemini frequently swaps these because
        # the PDF layout has numbers far from their labels.
        # Surcharge is computed on tax_base, so surcharge_rate = sur / tax_base.
        # Cess is computed on (tax_base + surcharge), so cess_rate = ces / (tax_base + sur).
        # In Indian IT: surcharge is typically 2-15% of tax, cess is 2-4% of (tax+surcharge).
        # If cess > surcharge AND swapping them produces valid rates, they're swapped.
        if sur > 0 and ces > 0 and tax_base > 0 and ces > sur:
            # Check if swapping produces valid rates
            swapped_sur = ces  # would-be surcharge
            swapped_ces = sur  # would-be cess
            swapped_sur_rate = swapped_sur / tax_base
            swapped_ces_rate = swapped_ces / (tax_base + swapped_sur)
            # Valid surcharge: 2-15%, valid cess: 2-4%
            if 0.01 <= swapped_sur_rate <= 0.20 and 0.015 <= swapped_ces_rate <= 0.05:
                logger.info(f"Auto-correcting swapped surcharge/cess for {section_key}: "
                           f"surcharge {sur}->{swapped_sur}, cess {ces}->{swapped_ces} "
                           f"(sur_rate={swapped_sur_rate:.2%}, cess_rate={swapped_ces_rate:.2%})")
                section["surcharge_total"] = swapped_sur
                section["cess"] = swapped_ces
                sur = swapped_sur
                ces = swapped_ces

        if gtl > 0 and tax_base > 0:
            calc_gtl = tax_base + sur + ces
            if calc_gtl != gtl:
                diff = gtl - calc_gtl
                if diff > 0:
                    if sur == 0 and ces > 0:
                        section["surcharge_total"] = diff
                        logger.info(f"Auto-corrected {section_key} Surcharge: {diff} (from Gross Tax Liability)")
                    elif ces == 0 and sur > 0:
                        section["cess"] = diff
                        logger.info(f"Auto-corrected {section_key} Cess: {diff} (from Gross Tax Liability)")
                    elif sur == 0 and ces == 0:
                        pass

    # Sanity check: PGBP swap (Gemini sometimes swaps ROI and Computed for PGBP)
    roi_dict = data.get("roi") or {}
    c1_dict = data.get("computed") or {}
    roi_pgbp = roi_dict.get("income_business_profession", 0)
    c1_pgbp = c1_dict.get("income_business_profession", 0)
    if roi_pgbp and c1_pgbp and roi_pgbp != c1_pgbp:
        import re
        clean_text = re.sub(r',', '', full_text)
        idx_roi = clean_text.find(str(roi_pgbp))
        idx_c1 = clean_text.find(str(c1_pgbp))
        if idx_roi != -1 and idx_c1 != -1 and idx_c1 < idx_roi:
            # PyMuPDF extracts left-to-right, so ROI must appear before C1.
            # If C1 appears before ROI in text, Gemini swapped them.
            logger.info(f"Auto-correcting swapped PGBP: ROI={c1_pgbp}, C1={roi_pgbp}")
            roi_dict["income_business_profession"] = c1_pgbp
            c1_dict["income_business_profession"] = roi_pgbp

    # Sanity check: deduction field hallucinations
    # Gemini sometimes puts tax_normal_rates into deduction fields by mistake.
    # Deductions can never equal the tax amount, so zero any that match.
    ded_keys = ["deduction_part_b", "deduction_part_c", "deduction_10aa"]
    for section_key in ("roi", "computed"):
        section = data.get(section_key)
        if not section or not isinstance(section, dict):
            continue
        tax_nr = section.get("tax_normal_rates", 0) or 0
        tax_oti = section.get("tax_on_total_income", 0) or 0
        if not tax_nr and not tax_oti:
            continue
        for dk in ded_keys:
            dv = section.get(dk, 0) or 0
            if dv > 0 and (dv == tax_nr or dv == tax_oti):
                logger.info(f"Zeroing hallucinated {dk}={dv} for {section_key} "
                           f"(matches tax_normal_rates={tax_nr})")
                section[dk] = 0

    return data


# ── Assessment Order Extraction (Required) ───────────────────

AO_PROMPT = """You are an Indian Income Tax expert. Extract structured data from this Assessment Order PDF.

The Assessment Order typically contains a "Final Table of Taxable Computation" or similar computation sheet at the end.
This table lists the income as per return, adjustments, and the total assessed income.

CRITICAL RULE FOR HEAD OF INCOME TRANSFERS:
If the Assessing Officer moves an item from one head of income to another (e.g., "interest income treated as Income from Other Sources" instead of Business Income), you MUST extract TWO separate adjustments:
1. A REDUCTION (negative amount) from the original head of income (e.g., Business or Profession).
2. An ADDITION (positive amount) to the new head of income (e.g., Other Sources).
Failure to extract both sides will cause the final totals to mismatch!

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
- In "additions", include EVERY item that adjusts the income in the computation table of the order. This includes additions, disallowances, variations, AND exemptions/reductions/reliefs.
- For additions, variations, and disallowances (items that increase income), "amount" must be POSITIVE (e.g., 1546181000).
- For exemptions, reductions, and reliefs (items that decrease income, often marked "Less:"), "amount" MUST be NEGATIVE (e.g., -120796095).
- If the AO denies or rejects a loss setoff (which effectively increases taxable income), treat it as a POSITIVE addition.
- "description" should capture the exact wording (e.g. "Dividend income, exempt u/s 10(34/35)" or "Variation in respect of issue of Disallowance u/s 43B")
- "head_of_income" should be the income head under which this addition falls. Most additions fall under "Business or Profession".
- "amount" should be a plain number without commas (use the negative sign for deductions).
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
        progress_cb("extracting", "Parsing Assessment Order with AI...", 0.5)

    if len(text.strip()) < 500:
        logger.warning(f"Assessment Order text is too short ({len(text)} chars). Falling back to native PDF upload.")
        reader = PyPDF2.PdfReader(pdf_path)
        if reader.is_encrypted:
            # We don't have password here, so we try decrypting with empty string or just use as is
            reader.decrypt("")
        writer = PyPDF2.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(temp_fd, 'wb') as f:
            writer.write(f)
        data = _ask_gemini(AO_PROMPT, pdf_path=temp_path)
        os.remove(temp_path)
    else:
        data = _ask_gemini(AO_PROMPT + text)
        
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict) and "additions" in data[0]:
            data = data[0]
        else:
            data = {"additions": data}
    elif not isinstance(data, dict):
        data = {}
    logger.info(f"Assessment Order parsed: {len(data.get('additions', []))} additions found")
    return data


# ── CIT(A) Order Extraction (Optional) ──────────────────────

CITA_PROMPT = """You are an Indian Income Tax expert. Analyze the provided text which may contain a CIT(A) order passed under section 250 of the Income Tax Act, and/or a CIT(A) Computation Sheet (Order Giving Effect / OGE).

The CIT(A) order discusses each ground of appeal raised by the Assessee and gives a decision on each. The Computation Sheet (OGE) calculates the revised income and lists the exact numerical relief granted for each ground.

If both are provided, use the combined context to extract the grounds of appeal, their status, and the precise numerical relief amounts granted. If only the Computation Sheet (OGE) is provided, you can deduce the allowed grounds based on the "Relief allowed" section.

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


def extract_cita_order(pdf_path: str = None, cita_comp_path: str = None, progress_cb=None) -> dict:
    """Extract appeal grounds and decisions from CIT(A) order and/or Computation Sheet."""
    if progress_cb:
        progress_cb("extracting", "Reading CIT(A) documents...", 0.55)

    text = ""
    pdf_paths = []
    
    if pdf_path and os.path.exists(pdf_path):
        order_text = _extract_pdf_text(pdf_path)
        text += f"\n--- CIT(A) ORDER ---\n{order_text}\n"
        pdf_paths.append(pdf_path)
        
    if cita_comp_path and os.path.exists(cita_comp_path):
        comp_text = _extract_pdf_text(cita_comp_path)
        text += f"\n--- CIT(A) COMPUTATION SHEET (OGE) ---\n{comp_text}\n"
        pdf_paths.append(cita_comp_path)

    logger.info(f"CIT(A) Documents: extracted {len(text)} chars combined")

    if progress_cb:
        progress_cb("extracting", "Analyzing CIT(A) Documents with AI...", 0.60)

    # Fallback to native PDF upload if text is very short (likely scanned image PDFs without OCR)
    if len(text.strip()) < 500 and pdf_paths:
        logger.warning(f"CIT(A) text is too short ({len(text)} chars). Falling back to native PDF upload.")
        
        # Merge all PDFs into one for the Gemini native upload
        writer = PyPDF2.PdfWriter()
        for p in pdf_paths:
            reader = PyPDF2.PdfReader(p)
            if reader.is_encrypted:
                reader.decrypt("")
            for page in reader.pages:
                writer.add_page(page)
                
        temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(temp_fd, 'wb') as f:
            writer.write(f)
            
        data = _ask_gemini(CITA_PROMPT, pdf_path=temp_path)
        os.remove(temp_path)
    else:
        data = _ask_gemini(CITA_PROMPT + text)
    
    # Robustness: occasionally the AI returns a list.
    if isinstance(data, list):
        # If it's a list containing a single dict that already has 'grounds', unwrap it.
        if len(data) == 1 and isinstance(data[0], dict) and "grounds" in data[0]:
            data = data[0]
        else:
            data = {"grounds": data}
    elif not isinstance(data, dict):
        data = {}

    grounds = data.get("grounds", [])
    logger.info(
        f"CIT(A) Order parsed: {len(grounds)} grounds, "
        f"total relief={data.get('total_relief', 0)}"
    )
    return data
