"""
KCM AI Suite — Translation Service
Integrates with Sarvam AI Translate API.
Handles text chunking and markdown-aware Gujarati-to-English translation.
"""

import re
import time
import logging
import requests

from app.config import (
    SARVAM_API_KEY,
    SARVAM_TRANSLATE_URL,
    TRANSLATE_MODEL,
    TRANSLATE_MODE,
    TRANSLATE_CHUNK_LIMIT,
    TARGET_LANGUAGE,
)

logger = logging.getLogger(__name__)

# Source language is always Gujarati for this module
SOURCE_LANGUAGE = "gu-IN"


# ── Public API ───────────────────────────────────────────────
def translate_markdown(
    markdown_text: str,
    progress_callback=None,
) -> str:
    """
    Translate Gujarati markdown text to English.
    Preserves markdown structure (headings, tables, bullets, etc.).

    Args:
        markdown_text: Extracted markdown from OCR.
        progress_callback: Optional callable(stage, detail, pct).

    Returns:
        Translated markdown text in English.
    """
    if not markdown_text.strip():
        return ""

    logger.info(f"Translating from Gujarati (gu-IN) to English (en-IN)")

    # Strip massive base64 embedded images from markdown (prevents API 500 errors)
    markdown_text = re.sub(r'!\[.*?\]\(data:image\/.*?;base64,[a-zA-Z0-9\+\/]+={0,2}\)', '', markdown_text)
    markdown_text = re.sub(r'<img[^>]+src="data:image\/.*?;base64,[a-zA-Z0-9\+\/]+={0,2}"[^>]*>', '', markdown_text, flags=re.IGNORECASE)

    # Parse markdown into translatable segments
    segments = _parse_markdown_segments(markdown_text)
    total_segments = len([s for s in segments if s["translatable"]])
    translated_count = 0

    if progress_callback:
        progress_callback("translating", f"Translating {total_segments} segments…", 0.0)

    # Translate each segment
    translated_segments = []
    for seg in segments:
        if not seg["translatable"]:
            # Non-translatable (empty lines, separators, etc.) — keep as-is
            translated_segments.append(seg["text"])
            continue

        prefix = seg.get("prefix", "")
        text = seg["content"]

        # Chunk the text if it's too long
        chunks = _chunk_text(text, TRANSLATE_CHUNK_LIMIT)
        translated_parts = []

        for chunk in chunks:
            translated_chunk = _call_translate_api(chunk)
            translated_parts.append(translated_chunk)
            time.sleep(0.1)  # Small delay to respect rate limits

        translated_text = " ".join(translated_parts)
        translated_segments.append(f"{prefix}{translated_text}")

        translated_count += 1
        if progress_callback:
            pct = translated_count / total_segments if total_segments > 0 else 1.0
            progress_callback(
                "translating",
                f"Translated {translated_count}/{total_segments} segments…",
                pct,
            )

    result = "\n".join(translated_segments)
    logger.info(f"Translation complete: {len(result)} characters")
    return result


# ── Private helpers ──────────────────────────────────────────
def _parse_markdown_segments(text: str) -> list:
    """
    Parse markdown text into segments, identifying structural prefixes
    so we can translate only the text content while preserving formatting.
    """
    lines = text.split("\n")
    segments = []

    for line in lines:
        stripped = line.strip()

        # Empty line
        if not stripped:
            segments.append({"text": "", "translatable": False})
            continue

        # Table separator row (e.g., |---|---|)
        if re.match(r"^\|[\s\-:|\+]+\|?$", stripped):
            segments.append({"text": line, "translatable": False})
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___", "- - -", "* * *"):
            segments.append({"text": line, "translatable": False})
            continue

        # Heading (# Heading text)
        heading_match = re.match(r"^(#{1,6}\s+)(.*)", line)
        if heading_match:
            segments.append({
                "text": line,
                "translatable": True,
                "prefix": heading_match.group(1),
                "content": heading_match.group(2),
            })
            continue

        # Table row ( | cell | cell | )
        if "|" in stripped and stripped.startswith("|"):
            cells = stripped.split("|")
            # Translate each cell individually
            translated_cells = []
            for cell in cells:
                cell_stripped = cell.strip()
                if cell_stripped:
                    translated_cells.append(cell_stripped)

            if translated_cells:
                segments.append({
                    "text": line,
                    "translatable": True,
                    "prefix": "| ",
                    "content": " | ".join(translated_cells),
                    "is_table_row": True,
                    "cell_contents": translated_cells,
                })
                continue

        # Bullet point
        bullet_match = re.match(r"^(\s*[-*+]\s+)(.*)", line)
        if bullet_match:
            segments.append({
                "text": line,
                "translatable": True,
                "prefix": bullet_match.group(1),
                "content": bullet_match.group(2),
            })
            continue

        # Numbered list
        numbered_match = re.match(r"^(\s*\d+\.\s+)(.*)", line)
        if numbered_match:
            segments.append({
                "text": line,
                "translatable": True,
                "prefix": numbered_match.group(1),
                "content": numbered_match.group(2),
            })
            continue

        # Regular paragraph line
        segments.append({
            "text": line,
            "translatable": True,
            "prefix": "",
            "content": stripped,
        })

    return segments


def _chunk_text(text: str, limit: int) -> list:
    """
    Split text into chunks of at most `limit` characters.
    Tries to split at sentence boundaries (। or . or newline).
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > limit:
        # Find the best split point (sentence boundary) within the limit
        split_pos = limit

        # Try splitting at Devanagari/Gujarati purna viram (।) first
        viram_pos = remaining.rfind("।", 0, limit)
        if viram_pos > limit * 0.3:
            split_pos = viram_pos + 1
        else:
            # Try period
            period_pos = remaining.rfind(".", 0, limit)
            if period_pos > limit * 0.3:
                split_pos = period_pos + 1
            else:
                # Try space
                space_pos = remaining.rfind(" ", 0, limit)
                if space_pos > limit * 0.3:
                    split_pos = space_pos + 1

        chunks.append(remaining[:split_pos].strip())
        remaining = remaining[split_pos:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def _call_translate_api(text: str) -> str:
    """Call the Sarvam Translate API for a single text chunk."""
    if not text.strip():
        return text

    payload = {
        "input": text,
        "source_language_code": SOURCE_LANGUAGE,
        "target_language_code": TARGET_LANGUAGE,
        "model": TRANSLATE_MODEL,
        "mode": TRANSLATE_MODE,
    }
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            SARVAM_TRANSLATE_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("translated_text", text)
    except requests.exceptions.HTTPError as e:
        logger.error(f"Translation API error: {e} — Response: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        raise
