"""
KCM AI Suite — Translation Service
Uses Google Gemini to read PDFs directly and translate Gujarati to English.
Replaces the previous Sarvam-based chunked translation pipeline.
"""

import time
import logging

from google import genai
from google.genai import types, errors

from app.config import (
    GCP_PROJECT_ID,
    GCP_LOCATION,
    TRANSLATE_GEMINI_MODEL,
)

logger = logging.getLogger(__name__)

# ── Gemini Setup ─────────────────────────────────────────────

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT_ID,
            location=GCP_LOCATION,
        )
    return _client


# ── Translation Prompt ───────────────────────────────────────

TRANSLATE_PROMPT = r"""You are an expert translator specializing in Indian languages, particularly Gujarati.

TASK: Read the attached PDF document and translate ALL text content from Gujarati to English.

RULES:
- Translate the ENTIRE document — do not skip or summarize any section.
- Preserve the document structure using clean, semantic HTML formatting.
- Output ONLY valid HTML code. Do NOT output Markdown. Do NOT wrap the HTML in ```html blocks.
- Use basic HTML tags: <h2>, <h3>, <p>, <ul>, <li>, <strong>, etc.
- For tables, use standard HTML: <table>, <thead>, <tbody>, <tr>, <th>, <td>.
- You may use inline CSS for basic layout (e.g., style="text-align: center;", style="border: 1px solid black;", style="border-collapse: collapse;").
- Translate by meaning/sense, not word-for-word. The English output should read naturally.
- For financial/legal terms, use standard Indian English equivalents (e.g., "assessee", "assessment year", "computation of income").
- Keep proper nouns (names, PAN numbers, addresses, dates, amounts in ₹) as-is — do not translate them.
- If any text is already in English, keep it unchanged.
- If certain text is illegible or unclear, mark it as [illegible] rather than guessing.
- Do NOT add any commentary, notes, or explanations — output ONLY the translated HTML document.
"""


# ── Public API ───────────────────────────────────────────────

def translate_pdf(pdf_path: str, progress_callback=None) -> str:
    """
    Translate a Gujarati PDF to English using Gemini.
    Sends the PDF directly to Gemini for combined OCR + translation.

    Args:
        pdf_path: Absolute path to the PDF file.
        progress_callback: Optional callable(stage, detail, pct).

    Returns:
        Translated text in Markdown format.
    """
    logger.info(f"Starting Gemini translation for: {pdf_path}")

    if progress_callback:
        progress_callback("translating", "Reading document…", 0.1)

    # Read PDF as bytes
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
    logger.info(f"PDF size: {pdf_size_mb:.1f} MB")

    if progress_callback:
        progress_callback("translating", "Translating document with Gemini…", 0.2)

    # Send to Gemini
    translated_text = _call_gemini(pdf_bytes)

    if not translated_text.strip():
        raise ValueError(
            "No text could be extracted or translated from the document. "
            "Please ensure the PDF contains readable text or scanned images."
        )

    logger.info(f"Translation complete: {len(translated_text)} characters")

    if progress_callback:
        progress_callback("translating", "Translation complete.", 1.0)

    return translated_text


# ── Private Helpers ──────────────────────────────────────────

def _call_gemini(pdf_bytes: bytes) -> str:
    """
    Send PDF bytes to Gemini for OCR + translation.
    Includes model fallback chain and retry with exponential backoff.
    """
    client = _get_client()

    pdf_part = types.Part.from_bytes(
        data=pdf_bytes,
        mime_type="application/pdf",
    )
    contents = [TRANSLATE_PROMPT, pdf_part]

    # Model fallback chain
    models_to_try = [TRANSLATE_GEMINI_MODEL]
    for fallback in ["gemini-3.5-flash", "gemini-2.5-flash"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    max_retries = 5

    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Calling Gemini model={model_name} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )

                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=8192,
                    ),
                )

                result = response.text or ""
                logger.info(
                    f"Gemini response received: {len(result)} characters "
                    f"(model={model_name})"
                )
                return result

            except errors.APIError as e:
                if "503" in str(e) or getattr(e, "code", None) == 503:
                    if attempt < max_retries - 1:
                        sleep_time = 2 ** attempt
                        logger.warning(
                            f"Model {model_name} overloaded (503). "
                            f"Retrying in {sleep_time}s…"
                        )
                        time.sleep(sleep_time)
                        continue
                    else:
                        logger.error(
                            f"Model {model_name} overloaded (503). "
                            f"Exhausted retries."
                        )
                        break  # Try next model
                else:
                    logger.error(f"API error with model {model_name}: {e}")
                    break  # Try next model

            except Exception as e:
                logger.error(
                    f"Unexpected error with model {model_name}: {e}"
                )
                break  # Try next model

    raise RuntimeError(
        "Failed to translate document with Gemini API. "
        "Please try again later."
    )
