"""
Notice Reply Drafting — Main Service
Orchestrates: PDF extraction → Gemini AI analysis → Word + Excel + Email generation.

All formatting rules and reply structure are embedded in the Gemini prompt
and document-generation code. No external sample data is required.
"""

import json
import logging
import os

import PyPDF2
from google import genai
from google.genai import types

from app.config import GCP_PROJECT_ID, GCP_LOCATION, GEMINI_MODEL
from app.services.notice_docx import generate_reply_docx
from app.services.notice_excel import generate_details_excel

logger = logging.getLogger(__name__)

# ── Gemini Setup ─────────────────────────────────────────────

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)
    return _client


# ── PDF Text Extraction ─────────────────────────────────────

def _extract_pdf_text(pdf_path: str) -> str:
    """Extract all text from a notice PDF."""
    reader = PyPDF2.PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"--- Page {i+1} ---\n{text}")
    return "\n\n".join(pages)


# ── Gemini Prompt ────────────────────────────────────────────

NOTICE_ANALYSIS_PROMPT = r"""You are an expert Indian Income Tax practitioner. Analyze this Income Tax Department notice and extract structured data for drafting a reply skeleton.

IMPORTANT RULES:
- NEVER include the name of any Income Tax Officer, even if mentioned in the notice.
- The addressee should be the designation/unit (e.g., "Income Tax Officer", "The Assessment Unit") along with the ward and city — extracted from the header, footer, or digital signature area of the notice.
- Look at the address block at the top of the notice (the "To," section) for the assessee's name and address.
- The notice address block header (where "OFFICE OF THE ..." or "GOVERNMENT OF INDIA" appears) and footer/digital-signature area contain the IT department's office information — use those for the addressee.
- Extract EACH numbered point/requirement from the notice as a separate item.
- If multiple sub-points are grouped under a single point (e.g., 4(i), 4(ii), 4(iii)), you may group them under one entry or split them — use your judgment based on whether they should be addressed together or separately in the reply.
- For each point, determine:
  - Whether the department is asking for specific DOCUMENTS (e.g., "furnish copy of...", "submit proof...", "provide ledger...")
  - Whether it is asking for an EXPLANATION (e.g., "explain why...", "state the reason...")
  - Whether a TABLE format would be appropriate for the response
  - What documents or evidence the Assessee could potentially provide to address the requirement
- If the notice is issued under a specific section of the Income Tax Act (like 142(1), 143(2), etc.), note it. If not under a specific section (e.g., "Issue letter - Give effect proceedings"), set notice_section to null.
- Determine if the Assessee is a company (name contains Pvt Ltd, Limited, LLP, Co., Corporation, etc.) or an individual.

Return a JSON object with this EXACT structure:
{
  "addressee": {
    "designation": "Income Tax Officer / The Assessment Unit / etc.",
    "ward_unit": "Ward 9(1)(1) / empty string if not available",
    "city": "Mumbai / empty string if not available"
  },
  "assessee_name": "Full name as appears in notice",
  "pan": "PAN number",
  "assessment_year": "2018-19",
  "notice_date": "21/04/2026",
  "din": "Full DIN string",
  "notice_section": "142(1) or null if not under specific section",
  "notice_type": "Brief description e.g. 'Issue letter - Give effect proceedings' or 'Notice u/s 142(1)' or 'Notice u/s 143(2)'",
  "is_company": true,
  "brief_context": "One-line summary of what this notice is broadly about, e.g. 'TDS credit verification for AY 2018-19' or 'Scrutiny assessment for AY 2024-25'",
  "points": [
    {
      "point_numbers": "1",
      "what_is_asked": "Exact or close paraphrase of what the department has asked — this will be used in the reply as 'your kind office has directed the Assessee to ...'",
      "requirement_type": "document | explanation | proof | information | compliance",
      "needs_table": false,
      "table_columns": ["Column1", "Column2"],
      "documents_asked": ["List of specific documents asked for, if any"],
      "suggested_response_approach": "How the reply skeleton should frame the response — e.g., 'submit documents as annexure', 'provide explanation', 'enclose details in table format'",
      "details_for_client": "What the client/assessee needs to provide — written clearly for a non-technical person. This goes into the 'Details Required' Excel.",
      "ai_remarks": "Any helpful remarks about what kind of evidence/documents the Assessee could provide"
    }
  ]
}

NOTICE TEXT:
"""


def _analyze_notice(text: str) -> dict:
    """Send notice text to Gemini for structured analysis."""
    import time
    from google.genai import errors
    client = _get_client()

    models_to_try = [GEMINI_MODEL]
    for fallback in ["gemini-3.5-flash", "gemini-2.5-pro", "gemini-2.5-flash"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    max_retries = 5

    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=NOTICE_ANALYSIS_PROMPT + text,
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


# ── Client Email Generator ───────────────────────────────────

def _generate_client_email(notice_data: dict) -> str:
    """Generate a short email message to send to the client along with the Details Required Excel."""
    name = notice_data.get("assessee_name", "the Assessee")
    ay = notice_data.get("assessment_year", "____")
    notice_type = notice_data.get("notice_type", "notice")
    notice_date = notice_data.get("notice_date", "____")
    section = notice_data.get("notice_section")

    section_ref = ""
    if section and section not in notice_type:
        section_ref = f" u/s {section} of the Income Tax Act, 1961"
    elif section and section in notice_type:
        # If it's already there, just add the act reference
        section_ref = " of the Income Tax Act, 1961"

    email = (
        f"Dear Sir/Ma'am,\n\n"
        f"This is to inform you that a {notice_type}{section_ref} dated {notice_date} "
        f"has been issued to you for the Assessment Year {ay}.\n\n"
        f"In order to draft a suitable reply, we request you to kindly provide "
        f"the details/documents as mentioned in the attached 'Details Required' sheet "
        f"at the earliest.\n\n"
        f"Please feel free to reach out in case of any queries.\n\n"
        f"Regards,\n"
        f"KCM & Associates"
    )
    return email


# ── Main Pipeline ────────────────────────────────────────────

def run_notice_reply_pipeline(
    pdf_path: str,
    output_docx_path: str,
    output_xlsx_path: str,
    progress_callback=None,
) -> dict:
    """
    Full Notice Reply pipeline:
    1. Extract text from notice PDF
    2. Analyze with Gemini AI
    3. Generate reply skeleton (Word)
    4. Generate details-required sheet (Excel)
    5. Generate client email message

    Returns dict with output paths and email text.
    """
    def pcb(stage, detail, pct):
        if progress_callback:
            progress_callback(stage, detail, pct)

    # Step 1: Extract PDF text
    pcb("extracting", "Reading notice PDF...", 0.05)
    text = _extract_pdf_text(pdf_path)
    logger.info(f"Notice PDF: extracted {len(text)} chars")

    if not text.strip():
        raise ValueError(
            "No text could be extracted from the notice PDF. "
            "Please ensure the PDF contains selectable text (not a scanned image)."
        )

    # Step 2: Analyze with Gemini
    pcb("analyzing", "Analyzing notice with AI...", 0.15)
    notice_data = _analyze_notice(text)
    logger.info(
        f"Notice analyzed: {notice_data.get('assessee_name')}, "
        f"AY {notice_data.get('assessment_year')}, "
        f"{len(notice_data.get('points', []))} points found"
    )

    # Step 3: Generate Word reply skeleton
    pcb("generating", "Generating reply skeleton (Word)...", 0.50)
    generate_reply_docx(notice_data, output_docx_path)
    logger.info(f"Reply skeleton saved: {output_docx_path}")

    # Step 4: Generate Excel details-required
    pcb("generating", "Generating Details Required (Excel)...", 0.75)
    generate_details_excel(notice_data, output_xlsx_path)
    logger.info(f"Details Required saved: {output_xlsx_path}")

    # Step 5: Generate client email
    pcb("generating", "Preparing client email message...", 0.90)
    email_text = _generate_client_email(notice_data)

    pcb("generating", "Notice Reply complete!", 1.0)

    return {
        "docx_path": output_docx_path,
        "xlsx_path": output_xlsx_path,
        "email_text": email_text,
        "notice_data": notice_data,
    }
