"""
Notice Reply Drafting — Word Document Generator
Produces a formal reply skeleton (.docx) in standard Income Tax reply format.

All formatting rules are embedded here — no external sample data dependency.

Key formatting rules:
- Font: Times New Roman, size 12 throughout
- "the Assessee" — always capitalized 'A', always preceded by 'the'
- "Annexure" — always bold, followed by ' __' (blank for user to number)
- All body paragraphs: justified alignment
- Subject/Ref/DIN lines: bold labels
- Uses Word's auto-update date field (DATE field) so the date refreshes on open
"""

import logging
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────

FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(12)

CLOSING_NOTE = (
    "Before parting, we request your kind office to grant an opportunity of "
    "virtual hearing as prescribed u/s 144B of the Act. Should your kind office "
    "require any further information or explanation the Assessee shall be pleased "
    "to submit the same on hearing from your kind office to do so."
)


# ── Helpers ──────────────────────────────────────────────────

def _set_run_font(run, bold=False, italic=False, underline=False, size=None):
    """Apply Times New Roman formatting to a run."""
    run.font.name = FONT_NAME
    run.font.size = size or FONT_SIZE
    run.bold = bold
    run.italic = italic
    run.underline = underline
    # Ensure East Asian font is also Times New Roman
    r = run._element
    rPr = r.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        r.insert(0, rPr)
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), FONT_NAME)
    rFonts.set(qn("w:cs"), FONT_NAME)


def _add_paragraph(doc, text="", bold=False, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
                   style=None, space_after=None):
    """Add a paragraph with consistent formatting."""
    p = doc.add_paragraph()
    if style:
        p.style = style
    p.alignment = alignment
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)

    if text:
        run = p.add_run(text)
        _set_run_font(run, bold=bold)
    return p


def _add_date_field(paragraph):
    """
    Insert a Word auto-update DATE field into the paragraph.
    The date updates every time the document is opened.
    Format: MMMM dd, yyyy (e.g., "May 04, 2026")
    """
    run = paragraph.add_run()
    _set_run_font(run, bold=True)

    # Create the field character elements
    fldChar_begin = OxmlElement("w:fldChar")
    fldChar_begin.set(qn("w:fldCharType"), "begin")

    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = ' DATE \\@ "MMMM dd, yyyy" '

    fldChar_separate = OxmlElement("w:fldChar")
    fldChar_separate.set(qn("w:fldCharType"), "separate")

    # Fallback text (shown before field is updated)
    fallback_run = OxmlElement("w:r")
    fallback_rPr = OxmlElement("w:rPr")
    fallback_rFonts = OxmlElement("w:rFonts")
    fallback_rFonts.set(qn("w:ascii"), FONT_NAME)
    fallback_rFonts.set(qn("w:hAnsi"), FONT_NAME)
    fallback_rFonts.set(qn("w:cs"), FONT_NAME)
    fallback_rPr.append(fallback_rFonts)
    fallback_sz = OxmlElement("w:sz")
    fallback_sz.set(qn("w:val"), "24")  # 12pt = 24 half-points
    fallback_rPr.append(fallback_sz)
    fallback_b = OxmlElement("w:b")
    fallback_rPr.append(fallback_b)
    fallback_run.append(fallback_rPr)
    fallback_t = OxmlElement("w:t")
    fallback_t.text = datetime.now().strftime("%B %d, %Y")
    fallback_run.append(fallback_t)

    fldChar_end = OxmlElement("w:fldChar")
    fldChar_end.set(qn("w:fldCharType"), "end")

    # Append field elements to the run
    run._element.append(fldChar_begin)

    instr_run = OxmlElement("w:r")
    instr_rPr = OxmlElement("w:rPr")
    instr_rFonts = OxmlElement("w:rFonts")
    instr_rFonts.set(qn("w:ascii"), FONT_NAME)
    instr_rFonts.set(qn("w:hAnsi"), FONT_NAME)
    instr_rFonts.set(qn("w:cs"), FONT_NAME)
    instr_rPr.append(instr_rFonts)
    instr_sz = OxmlElement("w:sz")
    instr_sz.set(qn("w:val"), "24")
    instr_rPr.append(instr_sz)
    instr_b = OxmlElement("w:b")
    instr_rPr.append(instr_b)
    instr_run.append(instr_rPr)
    instr_run.append(instrText)

    # Insert into paragraph XML after the begin field char's run
    paragraph._element.append(instr_run)

    sep_run = OxmlElement("w:r")
    sep_run.append(fldChar_separate)
    paragraph._element.append(sep_run)

    paragraph._element.append(fallback_run)

    end_run = OxmlElement("w:r")
    end_run.append(fldChar_end)
    paragraph._element.append(end_run)


def _add_bold_label_line(doc, label, value, use_tab=True):
    """Add a line like 'Sub:    Reply to ...' with bold label and normal value."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)

    sep = "\t" if use_tab else " "

    run_label = p.add_run(f"{label}{sep}")
    _set_run_font(run_label, bold=True)

    run_value = p.add_run(value)
    _set_run_font(run_value, bold=True)

    return p


def _add_annexure_ref(paragraph, prefix_text="", suffix_text=""):
    """Add text with bold 'Annexure __' reference."""
    if prefix_text:
        run = paragraph.add_run(prefix_text)
        _set_run_font(run)

    run_ann = paragraph.add_run("Annexure __")
    _set_run_font(run_ann, bold=True)

    if suffix_text:
        run = paragraph.add_run(suffix_text)
        _set_run_font(run)


def _build_subject_line(notice_data: dict) -> str:
    """Construct the Subject line based on notice type and section."""
    section = notice_data.get("notice_section")
    notice_type = notice_data.get("notice_type", "notice")
    notice_date = notice_data.get("notice_date", "____")

    if section:
        return (
            f"Reply to Notice u/s {section} of the Income Tax Act, 1961 "
            f"(hereinafter referred to as \u2018the Act\u2019) dated {notice_date}"
        )
    else:
        return f"Reply in pursuance to {notice_type} dated {notice_date}"


def _build_opening_para(notice_data: dict) -> str:
    """Build the opening paragraph text."""
    notice_date = notice_data.get("notice_date", "____")
    section = notice_data.get("notice_section")
    notice_type = notice_data.get("notice_type", "notice")
    brief_context = notice_data.get("brief_context", "")
    ay = notice_data.get("assessment_year", "____")

    if section:
        return (
            f"The Assessee is in receipt of the above-mentioned notice u/s {section} "
            f"of the Act dated {notice_date} whereby your kind office has directed "
            f"the Assessee to provide various details and explanation"
            f"{' pertaining to ' + brief_context if brief_context else ''}"
            f". In this regard, it is submitted as under:"
        )
    else:
        return (
            f"The Assessee is in receipt of the above-mentioned {notice_type} "
            f"dated {notice_date} whereby your kind office has directed "
            f"the Assessee to provide various details"
            f"{' pertaining to ' + brief_context if brief_context else ''}"
            f". In this regard, it is submitted as under:"
        )


def _build_point_response(point: dict) -> str:
    """
    Build the response sentence for a single notice point.
    Returns the 'Vide point no. X ...' text.
    """
    point_nums = point.get("point_numbers", "____")
    what_is_asked = point.get("what_is_asked", "____")
    req_type = point.get("requirement_type", "information")
    approach = point.get("suggested_response_approach", "")

    # Build the opening part
    opening = (
        f"Vide point no. {point_nums} of the captioned notice, "
        f"your kind office has directed the Assessee to {what_is_asked}."
    )

    # Build the response part based on requirement type
    if req_type == "document":
        response = (
            " In respect of the same, the Assessee hereby submits ______. "
            "The same has been enclosed as"
        )
        # Annexure reference will be added separately with bold formatting
        return opening, response, True  # True = needs annexure ref

    elif req_type == "explanation":
        response = (
            " In respect of the same, it is submitted that ______."
        )
        return opening, response, False

    elif req_type == "proof":
        response = (
            " In respect of the same, the Assessee hereby submits ______. "
            "The same has been enclosed as"
        )
        return opening, response, True

    elif req_type == "compliance":
        response = (
            " In respect of the same, the Assessee submits its compliance as under: "
            "______."
        )
        return opening, response, False

    else:  # information or other
        response = (
            " In respect of the same, it is submitted that ______."
        )
        return opening, response, False


def _set_default_font(doc):
    """Set the default font for the entire document to Times New Roman 12pt."""
    style = doc.styles["Normal"]
    font = style.font
    font.name = FONT_NAME
    font.size = FONT_SIZE
    rPr = style.element.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        style.element.append(rPr)
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), FONT_NAME)
    rFonts.set(qn("w:cs"), FONT_NAME)

    # Also set for No Spacing style if it exists
    for style_name in ["No Spacing", "List Paragraph", "List Number"]:
        try:
            s = doc.styles[style_name]
            s.font.name = FONT_NAME
            s.font.size = FONT_SIZE
        except KeyError:
            pass


# ── Main Generator ───────────────────────────────────────────

def generate_reply_docx(notice_data: dict, output_path: str):
    """
    Generate a reply skeleton Word document.

    The document follows standard Income Tax reply format:
    Date → Addressee → Subject/Ref → Opening → Point-by-point → Closing → Sign-off

    All formatting: Times New Roman 12pt, justified, bold Annexure references.
    """
    doc = Document()
    _set_default_font(doc)

    # Reduce default paragraph spacing
    for style_name in ["Normal", "No Spacing"]:
        try:
            s = doc.styles[style_name]
            s.paragraph_format.space_after = Pt(0)
            s.paragraph_format.space_before = Pt(0)
        except KeyError:
            pass

    # Set page margins
    for section in doc.sections:
        section.top_margin = Pt(72)     # 1 inch
        section.bottom_margin = Pt(72)
        section.left_margin = Pt(72)
        section.right_margin = Pt(72)

    addressee = notice_data.get("addressee", {})
    is_company = notice_data.get("is_company", False)

    # ── 1. Date (auto-update field) ──────────────────────────
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    date_para.paragraph_format.space_after = Pt(0)
    _add_date_field(date_para)

    # Blank line
    _add_paragraph(doc)

    # ── 2. Addressee ─────────────────────────────────────────
    _add_paragraph(doc, "To,")

    designation = addressee.get("designation", "The Assessment Unit")
    _add_paragraph(doc, designation)

    ward = addressee.get("ward_unit", "")
    if ward:
        _add_paragraph(doc, ward)

    city = addressee.get("city", "")
    if city:
        _add_paragraph(doc, city)
    else:
        _add_paragraph(doc, "Income Tax Department")

    # Blank line
    _add_paragraph(doc)

    # ── 3. Salutation ────────────────────────────────────────
    _add_paragraph(doc, "Respected Sir/Madam,")

    # Blank line
    _add_paragraph(doc)

    # ── 4. Subject line ──────────────────────────────────────
    subject = _build_subject_line(notice_data)
    _add_bold_label_line(doc, "Sub:", subject)

    # ── 5. Reference / DIN line ──────────────────────────────
    din = notice_data.get("din", "")
    notice_type = notice_data.get("notice_type", "Notice")
    notice_date = notice_data.get("notice_date", "____")
    section = notice_data.get("notice_section")

    if section:
        ref_text = f"DIN: {din}" if din else ""
        if ref_text:
            _add_bold_label_line(doc, "DIN:", din)
    else:
        ref_parts = []
        if notice_type:
            ref_parts.append(f"{notice_type} dated {notice_date}")
        if din:
            ref_parts.append(f"bearing DIN: {din}")
        ref_value = " ".join(ref_parts)
        if ref_value:
            _add_bold_label_line(doc, "Ref:", ref_value)

    # ── 6. Assessee name line ────────────────────────────────
    assessee_name = notice_data.get("assessee_name", "____")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(0)

    if is_company:
        run = p.add_run(f"\t{assessee_name} ")
        _set_run_font(run, bold=True)
        run2 = p.add_run("(the \u201cAssessee\u201d)")
        _set_run_font(run2, bold=True)
    else:
        run = p.add_run(f"\t{assessee_name} ")
        _set_run_font(run, bold=True)
        run2 = p.add_run("(\u201cthe Assessee\u201d)")
        _set_run_font(run2, bold=True)

    # ── 7. AY and PAN ───────────────────────────────────────
    ay = notice_data.get("assessment_year", "____")
    pan = notice_data.get("pan", "____")
    _add_bold_label_line(doc, "A.Y.:", ay)
    _add_bold_label_line(doc, "PAN:", pan)

    # Blank line
    _add_paragraph(doc)

    # ── 8. Opening paragraph ─────────────────────────────────
    opening_text = _build_opening_para(notice_data)
    _add_paragraph(doc, opening_text)

    # Blank line
    _add_paragraph(doc)

    # ── 9. Point-by-point responses ──────────────────────────
    points = notice_data.get("points", [])
    for idx, point in enumerate(points):
        opening, response, needs_annexure = _build_point_response(point)

        # Create paragraph for manual numbered list
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)

        # Add the manual number and tab directly to the text (no negative indent trickery)
        run_num = p.add_run(f"{idx + 1}.\t")
        _set_run_font(run_num)

        # Add the opening text
        run = p.add_run(opening)
        _set_run_font(run)

        # Add the response text
        run2 = p.add_run(response)
        _set_run_font(run2)

        # Add Annexure reference if needed
        if needs_annexure:
            run_space = p.add_run(" ")
            _set_run_font(run_space)
            run_ann = p.add_run("Annexure __")
            _set_run_font(run_ann, bold=True)
            run_suffix = p.add_run(" for your ready reference.")
            _set_run_font(run_suffix)

        # Add table if needed
        needs_table = point.get("needs_table", False)
        table_columns = point.get("table_columns", [])
        if needs_table and table_columns:
            # Add blank line before table
            _add_paragraph(doc)

            table = doc.add_table(rows=2, cols=len(table_columns))
            table.style = "Table Grid"

            # Header row
            for col_idx, col_name in enumerate(table_columns):
                cell = table.cell(0, col_idx)
                cell.text = ""
                p_cell = cell.paragraphs[0]
                run = p_cell.add_run(col_name)
                _set_run_font(run, bold=True)

            # Placeholder data row
            for col_idx in range(len(table_columns)):
                cell = table.cell(1, col_idx)
                cell.text = ""
                p_cell = cell.paragraphs[0]
                run = p_cell.add_run("______")
                _set_run_font(run)

        # Blank line after each point
        _add_paragraph(doc)

    # ── 10. Closing note ─────────────────────────────────────
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(0)
    try:
        p.style = doc.styles["List Paragraph"]
    except KeyError:
        pass
    p.paragraph_format.left_indent = Pt(36)
    run = p.add_run(CLOSING_NOTE)
    _set_run_font(run)

    # Blank lines
    _add_paragraph(doc)
    _add_paragraph(doc)

    # ── 11. Sign-off ─────────────────────────────────────────
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(0)
    try:
        p.style = doc.styles["List Paragraph"]
    except KeyError:
        pass
    p.paragraph_format.left_indent = Pt(36)
    run = p.add_run("Thanking You,")
    _set_run_font(run)

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p2.paragraph_format.space_after = Pt(0)
    try:
        p2.style = doc.styles["List Paragraph"]
    except KeyError:
        pass
    p2.paragraph_format.left_indent = Pt(36)
    run = p2.add_run("Yours Faithfully,")
    _set_run_font(run)

    # Blank lines for signature space
    _add_paragraph(doc)
    _add_paragraph(doc)

    # Signature line
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(0)
    try:
        p.style = doc.styles["List Paragraph"]
    except KeyError:
        pass
    p.paragraph_format.left_indent = Pt(36)
    run = p.add_run("______________________________")
    _set_run_font(run)

    # Assessee name (bold)
    assessee_name = notice_data.get("assessee_name", "____")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(0)
    try:
        p.style = doc.styles["List Paragraph"]
    except KeyError:
        pass
    p.paragraph_format.left_indent = Pt(36)

    if is_company:
        run = p.add_run(assessee_name)
        _set_run_font(run, bold=True)

        # (Authorized Signatory)
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p2.paragraph_format.space_after = Pt(0)
        try:
            p2.style = doc.styles["List Paragraph"]
        except KeyError:
            pass
        p2.paragraph_format.left_indent = Pt(36)
        run = p2.add_run("(Authorized Signatory)")
        _set_run_font(run, bold=True)
    else:
        run = p.add_run(assessee_name)
        _set_run_font(run, bold=True)

    # Save
    doc.save(output_path)
    logger.info(f"Reply skeleton saved to {output_path}")
