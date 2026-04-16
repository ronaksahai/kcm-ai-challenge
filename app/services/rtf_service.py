"""
KCM AI Suite — RTF Service
Generates RTF (Rich Text Format) documents from translated markdown text.
RTF is generated manually to avoid heavy dependencies and ensure compatibility
with Microsoft Word and other editors.
"""

import re
import logging
from datetime import datetime

from app.config import APP_NAME

logger = logging.getLogger(__name__)


def generate_rtf(translated_markdown: str, output_path: str, original_filename: str = "document") -> str:
    """
    Generate an RTF document from translated markdown text.
    Preserves heading hierarchy, tables, bullet points, and text structure.

    Args:
        translated_markdown: The translated text in markdown format.
        output_path: Where to save the generated RTF.
        original_filename: Name of the original document for the header.

    Returns:
        Path to the generated RTF file.
    """
    rtf_content = _build_rtf(translated_markdown, original_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rtf_content)

    logger.info(f"RTF generated: {output_path}")
    return output_path


def _build_rtf(markdown_text: str, original_filename: str) -> str:
    """Build the complete RTF document string."""

    # ── RTF Header ───────────────────────────────────────────
    rtf = []
    rtf.append(r"{\rtf1\ansi\ansicpg1252\deff0")

    # Font table
    rtf.append(r"{\fonttbl")
    rtf.append(r"{\f0\fswiss\fcharset0 Calibri;}")        # Body font
    rtf.append(r"{\f1\fswiss\fcharset0 Arial;}")           # Heading font
    rtf.append(r"{\f2\fmodern\fcharset0 Consolas;}")       # Monospace
    rtf.append(r"}")

    # Color table
    rtf.append(r"{\colortbl;")
    rtf.append(r"\red26\green32\blue44;")       # 1 - Dark gray (body)
    rtf.append(r"\red45\green55\blue72;")       # 2 - Medium gray (headings 2/3)
    rtf.append(r"\red113\green128\blue150;")    # 3 - Light gray (subtitle)
    rtf.append(r"\red74\green85\blue104;")      # 4 - Muted (H3)
    rtf.append(r"\red200\green200\blue200;")    # 5 - Border gray
    rtf.append(r"\red247\green250\blue252;")    # 6 - Light row bg
    rtf.append(r"}")

    # Document settings
    rtf.append(r"\paperw11906\paperh16838")     # A4
    rtf.append(r"\margl1134\margr1134\margt1418\margb1134")  # Margins ~2cm
    rtf.append(r"\widowctrl\ftnbj\aenddoc")

    # ── Document Title Header ────────────────────────────────
    rtf.append(r"\pard\qc\sb200\sa100")
    rtf.append(r"{\f1\b\fs36\cf1 Translated Document}")
    rtf.append(r"\par")

    # Subtitle
    rtf.append(r"\pard\qc\sb0\sa100")
    now = datetime.now().strftime("%d %B %Y, %I:%M %p")
    rtf.append(r"{\f0\fs16\cf3 Original: " + _escape_rtf(original_filename)
               + r" | Translated on: " + now
               + r" | By: " + APP_NAME + r"}")
    rtf.append(r"\par")

    # Horizontal line
    rtf.append(r"\pard\brdrb\brdrs\brdrw10\brsp20\brdrcf5 \par")
    rtf.append(r"\pard\sb200\sa0\par")

    # ── Parse and render markdown content ────────────────────
    # Pre-process: strip any embedded HTML tags to clean text
    markdown_text = _strip_html_to_text(markdown_text)
    lines = markdown_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Empty line → paragraph break
        if not stripped:
            rtf.append(r"\par")
            i += 1
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___", "- - -", "* * *"):
            rtf.append(r"\pard\brdrb\brdrs\brdrw5\brsp20\brdrcf5 \par")
            rtf.append(r"\pard\sb100\sa100\par")
            i += 1
            continue

        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            rtf.append(_rtf_heading(text, level))
            i += 1
            continue

        # Table detection
        if "|" in stripped and stripped.startswith("|"):
            table_rows, new_i = _collect_table_rows(lines, i)
            if table_rows:
                rtf.append(_rtf_table(table_rows))
                i = new_i
                continue

        # Bullet points
        bullet_match = re.match(r"^\s*[-*+]\s+(.*)", stripped)
        if bullet_match:
            text = bullet_match.group(1)
            rtf.append(_rtf_bullet(text))
            i += 1
            continue

        # Numbered list
        num_match = re.match(r"^\s*(\d+)\.\s+(.*)", stripped)
        if num_match:
            num = num_match.group(1)
            text = num_match.group(2)
            rtf.append(_rtf_numbered(num, text))
            i += 1
            continue

        # Regular paragraph
        rtf.append(_rtf_paragraph(stripped))
        i += 1

    # ── Close document ───────────────────────────────────────
    rtf.append(r"}")

    return "\n".join(rtf)


# ── RTF Element Builders ─────────────────────────────────────

def _rtf_heading(text: str, level: int) -> str:
    """Generate RTF for a heading."""
    escaped = _escape_rtf(text)
    escaped = _apply_inline_rtf(escaped)

    if level == 1:
        return (r"\pard\sb300\sa150\keepn"
                r"{\f1\b\fs32\cf1 " + escaped + r"}\par")
    elif level == 2:
        return (r"\pard\sb250\sa120\keepn"
                r"{\f1\b\fs28\cf2 " + escaped + r"}\par")
    elif level == 3:
        return (r"\pard\sb200\sa100\keepn"
                r"{\f1\b\fs24\cf4 " + escaped + r"}\par")
    else:
        return (r"\pard\sb150\sa80\keepn"
                r"{\f1\b\fs22\cf4 " + escaped + r"}\par")


def _rtf_paragraph(text: str) -> str:
    """Generate RTF for a body paragraph."""
    escaped = _escape_rtf(text)
    escaped = _apply_inline_rtf(escaped)
    return (r"\pard\sb40\sa60\qj\sl280\slmult1"
            r"{\f0\fs22\cf1 " + escaped + r"}\par")


def _rtf_bullet(text: str) -> str:
    """Generate RTF for a bullet point."""
    escaped = _escape_rtf(text)
    escaped = _apply_inline_rtf(escaped)
    return (r"\pard\li720\fi-360\sb20\sa40"
            r"{\f0\fs22\cf1 \u8226?  " + escaped + r"}\par")


def _rtf_numbered(num: str, text: str) -> str:
    """Generate RTF for a numbered list item."""
    escaped = _escape_rtf(text)
    escaped = _apply_inline_rtf(escaped)
    return (r"\pard\li720\fi-360\sb20\sa40"
            r"{\f0\fs22\cf1 " + num + r".  " + escaped + r"}\par")


def _rtf_table(rows: list) -> str:
    """Generate RTF table from parsed rows."""
    if not rows:
        return ""

    num_cols = max(len(row) for row in rows)
    col_width = 9000 // num_cols  # Total ~9000 twips ≈ 15.9 cm

    rtf_parts = []
    rtf_parts.append(r"\pard\sb100\sa100")

    for row_idx, row in enumerate(rows):
        # Normalize columns
        while len(row) < num_cols:
            row.append("")

        # Row definition
        rtf_parts.append(r"\trowd\trqc")

        # Cell borders and widths
        for col_idx in range(num_cols):
            right_pos = col_width * (col_idx + 1)
            rtf_parts.append(
                r"\clbrdrt\brdrs\brdrw10\brdrcf5"
                r"\clbrdrb\brdrs\brdrw10\brdrcf5"
                r"\clbrdrl\brdrs\brdrw10\brdrcf5"
                r"\clbrdrr\brdrs\brdrw10\brdrcf5"
            )
            # Header row gets darker background
            if row_idx == 0:
                rtf_parts.append(r"\clshdng10000\clcbpat1")
            elif row_idx % 2 == 0:
                rtf_parts.append(r"\clshdng500\clcbpat6")

            rtf_parts.append(r"\cellx" + str(right_pos))

        # Cell contents
        rtf_parts.append(r"\pard\intbl")
        for col_idx, cell in enumerate(row):
            escaped = _escape_rtf(cell)
            if row_idx == 0:
                rtf_parts.append(r"{\f0\b\fs20\cf0 " + escaped + r"}\cell")
            else:
                rtf_parts.append(r"{\f0\fs20\cf1 " + escaped + r"}\cell")

        rtf_parts.append(r"\row")

    rtf_parts.append(r"\pard\par")
    return "\n".join(rtf_parts)


# ── Helpers ──────────────────────────────────────────────────

def _collect_table_rows(lines: list, start: int) -> tuple:
    """Collect table rows from markdown lines."""
    rows = []
    i = start

    while i < len(lines):
        stripped = lines[i].strip()
        if "|" not in stripped:
            break

        # Skip separator rows
        if re.match(r"^\|[\s\-:|\+]+\|?$", stripped):
            i += 1
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]
        rows.append(cells)
        i += 1

    return rows, i


def _escape_rtf(text: str) -> str:
    """Escape special RTF characters."""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")

    # Encode non-ASCII characters as Unicode
    result = []
    for ch in text:
        if ord(ch) > 127:
            result.append(f"\\u{ord(ch)}?")
        else:
            result.append(ch)

    return "".join(result)


def _apply_inline_rtf(text: str) -> str:
    """Convert markdown inline formatting to RTF formatting."""
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"{\\b \1}", text)
    text = re.sub(r"__(.+?)__", r"{\\b \1}", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"{\\i \1}", text)
    text = re.sub(r"_(.+?)_", r"{\\i \1}", text)
    return text


def _strip_html_to_text(text: str) -> str:
    """
    Convert any embedded HTML (from Sarvam OCR output) to clean plain text.
    """
    # Replace <br>, <br/>, <br /> with newline
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)

    # Replace <hr>, <hr/>, <hr /> with markdown horizontal rule
    text = re.sub(r'<hr\s*/?>', '\n---\n', text, flags=re.IGNORECASE)

    # Handle table rows: convert </tr> to newline
    text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)

    # Convert <td> and <th> content — add separator between cells
    text = re.sub(r'</t[dh]>\s*<t[dh][^>]*>', ' | ', text, flags=re.IGNORECASE)

    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Clean up excessive whitespace and blank lines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

    # Decode HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"')

    return text.strip()
