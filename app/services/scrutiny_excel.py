"""
Order Scrutiny — Excel Generation
Creates the standardized Order Scrutiny Excel workbook using openpyxl.
"""

import logging
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, numbers
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────

FONT_NAME = "Times New Roman"
FONT_SIZE = 12
NUM_FMT = '_ * #,##0_ ;_ * \\-#,##0_ ;_ * "-"??_ ;_ @_ '

THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

COL_WIDTHS = {
    "A": 55.3, "B": 16.7, "C": 16.7, "D": 13.0,
    "E": 17.1, "F": 55.0, "G": 15.0, "H": 12.3,
}


def _font(bold=False, size=FONT_SIZE):
    return Font(name=FONT_NAME, size=size, bold=bold)


def _align(horizontal="left", wrap=True):
    return Alignment(horizontal=horizontal, vertical="center", wrap_text=wrap)


def _cell(ws, row, col, value, bold=False, num_fmt=None):
    """Set cell value with standard formatting."""
    c = ws.cell(row=row, column=col, value=value)
    c.font = _font(bold=bold)
    c.alignment = _align()
    if num_fmt:
        c.number_format = num_fmt
    return c


def _val(data, key, default=0):
    """Safely get a numeric value from dict."""
    v = data.get(key, default)
    if v is None or v == "" or v == "N/A":
        return 0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0


def _parse_date(date_str):
    """Parse DD/MM/YYYY string to datetime."""
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return date_str


def _gen_remark(roi_val, comp_val, head_name):
    """Generate remark if 143(3) differs from ROI."""
    try:
        r = float(roi_val) if roi_val else 0
        c = float(comp_val) if comp_val else 0
    except (ValueError, TypeError):
        return ""
    diff = c - r
    if abs(diff) < 1:
        return ""
    if diff > 0:
        return f"Addition of Rs. {abs(int(diff)):,} made by AO in {head_name}"
    else:
        return f"Reduction of Rs. {abs(int(diff)):,} by AO in {head_name}"


# ── Main Excel Generator ────────────────────────────────────

def generate_scrutiny_excel(comp_data: dict, intim_data: dict,
                            ao_data: dict, output_path: str,
                            progress_cb=None):
    """
    Generate the Order Scrutiny Excel workbook.

    comp_data  = Computation Sheet extracted data (143(3) column)
    intim_data = Intimation data with 'roi' and 'computed' sub-dicts
    ao_data    = Assessment Order data (optional, may be empty dict)
    """
    if progress_cb:
        progress_cb("generating", "Creating Excel workbook...", 0.7)

    wb = Workbook()
    ws = wb.active
    ws.title = "Tax Payable"

    # Column widths
    for col_letter, width in COL_WIDTHS.items():
        ws.column_dimensions[col_letter].width = width

    roi = intim_data.get("roi", {})
    c1 = intim_data.get("computed", {})
    c3 = comp_data

    entity = comp_data.get("entity_name") or intim_data.get("entity_name", "")
    ay = comp_data.get("assessment_year") or intim_data.get("assessment_year", "")

    # ── Row 1-3: Header ──────────────────────────────────────
    _cell(ws, 1, 1, entity.upper(), bold=True)
    _cell(ws, 2, 1, f"A.Y. {ay}", bold=True)

    # ── Row 4: Demand ────────────────────────────────────────
    _cell(ws, 4, 1, "Demand as per order u/s 156", bold=True)
    _cell(ws, 4, 2, _val(c3, "demand_amount") or _val(c3, "balance_payable_refundable"),
          bold=True, num_fmt=NUM_FMT)

    # ── Row 6-7: Section header ──────────────────────────────
    _cell(ws, 6, 1, "Working of Demand Payable or Refund", bold=True)
    _cell(ws, 7, 4, "(Amount in Rs.)")

    # ── Row 8: Column headers ────────────────────────────────
    headers = ["Particulars", "As per ROI", "As per 143(1)",
               "As per 143(3)", "Corrected Computation", "Remarks"]
    for i, h in enumerate(headers, 1):
        _cell(ws, 8, i, h, bold=True)

    # ── Row 9-10: Dates ──────────────────────────────────────
    _cell(ws, 9, 1, "Filing Date")
    _cell(ws, 9, 2, _parse_date(intim_data.get("filing_date")))
    if isinstance(ws.cell(9, 2).value, datetime):
        ws.cell(9, 2).number_format = "DD/MM/YYYY"
    _cell(ws, 9, 3, "-")
    _cell(ws, 9, 4, "-")

    _cell(ws, 10, 1, "Order Date")
    _cell(ws, 10, 2, "-")
    _cell(ws, 10, 3, _parse_date(intim_data.get("intimation_date")))
    if isinstance(ws.cell(10, 3).value, datetime):
        ws.cell(10, 3).number_format = "DD/MM/YYYY"
    _cell(ws, 10, 4, _parse_date(c3.get("order_date")))
    if isinstance(ws.cell(10, 4).value, datetime):
        ws.cell(10, 4).number_format = "DD/MM/YYYY"

    # ── Row 12: Section title (merged) ───────────────────────
    ws.merge_cells("A12:F12")
    _cell(ws, 12, 1, "Computation of Income Tax Payable/(Refundable)", bold=True)

    # ── Row 14: Heads of Income ──────────────────────────────
    _cell(ws, 14, 1, "Heads of Income ", bold=True)

    # Helper to fill a data row (A=label, B=ROI, C=143(1), D=143(3), F=remark)
    def data_row(row, label, roi_key, c1_key=None, c3_key=None,
                 bold=False, roi_val=None, c1_val=None, c3_val=None,
                 formula_b=None, formula_c=None, formula_d=None,
                 formula_e=None, auto_remark=False, remark=""):
        _cell(ws, row, 1, label, bold=bold)

        if formula_b:
            _cell(ws, row, 2, formula_b, bold=bold, num_fmt=NUM_FMT)
        elif roi_val is not None:
            _cell(ws, row, 2, roi_val, bold=bold, num_fmt=NUM_FMT)
        elif roi_key:
            _cell(ws, row, 2, _val(roi, roi_key), bold=bold, num_fmt=NUM_FMT)

        if formula_c:
            _cell(ws, row, 3, formula_c, bold=bold, num_fmt=NUM_FMT)
        elif c1_val is not None:
            _cell(ws, row, 3, c1_val, bold=bold, num_fmt=NUM_FMT)
        elif c1_key:
            _cell(ws, row, 3, _val(c1, c1_key), bold=bold, num_fmt=NUM_FMT)

        if formula_d:
            _cell(ws, row, 4, formula_d, bold=bold, num_fmt=NUM_FMT)
        elif c3_val is not None:
            _cell(ws, row, 4, c3_val, bold=bold, num_fmt=NUM_FMT)
        elif c3_key:
            _cell(ws, row, 4, _val(c3, c3_key), bold=bold, num_fmt=NUM_FMT)

        if formula_e:
            _cell(ws, row, 5, formula_e, bold=bold, num_fmt=NUM_FMT)

        # Auto-generate remark if difference exists
        if auto_remark and not remark:
            rv = _val(roi, roi_key) if roi_key else (roi_val or 0)
            cv = _val(c3, c3_key) if c3_key else (c3_val or 0)
            remark = _gen_remark(rv, cv, label.strip())

        if remark:
            _cell(ws, row, 6, remark)

    # ── Rows 15-23: Income heads ─────────────────────────────
    data_row(15, "Income from House Property",
             "income_house_property", "income_house_property", "income_house_property",
             auto_remark=True, c1_val=_val(c1, "income_house_property"))
    # Make C15 and D15 bold like sample
    ws.cell(15, 3).font = _font(bold=True)
    ws.cell(15, 4).font = _font(bold=True)

    data_row(16, "Profits and Gains from Business or Profession",
             "income_business_profession", "income_business_profession",
             "income_business_profession", auto_remark=True)

    # Addition rows (from AO) - populate from assessment order if available
    additions = ao_data.get("additions", []) if ao_data else []
    add_labels = [
        ("Add: Adjustment by TPO", 17),
        ("Add: Disallowance of CSR expense", 18),
        ("Add: Disallowance us 40(a)(ia) rws 194C", 19),
        ("Add: Disallowance us 40(a)(ia) rws 194R", 20),
    ]
    for label, row in add_labels:
        amt = 0
        remark = ""
        for a in additions:
            desc = (a.get("description") or "").lower()
            if any(kw in desc for kw in label.lower().split(":")[1].strip().split()):
                amt = a.get("amount", 0)
                remark = a.get("description", "")
                break
        _cell(ws, row, 1, label)
        _cell(ws, row, 4, amt, num_fmt=NUM_FMT)
        if remark:
            _cell(ws, row, 6, remark)

    data_row(21, "Income from Capital Gains",
             "income_capital_gains", "income_capital_gains",
             "income_capital_gains", auto_remark=True)

    data_row(22, "Income from Other Sources",
             "income_other_sources", None, None,
             formula_c="=B22", formula_d="=C22")

    _cell(ws, 23, 1, "Add: Forex Gain on dividend from foreign subsidiary")
    _cell(ws, 23, 4, 0, num_fmt=NUM_FMT)

    # ── Row 24: Gross Total Income ───────────────────────────
    data_row(24, "Gross Total Income as per Return of Income", None, None, None,
             bold=True, formula_b="=SUM(B15:B23)", formula_c="=SUM(C15:C23)",
             formula_d="=SUM(D15:D23)")

    # ── Row 26: Assessed GTI ─────────────────────────────────
    data_row(26, "Assessed Gross Total Income", None, None, None,
             bold=True, formula_b="=SUM(B24:B24)", formula_c="=SUM(C24:C24)",
             formula_d="=SUM(D24:D24)")

    # ── Row 28-30: Deductions ────────────────────────────────
    data_row(28, "Less: Deduction under Chapter VI-A", None, None, None,
             bold=True, formula_b="=SUM(B29:B30)", formula_c="=SUM(C29:C30)",
             formula_d="=SUM(D29:D30)")
    data_row(29, "Part-B of Chapter VI-A",
             "deduction_part_b", "deduction_part_b", "deduction_part_b")
    data_row(30, "Part-C of Chapter VI-A",
             "deduction_part_c", None, None,
             formula_c="=B30", formula_d="=C30")

    # ── Row 32: 10AA ─────────────────────────────────────────
    data_row(32, "Deduction u/s 10AA",
             "deduction_10aa", "deduction_10aa", "deduction_10aa")

    # ── Row 34: Total Income ─────────────────────────────────
    data_row(34, "Total Income as per Normal provisions", None, None, None,
             bold=True, formula_b="=ROUND(B26-B28,-1)",
             formula_c="=ROUND(C26-C28,-1)", formula_d="=ROUND(D26-D28,-1)")

    # ── Row 36: Tax ref Note-1 ───────────────────────────────
    data_row(36, "Tax as per Normal provision (Refer Note 1 below)",
             None, None, None, bold=True,
             formula_b="=B72", formula_c="=C72", formula_d="=D72")

    # ── Rows 38-44: Interest ─────────────────────────────────
    _cell(ws, 38, 1, "Add:")
    data_row(39, "       Interest U/s 234A",
             "interest_234a", "interest_234a", "interest_234a")
    data_row(40, "       Interest U/s 234B",
             "interest_234b", "interest_234b", "interest_234b",
             formula_d="=B40")
    data_row(41, "       Interest U/s 234C",
             "interest_234c", "interest_234c", None,
             formula_c="=B41", formula_d="=C41")
    data_row(42, "       Interest U/s 234D",
             None, None, None, roi_val=0, formula_c="=B42", formula_d="=C42")
    data_row(43, "       FEE FOR DEFAULT IN FURNISHING \nRETURN OF INCOME (SECTION 234F)",
             "fee_234f", "fee_234f", "fee_234f")

    # Total interest - use direct value for 143(3) if AO gave lump sum
    _cell(ws, 44, 1, "TOTAL INTEREST AND FEE PAYABLE", bold=True)
    _cell(ws, 44, 2, "=SUM(B39:B43)", num_fmt=NUM_FMT)
    _cell(ws, 44, 3, "=SUM(C39:C43)", num_fmt=NUM_FMT)
    total_int = _val(c3, "total_interest_fee")
    if total_int > 0:
        _cell(ws, 44, 4, total_int, bold=True, num_fmt=NUM_FMT)
        _cell(ws, 44, 6, f"Interest of Rs. {int(total_int):,} levied by AO")
    else:
        _cell(ws, 44, 4, "=SUM(D39:D43)", bold=True, num_fmt=NUM_FMT)

    # ── Row 46: Total Tax Payable ────────────────────────────
    data_row(46, "Total Tax Payable ", None, None, None,
             bold=True, formula_b="=B36+B44", formula_c="=C36+C44",
             formula_d="=D36+D44")

    # ── Rows 48-54: Taxes Paid ───────────────────────────────
    _cell(ws, 48, 1, "Less:", bold=True)
    data_row(49, "         Tax Deducted at Source",
             "tds", "tds", "tds", auto_remark=True)
    data_row(50, "         Tax Collected at Source",
             "tcs", "tcs", "tcs", auto_remark=True)
    data_row(51, "         Advance Tax",
             "advance_tax", None, "advance_tax",
             formula_c="=B51")
    data_row(52, "         Self Assessment Tax",
             "self_assessment_tax", None, None,
             formula_c="=B52", formula_d="=C52")
    data_row(53, "         Regular Assessment Tax",
             "regular_tax", "regular_tax", None, roi_val=0)

    data_row(54, "Total Taxes Paid", None, None, None,
             bold=True, formula_b="=SUM(B49:B53)",
             formula_c="=SUM(C49:C53)", formula_d="=SUM(D49:D53)")

    # ── Row 56-61: Net Tax / Refund ──────────────────────────
    data_row(56, "Net Tax Payable/Refundable", None, None, None,
             bold=True, formula_b="=ROUND(B46-SUM(B49:B53),-1)",
             formula_c="=ROUND(C46-SUM(C49:C53),-1)",
             formula_d="=ROUND(D46-SUM(D49:D53),-1)")

    _cell(ws, 57, 1, "Add: Interest u/s 244A (As per separate sheet attached)")
    for col in (2, 3, 4):
        _cell(ws, 57, col, 0, bold=True, num_fmt=NUM_FMT)

    _cell(ws, 58, 1, "Less: Refund Already Issued")
    _cell(ws, 58, 2, 0, num_fmt=NUM_FMT)
    _cell(ws, 58, 3, 0, num_fmt=NUM_FMT)
    ref_issued = _val(c3, "refund_already_issued")
    _cell(ws, 58, 4, ref_issued, num_fmt=NUM_FMT)
    if ref_issued > 0:
        _cell(ws, 58, 6, f"Refund of Rs. {int(ref_issued):,} already issued and adjusted")

    data_row(59, "Payable /(Refund)", None, None, None,
             bold=True, formula_b="=B56-B57+B58",
             formula_c="=C56-C57+C58", formula_d="=D56-D57+D58")

    _cell(ws, 60, 1, "Refund Adjusted")
    _cell(ws, 60, 2, 0, bold=True, num_fmt=NUM_FMT)

    data_row(61, "Payable /(Refund) - Round off  (A)", None, None, None,
             bold=True, formula_b="=ROUND(B59+B60,-1)",
             formula_c="=ROUND(C59+C60,-1)", formula_d="=ROUND(D59+D60,-1)")

    # ── Rows 64-72: Note-1 Tax Calculation ───────────────────
    if progress_cb:
        progress_cb("generating", "Building tax calculation note...", 0.85)

    _cell(ws, 64, 1, "Note-1 : Calculation of tax liability as per Normal provisions",
          bold=True)

    note_headers = ["Particulars", "As per ROI", "As per 143(1)",
                    "As per 143(3) r.w.s. 154", "Corrected Computation"]
    for i, h in enumerate(note_headers, 1):
        _cell(ws, 65, i, h, bold=True)

    # Tax at normal rates (22% for 115BAA companies)
    _cell(ws, 66, 1, "Tax at normal rates")
    for col in ("B", "C", "D", "E"):
        _cell(ws, 66, ord(col) - 64, f"={col}34*22%", num_fmt=NUM_FMT)

    _cell(ws, 67, 1, "Tax at special rates")
    _cell(ws, 67, 2, 0, num_fmt=NUM_FMT)
    _cell(ws, 67, 3, "=B67", num_fmt=NUM_FMT)
    _cell(ws, 67, 4, 0, num_fmt=NUM_FMT)
    _cell(ws, 67, 5, 0, num_fmt=NUM_FMT)

    _cell(ws, 68, 1, "Total", bold=True)
    for col in ("B", "C", "D", "E"):
        _cell(ws, 68, ord(col) - 64, f"=SUM({col}66:{col}67)", bold=True, num_fmt=NUM_FMT)

    _cell(ws, 70, 1, "Surcharge @ 10%")
    for col in ("B", "C", "D", "E"):
        _cell(ws, 70, ord(col) - 64, f"={col}68*10%", num_fmt=NUM_FMT)

    _cell(ws, 71, 1, "Cess @ 4%")
    for col in ("B", "C", "D", "E"):
        _cell(ws, 71, ord(col) - 64, f"=({col}70+{col}68)*4%", num_fmt=NUM_FMT)

    _cell(ws, 72, 1, "Total", bold=True)
    for col in ("B", "C", "D", "E"):
        _cell(ws, 72, ord(col) - 64, f"=+{col}70+{col}71+{col}68", bold=True, num_fmt=NUM_FMT)

    # ── Apply number format to all data cells ────────────────
    for row in range(8, 73):
        for col in range(2, 6):
            c = ws.cell(row, col)
            if c.value is not None and not c.number_format.startswith("DD"):
                if c.number_format == "General":
                    c.number_format = NUM_FMT
            c.alignment = _align()
            if not c.font.name:
                c.font = _font()

    # ── Save ─────────────────────────────────────────────────
    if progress_cb:
        progress_cb("generating", "Saving Excel file...", 0.95)

    wb.save(output_path)
    logger.info(f"Order Scrutiny Excel saved: {output_path}")
    return output_path
