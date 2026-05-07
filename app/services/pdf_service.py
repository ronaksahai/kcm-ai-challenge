"""
KCM AI Suite — PDF Service
Handles:
  1. Splitting large PDFs into ≤ 10-page batches.
  2. Generating formatted PDF output from translated markdown text.
"""

import os
import re
import logging
from datetime import datetime

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    PageBreak,
)

from app.config import TEMP_DIR, APP_NAME

logger = logging.getLogger(__name__)

# ── PDF Splitting ────────────────────────────────────────────

def get_page_count(pdf_path: str) -> int:
    """Return the number of pages in a PDF."""
    reader = PdfReader(pdf_path)
    return len(reader.pages)


def split_pdf(pdf_path: str, max_pages: int = 10) -> list:
    """
    Split a PDF into multiple files, each with at most max_pages pages.
    Returns a list of file paths to the generated batch files.
    """
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    if total_pages <= max_pages:
        return [pdf_path]

    batch_paths = []
    batch_num = 0

    for start in range(0, total_pages, max_pages):
        end = min(start + max_pages, total_pages)
        writer = PdfWriter()

        for page_idx in range(start, end):
            writer.add_page(reader.pages[page_idx])

        batch_filename = f"batch_{batch_num}_{os.path.basename(pdf_path)}"
        batch_path = os.path.join(TEMP_DIR, batch_filename)

        with open(batch_path, "wb") as f:
            writer.write(f)

        batch_paths.append(batch_path)
        batch_num += 1
        logger.info(f"  Created batch {batch_num}: pages {start + 1}–{end}")

    return batch_paths


# ── PDF Generation ───────────────────────────────────────────

def generate_pdf(translated_markdown: str, output_path: str, original_filename: str = "document") -> str:
    """
    Generate a professionally formatted PDF from translated markdown text.
    Preserves heading hierarchy, tables, bullet points, and text structure.

    Args:
        translated_markdown: The translated text in markdown format.
        output_path: Where to save the generated PDF.
        original_filename: Name of the original document for the header.

    Returns:
        Path to the generated PDF file.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=f"Translated: {original_filename}",
        author=APP_NAME,
    )

    styles = _create_styles()
    elements = []

    # ── Document Header ──────────────────────────────────────
    elements.append(Paragraph(f"Translated Document", styles["DocTitle"]))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        f"Original: {_escape_xml(original_filename)} &nbsp; | &nbsp; "
        f"Translated on: {datetime.now().strftime('%d %B %Y, %I:%M %p')} &nbsp; | &nbsp; "
        f"By: {APP_NAME}",
        styles["DocSubtitle"],
    ))
    elements.append(Spacer(1, 3 * mm))
    elements.append(HRFlowable(
        width="100%", thickness=0.5, color=colors.HexColor("#4a5568"),
    ))
    elements.append(Spacer(1, 6 * mm))

    # ── Parse and render markdown ────────────────────────────
    md_elements = _parse_markdown_to_elements(translated_markdown, styles)
    elements.extend(md_elements)

    # ── Build PDF ────────────────────────────────────────────
    doc.build(elements, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    logger.info(f"PDF generated: {output_path}")
    return output_path


def _create_styles():
    """Create the style sheet for the PDF."""
    base = getSampleStyleSheet()

    styles = {}

    styles["DocTitle"] = ParagraphStyle(
        "DocTitle",
        parent=base["Title"],
        fontSize=18,
        textColor=colors.HexColor("#1a202c"),
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    styles["DocSubtitle"] = ParagraphStyle(
        "DocSubtitle",
        parent=base["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#718096"),
        alignment=TA_CENTER,
        fontName="Helvetica",
    )

    styles["Heading1"] = ParagraphStyle(
        "Heading1",
        parent=base["Heading1"],
        fontSize=16,
        textColor=colors.HexColor("#1a202c"),
        spaceBefore=12,
        spaceAfter=6,
        fontName="Helvetica-Bold",
        borderWidth=0,
        borderPadding=0,
        borderColor=None,
    )

    styles["Heading2"] = ParagraphStyle(
        "Heading2",
        parent=base["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#2d3748"),
        spaceBefore=10,
        spaceAfter=5,
        fontName="Helvetica-Bold",
    )

    styles["Heading3"] = ParagraphStyle(
        "Heading3",
        parent=base["Heading3"],
        fontSize=12,
        textColor=colors.HexColor("#4a5568"),
        spaceBefore=8,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )

    styles["BodyText"] = ParagraphStyle(
        "BodyText",
        parent=base["BodyText"],
        fontSize=10,
        textColor=colors.HexColor("#2d3748"),
        spaceBefore=2,
        spaceAfter=4,
        leading=14,
        alignment=TA_JUSTIFY,
        fontName="Helvetica",
    )

    styles["BulletText"] = ParagraphStyle(
        "BulletText",
        parent=base["BodyText"],
        fontSize=10,
        textColor=colors.HexColor("#2d3748"),
        spaceBefore=1,
        spaceAfter=2,
        leading=14,
        leftIndent=15,
        bulletIndent=5,
        fontName="Helvetica",
    )

    styles["TableHeader"] = ParagraphStyle(
        "TableHeader",
        parent=base["Normal"],
        fontSize=9,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )

    styles["TableCell"] = ParagraphStyle(
        "TableCell",
        parent=base["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#2d3748"),
        fontName="Helvetica",
        alignment=TA_LEFT,
    )

    return styles


def _parse_markdown_to_elements(text: str, styles: dict) -> list:
    """Convert markdown text into ReportLab flowable elements."""
    # Pre-process: strip any embedded HTML tags to clean text
    text = _strip_html_to_text(text)

    elements = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines (add small spacer)
        if not stripped:
            elements.append(Spacer(1, 2 * mm))
            i += 1
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___", "- - -", "* * *"):
            elements.append(Spacer(1, 3 * mm))
            elements.append(HRFlowable(
                width="100%", thickness=0.3, color=colors.HexColor("#cbd5e0"),
            ))
            elements.append(Spacer(1, 3 * mm))
            i += 1
            continue

        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text_content = _escape_xml(_apply_inline_formatting(heading_match.group(2)))
            style_key = f"Heading{min(level, 3)}"
            elements.append(Paragraph(text_content, styles[style_key]))
            i += 1
            continue

        # Table detection — look for a row followed by a separator
        if "|" in stripped and stripped.startswith("|"):
            table_rows, new_i = _collect_table(lines, i)
            if table_rows:
                table_element = _build_table(table_rows, styles)
                if table_element:
                    elements.append(Spacer(1, 3 * mm))
                    elements.append(table_element)
                    elements.append(Spacer(1, 3 * mm))
                i = new_i
                continue

        # Bullet points
        bullet_match = re.match(r"^\s*[-*+]\s+(.*)", stripped)
        if bullet_match:
            bullet_text = _escape_xml(_apply_inline_formatting(bullet_match.group(1)))
            elements.append(Paragraph(
                f"•  {bullet_text}",
                styles["BulletText"],
            ))
            i += 1
            continue

        # Numbered list
        num_match = re.match(r"^\s*(\d+)\.\s+(.*)", stripped)
        if num_match:
            num = num_match.group(1)
            item_text = _escape_xml(_apply_inline_formatting(num_match.group(2)))
            elements.append(Paragraph(
                f"{num}.  {item_text}",
                styles["BulletText"],
            ))
            i += 1
            continue

        # Regular paragraph
        para_text = _escape_xml(_apply_inline_formatting(stripped))
        elements.append(Paragraph(para_text, styles["BodyText"]))
        i += 1

    return elements


def _collect_table(lines: list, start: int) -> tuple:
    """Collect consecutive table rows starting from 'start'. Returns (rows, next_index)."""
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

        cells = [c.strip() for c in stripped.split("|")]
        # Remove empty first/last from | delimiters
        cells = [c for c in cells if c or cells.index(c) not in (0, len(cells) - 1)]
        cells = [c for idx, c in enumerate(cells) if not (idx == 0 and c == "") or not (idx == len(cells) - 1 and c == "")]
        # Re-parse more cleanly
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        rows.append(cells)
        i += 1

    return rows, i


def _build_table(rows: list, styles: dict):
    """Build a ReportLab Table from parsed rows."""
    if not rows:
        return None

    # Determine column count from the first row
    num_cols = max(len(row) for row in rows)

    # Normalize rows to have equal columns
    normalized = []
    for row in rows:
        while len(row) < num_cols:
            row.append("")
        normalized.append(row)

    # First row is the header
    table_data = []

    for row_idx, row in enumerate(normalized):
        style_key = "TableHeader" if row_idx == 0 else "TableCell"
        table_data.append([
            Paragraph(_escape_xml(cell), styles[style_key]) for cell in row
        ])

    # Calculate column widths
    available_width = A4[0] - 40 * mm
    col_width = available_width / num_cols

    table = Table(table_data, colWidths=[col_width] * num_cols)

    # Style the table
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]

    table.setStyle(TableStyle(style_commands))
    return table


def _apply_inline_formatting(text: str) -> str:
    """Convert markdown inline formatting to ReportLab XML tags."""
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_", r"<i>\1</i>", text)
    return text


def _escape_xml(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraphs, preserving our tags."""
    # First, protect our formatting tags
    text = text.replace("<b>", "BOLD_OPEN").replace("</b>", "BOLD_CLOSE")
    text = text.replace("<i>", "ITALIC_OPEN").replace("</i>", "ITALIC_CLOSE")

    # Escape XML chars
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    # Restore formatting tags
    text = text.replace("BOLD_OPEN", "<b>").replace("BOLD_CLOSE", "</b>")
    text = text.replace("ITALIC_OPEN", "<i>").replace("ITALIC_CLOSE", "</i>")

    return text


def _strip_html_to_text(text: str) -> str:
    """
    Convert any embedded HTML (from Sarvam OCR output) to clean plain text.
    Handles broken HTML tables seamlessly.
    """
    import re as _re

    # Replace <br>, <br/>, <br /> with newline
    text = _re.sub(r'<br\s*/?>', '\n', text, flags=_re.IGNORECASE)
    # Replace <hr>, <hr/>, <hr /> with markdown horizontal rule
    text = _re.sub(r'<hr\s*/?>', '\n---\n', text, flags=_re.IGNORECASE)

    tr_blocks = _re.split(r'(?i)<tr[^>]*>', text)
    new_text_parts = [tr_blocks[0]]
    in_table = False
    
    for block in tr_blocks[1:]:
        match = _re.search(r'(?i)</tr>|</?(?:table|thead|tbody|tfoot)[^>]*>', block)
        if match:
            row_content = block[:match.start()]
            after_row = block[match.start():]
        else:
            row_content = block
            after_row = ""
            
        cell_blocks = _re.split(r'(?i)<t[dh][^>]*>', row_content)
        clean_cells = []
        
        pre_cell_text = _re.sub(r'<[^>]+>', ' ', cell_blocks[0]).strip()
        
        for idx, cell_html in enumerate(cell_blocks[1:]):
            cell_text = _re.split(r'(?i)</t[dh]>', cell_html)[0]
            clean_str = _re.sub(r'<[^>]+>', ' ', cell_text).strip()
            
            if idx == 0 and pre_cell_text:
                clean_str = pre_cell_text + " " + clean_str
                
            clean_str = _re.sub(r'[ \t\n\r]+', ' ', clean_str)
            clean_str = clean_str.replace('|', '\\|')
            clean_cells.append(clean_str)
            
        if clean_cells:
            md_row = "| " + " | ".join(clean_cells) + " |"
            if not in_table:
                sep = "| " + " | ".join(["---"] * len(clean_cells)) + " |"
                new_text_parts.append("\n\n" + md_row + "\n" + sep + "\n")
                in_table = True
            else:
                new_text_parts.append(md_row + "\n")
        else:
            in_table = False
            new_text_parts.append("\n" + pre_cell_text + "\n")
            
        # Strip structural table tags from after_row
        after_clean = _re.sub(r'(?i)</?(?:table|thead|tbody|tfoot)[^>]*>', '', after_row)
        after_clean = _re.sub(r'<!--.*?-->', '', after_clean, flags=_re.DOTALL)
        
        if not after_clean.strip():
            # Only whitespace between this row and the next. Keep it contiguous!
            after_clean = ""
        else:
            # Substantial text means the table broke or ended.
            in_table = False
            after_clean = "\n\n" + after_clean.strip() + "\n\n"
            
        new_text_parts.append(after_clean)

    text = "".join(new_text_parts)

    # Remove all remaining HTML tags
    text = _re.sub(r'<[^>]+>', '', text)

    # Clean up excessive whitespace and blank lines
    text = _re.sub(r'[ \t]+', ' ', text)           # Collapse spaces
    text = _re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Max 2 consecutive newlines

    # Decode HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"')

    return text.strip()
    text = text.replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"')

    return text.strip()


def _add_page_number(canvas, doc):
    """Add page number footer and subtle header line to each page."""
    canvas.saveState()

    # Page number footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#a0aec0"))
    canvas.drawCentredString(
        A4[0] / 2, 12 * mm,
        f"Page {canvas.getPageNumber()}",
    )

    # App name in footer right
    canvas.drawRightString(
        A4[0] - 20 * mm, 12 * mm,
        APP_NAME,
    )

    canvas.restoreState()
