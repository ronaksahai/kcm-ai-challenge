"""
Case Law / Precedent Finder Service
Single-stage pipeline using Gemini 3.6 Flash + Google Search grounding.
Supports file text extraction (PDF, Word, Excel, images) and Taxmann URL generation.
"""

import json
import logging
import os
import csv

import PyPDF2
import openpyxl
from docx import Document as DocxDocument

from google import genai
from google.genai import types as genai_types
from app.config import GCP_PROJECT_ID, GCP_LOCATION

logger = logging.getLogger(__name__)

# ── Model Configuration ─────────────────────────────────────
GEMINI_MODEL = "gemini-3.6-flash"

_gemini_client = None

def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)
    return _gemini_client


# ── File Text Extraction ────────────────────────────────────

def extract_file_text(file_path: str) -> str:
    """Extract text content from uploaded files (PDF, Word, Excel, images)."""
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".pdf":
            return _extract_pdf_text(file_path)
        elif ext in (".docx", ".doc"):
            return _extract_docx_text(file_path)
        elif ext in (".xlsx", ".xls"):
            return _extract_excel_text(file_path)
        elif ext == ".csv":
            return _extract_csv_text(file_path)
        elif ext in (".jpg", ".jpeg", ".png"):
            # For images, return a placeholder — full OCR would need an additional service
            return f"[Image file attached: {os.path.basename(file_path)}]"
        else:
            return f"[Unsupported file type: {ext}]"
    except Exception as e:
        logger.warning(f"Failed to extract text from {file_path}: {e}")
        return f"[Failed to extract text from {os.path.basename(file_path)}]"

def _extract_pdf_text(path: str) -> str:
    reader = PyPDF2.PdfReader(path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)

def _extract_docx_text(path: str) -> str:
    doc = DocxDocument(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)

def _extract_excel_text(path: str) -> str:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    lines = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        lines.append(f"--- Sheet: {sheet_name} ---")
        for row in ws.iter_rows(values_only=True):
            row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
            if row_text.strip().replace("|", "").strip():
                lines.append(row_text)
    wb.close()
    return "\n".join(lines)

def _extract_csv_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        lines = [" | ".join(row) for row in reader]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  GEMINI SEARCH LOGIC
# ══════════════════════════════════════════════════════════════

GEMINI_ANALYSIS_PROMPT = """
You are a Senior Indian Tax Advocate. A CA professional is preparing a submission/appeal 
and needs case law precedents with facts IDENTICAL to their scenario.

THE USER'S SCENARIO:
{scenario}

{court_filter_instruction}

{context_section}

YOUR TASK:
1. Search the web (Indian Kanoon, Taxmann, ITAT, etc.) for real, verifiable Indian Income Tax case laws 
   where the FACTS are substantially identical to the user's scenario.
2. REJECT cases that merely discuss similar legal principles but have different facts.
3. CITATION NUMBERS ARE MANDATORY. Drop any case without a verifiable citation.

For each case you KEEP (max 5), provide:
- "case_name": Full case name
- "citations": Array of ALL citation numbers (e.g., "ITA No...", "[2023] 150 taxmann.com 123")
- "court": Court name
- "date": Judgment date (YYYY-MM-DD or YYYY)
- "section": Relevant IT Act sections
- "facts_summary": One detailed paragraph summarizing the specific facts of the case.
- "holding": One detailed paragraph summarizing what the court decided and why.
- "taxmann_url": If any citation contains "taxmann.com", construct a URL like: https://www.taxmann.com/research/direct-tax-laws/top-story/CITATION-NUMBER. Otherwise null.
- "source_url": Best available URL to read the full judgment (Indian Kanoon, ITAT website, etc.). If a taxmann_url exists, keep this as a fallback. Otherwise null.

Return ONLY valid JSON:
{{
  "results": [
    {{
      "case_name": "...",
      "citations": ["..."],
      "court": "...",
      "date": "...",
      "section": "...",
      "facts_summary": "...",
      "holding": "...",
      "taxmann_url": "...",
      "source_url": "..."
    }}
  ],
  "search_summary": "Brief 1-line summary of what was found",
  "no_results_reason": null
}}
"""

def search_precedents(scenario: str, court_filter: str = "all", context_text: str = "") -> dict:
    """
    Single-stage case law search: Gemini 3.6 Flash + Google Search
    """
    if not scenario or not scenario.strip():
        return {"results": [], "search_summary": "", "no_results_reason": "No scenario provided."}

    logger.info(f"Starting Gemini 3.6 case law search for: {scenario[:100]}...")

    court_instructions = {
        "all": "Search across ALL courts: ITAT, High Courts, and the Supreme Court.",
        "supreme_court": "Search ONLY in Supreme Court of India judgments.",
        "high_court": "Search ONLY in High Court judgments (any High Court in India).",
        "itat": "Search ONLY in ITAT (Income Tax Appellate Tribunal) orders.",
    }
    court_filter_instruction = court_instructions.get(court_filter, court_instructions["all"])

    context_section = ""
    if context_text:
        truncated = context_text[:15000] # Fit comfortably in context
        context_section = f"ADDITIONAL CONTEXT FROM ATTACHED DOCUMENTS:\n{truncated}"

    prompt = GEMINI_ANALYSIS_PROMPT.format(
        scenario=scenario.strip(),
        court_filter_instruction=court_filter_instruction,
        context_section=context_section,
    )

    client = _get_gemini_client()
    google_search_tool = genai_types.Tool(google_search=genai_types.GoogleSearch())

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                tools=[google_search_tool],
                temperature=0.1
            ),
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        data = json.loads(raw_text)

        # Validate
        if not isinstance(data, dict):
            data = {"results": [], "search_summary": "", "no_results_reason": "Unexpected AI response."}
        if "results" not in data:
            data["results"] = []

        # Filter out results without citations
        valid_results = []
        for r in data.get("results", []):
            citations = r.get("citations", [])
            if citations and any(c.strip() for c in citations if c):
                valid_results.append(r)
            else:
                logger.warning(f"Dropped case without citations: {r.get('case_name', 'Unknown')}")
        data["results"] = valid_results

        logger.info(f"Search complete: Found {len(valid_results)} matching cases.")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response: {e}")
        return {"results": [], "search_summary": "", "no_results_reason": "Failed to parse AI response. Please try again."}
    except Exception as e:
        logger.error(f"Gemini search failed: {e}")
        raise

