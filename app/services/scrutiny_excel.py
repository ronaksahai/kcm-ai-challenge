"""
Order Scrutiny — Excel Generation
Creates the standardized Order Scrutiny Excel workbook using openpyxl.
Supports dynamic addition heads from Assessment Order and optional CIT(A) column.
"""

import logging
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
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


def _match_ground_to_addition(grounds: list, addition: dict) -> dict | None:
    """Find a CIT(A) ground that matches a given AO addition."""
    add_desc = (addition.get("description") or "").lower()
    add_section = (addition.get("section") or "").lower()
    add_amount = addition.get("amount", 0)

    for g in grounds:
        g_section = (g.get("section") or "").lower()
        g_amount = g.get("addition_amount", 0)

        # Match by section if both have one
        if add_section and g_section and add_section == g_section:
            return g
        # Match by amount
        if add_amount and g_amount and abs(abs(add_amount) - abs(g_amount)) < 2:
            return g

    # If no exact match, fallback to keyword overlap
    for g in grounds:
        g_desc = (g.get("addition_description") or g.get("description") or "").lower()
        add_words = set(add_desc.split())
        g_words = set(g_desc.split())
        overlap = add_words & g_words
        # Need meaningful overlap (excluding common words)
        common = {"of", "in", "the", "u/s", "us", "respect", "issue", "variation",
                  "addition", "disallowance", "add", "on", "and", "for", "to", "a",
                  "an", "as", "by", "at", "with", "from", "is", "was", "rs.", "rs",
                  "amount", "total", "income", "interest"}
        meaningful = overlap - common
        if len(meaningful) >= 3:
            return g

    return None


# ── Main Excel Generator ────────────────────────────────────

def generate_scrutiny_excel(comp_data: dict, intim_data: dict,
                            ao_data: dict, output_path: str,
                            cita_data: dict = None, progress_cb=None):
    """
    Generate the Order Scrutiny Excel workbook.

    comp_data  = Computation Sheet extracted data (143(3) column)
    intim_data = Intimation data with 'roi' and 'computed' sub-dicts
    ao_data    = Assessment Order data (required, has 'additions' list)
    cita_data  = CIT(A) Order data (optional, has 'grounds' list)
    """
    if progress_cb:
        progress_cb("generating", "Creating Excel workbook...", 0.7)

    wb = Workbook()
    ws = wb.active
    ws.title = "Tax Payable"

    has_cita = bool(cita_data and cita_data.get("grounds"))

    # ── Column layout ────────────────────────────────────────
    # Columns follow the chronological timeline:
    # A: Particulars
    # B: As per ROI
    # C: As per 143(1)
    # D: As per 143(3)
    # E: As per CIT(A) u/s 250 (only if CIT(A) data present)
    # then: Corrected Computation, Remarks
    is_itr = intim_data.get("is_itr", False)
    has_143_1 = not is_itr

    col_idx = 2
    COL_ROI = col_idx; col_idx += 1
    if has_143_1:
        COL_C1 = col_idx; col_idx += 1
    else:
        COL_C1 = None
    COL_C3 = col_idx; col_idx += 1
    if has_cita:
        COL_CITA = col_idx; col_idx += 1
    else:
        COL_CITA = None
    COL_CORRECTED = col_idx; col_idx += 1
    COL_REMARKS = col_idx

    col_widths = {"A": 55.3}
    letters = ["B", "C", "D", "E", "F", "G", "H", "I"]
    curr = 0
    col_widths[letters[curr]] = 16.7; curr += 1
    if has_143_1:
        col_widths[letters[curr]] = 16.7; curr += 1
    col_widths[letters[curr]] = 16.7 if has_cita else 13.0; curr += 1
    if has_cita:
        col_widths[letters[curr]] = 20.0; curr += 1
    col_widths[letters[curr]] = 17.1; curr += 1
    col_widths[letters[curr]] = 55.0; curr += 1

    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    # Helper to get column letter
    def cl(col_num):
        return get_column_letter(col_num)

    # 143(3) column base should ALWAYS be the Return of Income (ROI), 
    # because Assessment Orders scrutinize the returned income, not the 143(1) intimation.
    roi = intim_data.get("roi") or {}
    base_data = roi
    base_col = cl(COL_ROI)
    # c3_col: used for CIT(A) deductions/interest that inherit from AO
    c3_col = cl(COL_C3)
    base_data = base_data or {}


    c1 = intim_data.get("computed") or {}
    c3 = comp_data
    additions = ao_data.get("additions", []) if ao_data else []
    grounds = cita_data.get("grounds", []) if cita_data else []

    entity = comp_data.get("entity_name") or intim_data.get("entity_name", "")
    ay = comp_data.get("assessment_year") or intim_data.get("assessment_year", "")

    # ── Row 1-3: Header ──────────────────────────────────────
    _cell(ws, 1, 1, entity.upper(), bold=True)
    _cell(ws, 2, 1, f"A.Y. {ay}", bold=True)

    # ── Row 4: Demand ────────────────────────────────────────
    _cell(ws, 4, 1, "Demand as per order u/s 156", bold=True)
    _cell(ws, 4, COL_ROI, _val(c3, "demand_amount") or _val(c3, "balance_payable_refundable"),
          bold=True, num_fmt=NUM_FMT)

    # ── Row 6-7: Section header ──────────────────────────────
    _cell(ws, 6, 1, "Working of Demand Payable or Refund", bold=True)
    _cell(ws, 7, COL_C3, "(Amount in Rs.)")

    # ── Row 8: Column headers ────────────────────────────────
    headers = ["Particulars", "As per ROI"]
    if has_143_1:
        headers.append("As per 143(1)")
    headers.append("As per 143(3)")
    if has_cita:
        headers.append("As per CIT(A)\nu/s 250")
    headers.extend(["Corrected\nComputation", "Remarks"])
    for i, h in enumerate(headers, 1):
        _cell(ws, 8, i, h, bold=True)

    # ── Row 9-10: Dates ──────────────────────────────────────
    _cell(ws, 9, 1, "Filing Date")
    _cell(ws, 9, COL_ROI, _parse_date(intim_data.get("filing_date")))
    if isinstance(ws.cell(9, COL_ROI).value, datetime):
        ws.cell(9, COL_ROI).number_format = "DD/MM/YYYY"
    if has_143_1:
        _cell(ws, 9, COL_C1, "-")
    _cell(ws, 9, COL_C3, "-")
    if has_cita:
        _cell(ws, 9, COL_CITA, "-")

    _cell(ws, 10, 1, "Order Date")
    _cell(ws, 10, COL_ROI, "-")
    if has_143_1:
        _cell(ws, 10, COL_C1, _parse_date(intim_data.get("intimation_date")))
        if isinstance(ws.cell(10, COL_C1).value, datetime):
            ws.cell(10, COL_C1).number_format = "DD/MM/YYYY"
    _cell(ws, 10, COL_C3, _parse_date(c3.get("order_date")))
    if isinstance(ws.cell(10, COL_C3).value, datetime):
        ws.cell(10, COL_C3).number_format = "DD/MM/YYYY"
    if has_cita:
        _cell(ws, 10, COL_CITA, _parse_date(cita_data.get("order_date")))
        if isinstance(ws.cell(10, COL_CITA).value, datetime):
            ws.cell(10, COL_CITA).number_format = "DD/MM/YYYY"

    # ── Row 12: Section title (merged) ───────────────────────
    last_col_letter = cl(len(headers))
    ws.merge_cells(f"A12:{last_col_letter}12")
    _cell(ws, 12, 1, "Computation of Income Tax Payable/(Refundable)", bold=True)

    # ── Row 14: Heads of Income ──────────────────────────────
    _cell(ws, 14, 1, "Heads of Income ", bold=True)

    # ── Helper: data_row ─────────────────────────────────────
    def data_row(row, label, roi_key=None, c1_key=None, c3_key=None,
                 bold=False, roi_val=None, c1_val=None, c3_val=None,
                 cita_val=None,
                 formula_b=None, formula_c=None, formula_d=None,
                 formula_e=None, formula_corr=None,
                 auto_remark=False, remark=""):
        _cell(ws, row, 1, label, bold=bold)

        # Column B: ROI
        if formula_b:
            _cell(ws, row, COL_ROI, formula_b, bold=bold, num_fmt=NUM_FMT)
        elif roi_val is not None:
            _cell(ws, row, COL_ROI, roi_val, bold=bold, num_fmt=NUM_FMT)
        elif roi_key:
            _cell(ws, row, COL_ROI, _val(roi, roi_key), bold=bold, num_fmt=NUM_FMT)

        # Column C: 143(1)
        if has_143_1:
            if formula_c:
                _cell(ws, row, COL_C1, formula_c, bold=bold, num_fmt=NUM_FMT)
            elif c1_val is not None:
                _cell(ws, row, COL_C1, c1_val, bold=bold, num_fmt=NUM_FMT)
            elif c1_key:
                _cell(ws, row, COL_C1, _val(c1, c1_key), bold=bold, num_fmt=NUM_FMT)

        # Column D: 143(3)
        if formula_d:
            _cell(ws, row, COL_C3, formula_d, bold=bold, num_fmt=NUM_FMT)
        elif c3_val is not None:
            _cell(ws, row, COL_C3, c3_val, bold=bold, num_fmt=NUM_FMT)
        elif c3_key:
            _cell(ws, row, COL_C3, _val(c3, c3_key), bold=bold, num_fmt=NUM_FMT)

        # Column E: CIT(A) (only if present)
        if has_cita:
            if formula_e:
                _cell(ws, row, COL_CITA, formula_e, bold=bold, num_fmt=NUM_FMT)
            elif cita_val is not None:
                _cell(ws, row, COL_CITA, cita_val, bold=bold, num_fmt=NUM_FMT)

        # Corrected Computation
        if formula_corr:
            _cell(ws, row, COL_CORRECTED, formula_corr, bold=bold, num_fmt=NUM_FMT)

        # Auto-generate remark if difference exists
        if auto_remark and not remark:
            rv = _val(roi, roi_key) if roi_key else (roi_val or 0)
            cv = _val(c3, c3_key) if c3_key else (c3_val or 0)
            remark = _gen_remark(rv, cv, label.strip())

        if remark:
            _cell(ws, row, COL_REMARKS, remark)

    # ── Rows 15+: Income heads with dynamic additions ────────

    # Group additions by head_of_income
    additions_by_head = {}
    for a in additions:
        head = (a.get("head_of_income")
                or "Business or Profession").strip()
        # Normalize head names
        head_lower = head.lower()
        if "house" in head_lower:
            head = "House Property"
        elif ("business" in head_lower
              or "profession" in head_lower):
            head = "Business or Profession"
        elif "capital" in head_lower:
            head = "Capital Gains"
        elif "other" in head_lower:
            head = "Other Sources"
        additions_by_head.setdefault(head, []).append(a)

    # ── Helper: write addition sub-rows ────────────────────────
    def _write_addition_rows(start_row, head_additions, grounds_list, head_key):
        """Write addition sub-rows under a major head. Returns next row."""
        row = start_row
        sum_adds = 0
        for a in head_additions:
            desc = a.get("description", "Addition")
            amt = a.get("amount", 0)
            sum_adds += amt
            matched = (_match_ground_to_addition(grounds_list, a)
                       if grounds_list else None)
            remark = desc
            cita_cell_val = amt  # Default: copy addition as-is to CIT(A) column

            if matched:
                status = matched.get("status", "")
                relief = matched.get("relief_amount", 0)
                cita_remark = ""
                if status == "allowed":
                    cita_cell_val = 0
                    cita_remark = (
                        "Allowed by CIT(A) — addition deleted")
                elif status == "dismissed":
                    cita_cell_val = amt
                    cita_remark = (
                        "Dismissed by CIT(A) — addition upheld")
                elif status == "partly_allowed":
                    cita_cell_val = amt - relief
                    cita_remark = (
                        "Partly allowed by CIT(A) — "
                        f"relief of Rs. {int(relief):,}")
                elif status == "allowed_for_statistical_purpose":
                    cita_cell_val = amt
                    cita_remark = (
                        "Allowed for statistical purpose "
                        "— set aside to AO")
                if cita_remark:
                    remark = f"{desc}. {cita_remark}"
                if matched.get("remarks"):
                    remark += f". {matched['remarks']}"

            label = f"Add: {desc}" if amt >= 0 else f"Less: {desc}"
            _cell(ws, row, 1, label)
            _cell(ws, row, COL_C3, amt, num_fmt=NUM_FMT)
            if has_cita and cita_cell_val is not None:
                _cell(ws, row, COL_CITA, cita_cell_val,
                      num_fmt=NUM_FMT)
            if remark:
                _cell(ws, row, COL_REMARKS, remark)
            row += 1

        return row

    cur_row = 15
    hp_row = cur_row  # remember first income row for GTI SUM

    # For column D, we need smart logic:
    # - If there are additions for a head: use ROI base (additions add the rest as sub-rows)
    # - If there are NO additions for a head: use comp_data directly (no sub-rows will bridge the gap)
    def _d_for_head(head_key, head_group_name, row):
        """Return (formula_d, c3_key) tuple for the income head data_row."""
        has_adds = bool(additions_by_head.get(head_group_name, []))
        if has_adds:
            return f"={base_col}{row}", None  # formula pointing to ROI; additions follow
        else:
            return None, head_key  # use comp_data value directly

    # --- House Property ---
    fd, ck = _d_for_head("income_house_property", "House Property", cur_row)
    data_row(cur_row, "Income from House Property",
             "income_house_property", "income_house_property", ck,
             formula_d=fd,
             formula_e=f"={cl(COL_ROI)}{cur_row}" if has_cita else None)
    cur_row += 1
    # Addition sub-rows for House Property
    hp_adds = additions_by_head.get("House Property", [])
    if hp_adds or _val(c3, "income_house_property") != _val(base_data, "income_house_property"):
        cur_row = _write_addition_rows(cur_row, hp_adds, grounds, "income_house_property")

    # --- Business or Profession ---
    fd, ck = _d_for_head("income_business_profession", "Business or Profession", cur_row)
    data_row(cur_row, "Profits and Gains from Business or Profession",
             "income_business_profession",
             "income_business_profession", ck,
             formula_d=fd,
             formula_e=f"={cl(COL_ROI)}{cur_row}" if has_cita else None)
    cur_row += 1
    # Addition sub-rows for PGBP
    bp_adds = additions_by_head.get("Business or Profession", [])
    if bp_adds or _val(c3, "income_business_profession") != _val(base_data, "income_business_profession"):
        cur_row = _write_addition_rows(cur_row, bp_adds, grounds, "income_business_profession")

    # --- Capital Gains ---
    fd, ck = _d_for_head("income_capital_gains", "Capital Gains", cur_row)
    data_row(cur_row, "Income from Capital Gains",
             "income_capital_gains", "income_capital_gains", ck,
             formula_d=fd,
             formula_e=f"={cl(COL_ROI)}{cur_row}" if has_cita else None)
    cur_row += 1
    # Addition sub-rows for Capital Gains
    cg_adds = additions_by_head.get("Capital Gains", [])
    if cg_adds or _val(c3, "income_capital_gains") != _val(base_data, "income_capital_gains"):
        cur_row = _write_addition_rows(cur_row, cg_adds, grounds, "income_capital_gains")

    # --- Other Sources ---
    fd, ck = _d_for_head("income_other_sources", "Other Sources", cur_row)
    data_row(cur_row, "Income from Other Sources",
             "income_other_sources", "income_other_sources", ck,
             formula_d=fd,
             formula_e=f"={cl(COL_ROI)}{cur_row}" if has_cita else None)
    cur_row += 1
    # Addition sub-rows for Other Sources
    os_adds = additions_by_head.get("Other Sources", [])
    if os_adds or _val(c3, "income_other_sources") != _val(base_data, "income_other_sources"):
        cur_row = _write_addition_rows(cur_row, os_adds, grounds, "income_other_sources")

    # ── Overall Balancing Figure ─────────────────────────────
    # Column D base mirrors _d_for_head: ROI for heads with additions,
    # comp_data for heads without additions.
    _head_groups = {
        "income_house_property": "House Property",
        "income_business_profession": "Business or Profession",
        "income_capital_gains": "Capital Gains",
        "income_other_sources": "Other Sources",
    }
    sum_d_base = 0
    for _hk, _hg in _head_groups.items():
        if additions_by_head.get(_hg, []):
            sum_d_base += _val(base_data, _hk) or 0  # ROI base when additions exist
        else:
            sum_d_base += _val(c3, _hk) or 0  # comp_data when no additions
    sum_adds = sum((a.get("amount") or 0) for a in additions)
    expected_sum_of_heads = (_val(c3, "gross_total_income") or 0) + (_val(c3, "current_year_loss_setoff") or 0) + (_val(c3, "brought_forward_loss_setoff") or 0)

    overall_diff = expected_sum_of_heads - (sum_d_base + sum_adds)
    
    # ── Math Rescue: Missing Loss Setoffs in 143(3) ────────────────
    # If the AO order states Total Income but leaves the loss setoff implicit, 
    # overall_diff will exactly match the missing loss setoff as a negative number.
    if overall_diff < 0 and _val(c3, "brought_forward_loss_setoff") == 0:
        roi_bf = _val(base_data, "brought_forward_loss_setoff") or 0
        if roi_bf > 0 and abs(overall_diff + roi_bf) < 10:
            c3["brought_forward_loss_setoff"] = roi_bf
            overall_diff = 0
            
    if overall_diff < 0 and _val(c3, "current_year_loss_setoff") == 0:
        roi_cy = _val(base_data, "current_year_loss_setoff") or 0
        if roi_cy > 0 and abs(overall_diff + roi_cy) < 10:
            c3["current_year_loss_setoff"] = roi_cy
            overall_diff = 0

    if overall_diff != 0:
        label = "Add: Other unaccounted adjustments as per computation sheet" if overall_diff > 0 else "Less: Other unaccounted reductions as per computation sheet"
        _cell(ws, cur_row, 1, label)
        _cell(ws, cur_row, COL_C3, overall_diff, num_fmt=NUM_FMT)
        # We purposely do NOT copy 143(3) balancing figures to the CIT(A) column, 
        # as CIT(A) operates on explicit grounds and has independent math.
        _cell(ws, cur_row, COL_REMARKS, "Balancing figure to match Gross Total Income in computation sheet")
        cur_row += 1

    # ── Loss Setoffs ─────────────────────────────────────────
    cy_row = cur_row
    data_row(cy_row, "Less: Losses of current year set off",
             "current_year_loss_setoff", "current_year_loss_setoff", "current_year_loss_setoff",
             formula_e=f"={cl(COL_ROI)}{cur_row}" if has_cita else None)
    cur_row += 1

    bf_row = cur_row
    data_row(bf_row, "Less: Brought forward losses set off",
             "brought_forward_loss_setoff", "brought_forward_loss_setoff", "brought_forward_loss_setoff",
             formula_e=f"={c3_col}{cur_row}" if has_cita else None)
    cur_row += 1

    # ── Gross Total Income ───────────────────────────────────
    # Sum from the first income head row to the row before loss setoffs, minus setoffs
    gti_row = cur_row
    b, c, d = cl(COL_ROI), cl(COL_C1) if has_143_1 else "", cl(COL_C3)
    
    fc = f"=SUM({c}{hp_row}:{c}{cy_row - 1})-{c}{cy_row}-{c}{bf_row}" if has_143_1 else None
    data_row(gti_row,
             "Gross Total Income as per Return of Income",
             None, None, None, bold=True,
             formula_b=f"=SUM({b}{hp_row}:{b}{cy_row - 1})-{b}{cy_row}-{b}{bf_row}",
             formula_c=fc,
             formula_d=f"=SUM({d}{hp_row}:{d}{cy_row - 1})-{d}{cy_row}-{d}{bf_row}")
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, gti_row, COL_CITA,
              f"=SUM({e}{hp_row}:{e}{cy_row - 1})-{e}{cy_row}-{e}{bf_row}",
              bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Assessed Gross Total Income ──────────────────────────
    agti_row = cur_row
    data_row(agti_row, "Assessed Gross Total Income", None, None, None,
             bold=True,
             formula_b=f"={b}{gti_row}",
             formula_c=f"={c}{gti_row}",
             formula_d=f"={d}{gti_row}")
    if has_cita:
        _cell(ws, agti_row, COL_CITA,
              f"={cl(COL_CITA)}{gti_row}", bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Deductions ───────────────────────────────────────────
    # Determine if we need to use total_deductions_via as fallback
    roi_ded_b = _val(roi, "deduction_part_b")
    roi_ded_c = _val(roi, "deduction_part_c")
    roi_ded_total = _val(roi, "total_deductions_via")
    c1_ded_b = _val(c1, "deduction_part_b")
    c1_ded_c = _val(c1, "deduction_part_c")
    c1_ded_total = _val(c1, "total_deductions_via")
    c3_ded_b = _val(c3, "deduction_part_b")
    c3_ded_c = _val(c3, "deduction_part_c")
    c3_ded_total = _val(c3, "total_deductions_via")

    # If Part-B + Part-C = 0 but total_deductions_via > 0, use total as Part-B fallback
    if roi_ded_b + roi_ded_c == 0 and roi_ded_total > 0:
        roi_ded_b = roi_ded_total
    if c1_ded_b + c1_ded_c == 0 and c1_ded_total > 0:
        c1_ded_b = c1_ded_total
    if c3_ded_b + c3_ded_c == 0 and c3_ded_total > 0:
        c3_ded_b = c3_ded_total

    ded_header_row = cur_row
    ded_b_row = cur_row + 1
    ded_c_row = cur_row + 2

    data_row(ded_header_row, "Less: Deduction under Chapter VI-A", None, None, None,
             bold=True,
             formula_b=f"=SUM({b}{ded_b_row}:{b}{ded_c_row})",
             formula_c=f"=SUM({c}{ded_b_row}:{c}{ded_c_row})",
             formula_d=f"=SUM({d}{ded_b_row}:{d}{ded_c_row})")
    if has_cita:
        _cell(ws, ded_header_row, COL_CITA,
              f"=SUM({cl(COL_CITA)}{ded_b_row}:{cl(COL_CITA)}{ded_c_row})",
              bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    data_row(cur_row, "Part-B of Chapter VI-A",
             roi_val=roi_ded_b, c1_val=c1_ded_b if has_143_1 else None,
             c3_val=c3_ded_b)
    if has_cita:
        _cell(ws, cur_row, COL_CITA,
              f"={cl(COL_C3)}{cur_row}", num_fmt=NUM_FMT)
    cur_row += 1

    data_row(cur_row, "Part-C of Chapter VI-A",
             roi_val=roi_ded_c, c1_val=c1_ded_c if has_143_1 else None,
             c3_val=c3_ded_c)
    if has_cita:
        _cell(ws, cur_row, COL_CITA,
              f"={cl(COL_C3)}{cur_row}", num_fmt=NUM_FMT)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Deduction u/s 10AA ───────────────────────────────────
    ded10aa_row = cur_row
    data_row(cur_row, "Deduction u/s 10AA",
             "deduction_10aa", "deduction_10aa", "deduction_10aa")
    if has_cita:
        _cell(ws, cur_row, COL_CITA,
              f"={cl(COL_C3)}{cur_row}", num_fmt=NUM_FMT)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Total Income ─────────────────────────────────────────
    ti_row = cur_row
    data_row(ti_row, "Total Income as per Normal provisions", None, None, None,
             bold=True,
             formula_b=f"=ROUND({b}{agti_row}-{b}{ded_header_row},-1)",
             formula_c=f"=ROUND({c}{agti_row}-{c}{ded_header_row},-1)" if has_143_1 else None,
             formula_d=f"=ROUND({d}{agti_row}-{d}{ded_header_row},-1)")
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, ti_row, COL_CITA,
              f"=ROUND({e}{agti_row}-{e}{ded_header_row},-1)",
              bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # ── Income chargeable to tax at special rates ──────────
    special_inc_row = cur_row
    data_row(cur_row, "Income chargeable to tax at special rates",
             "income_special_rates", "income_special_rates", "income_special_rates")
    if has_cita:
        _cell(ws, cur_row, COL_CITA,
              f"={cl(COL_C3)}{cur_row}", num_fmt=NUM_FMT)
    cur_row += 1

    # ── Income chargeable to tax at normal rates ───────────
    normal_inc_row = cur_row
    data_row(cur_row, "Income chargeable to tax at normal rates",
             None, None, None,
             formula_b=f"={b}{ti_row}-{b}{special_inc_row}",
             formula_c=f"={c}{ti_row}-{c}{special_inc_row}" if has_143_1 else None,
             formula_d=f"={d}{ti_row}-{d}{special_inc_row}")
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, cur_row, COL_CITA,
              f"={e}{ti_row}-{e}{special_inc_row}", num_fmt=NUM_FMT)
    cur_row += 1

    # ── Deemed Total Income u/s 115JB ────────────────────────
    mat_inc_row = cur_row
    roi_mat = _val(roi, "income_115jb")
    c1_mat = _val(c1, "income_115jb")
    c3_mat = _val(c3, "income_115jb")
    
    cita_mat = None
    if has_cita:
        cita_mat = _val(cita_data, "income_115jb")
        if not cita_mat:
            mat_relief = sum(g.get("relief_amount", 0) for g in grounds if str(g.get("section", "")).upper() == "115JB")
            cita_mat = c3_mat - mat_relief if c3_mat else None

    data_row(cur_row, "Deemed Total Income u/s 115JB",
             roi_val=roi_mat, 
             c1_val=c1_mat if has_143_1 else None,
             c3_val=c3_mat,
             cita_val=cita_mat)
    cur_row += 1

    # ── Losses carried forward ───────────────────────────────
    cf_row = cur_row
    data_row(cur_row, "Losses in current year to be carried forward",
             "loss_carried_forward", "loss_carried_forward", "loss_carried_forward",
             formula_e=f"={cl(COL_ROI)}{cur_row}" if has_cita else None)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Tax (Refer Note-1) ───────────────────────────────────
    # We'll set the note row reference later
    tax_ref_row = cur_row
    # Placeholder — will be filled with formula referencing note total
    _cell(ws, tax_ref_row, 1, "Tax as per Normal provision (Refer Note 1 below)", bold=True)
    cur_row += 1

    # Insert 115JAA credit row
    credit_115_row = cur_row
    _cell(ws, cur_row, 1, "Credit u/s 115JAA of tax paid in earlier years")
    roi_credit_115 = _val(roi, "credit_115jaa") or 0
    c1_credit_115 = _val(c1, "credit_115jaa") if has_143_1 else 0
    c1_credit_115 = c1_credit_115 or 0
    c3_credit_115 = _val(c3, "credit_115jaa") or 0
    # Formulas will be filled after Note-1 is generated
    cur_row += 1

    # Tax payable after credit
    tax_after_credit_row = cur_row
    _cell(ws, cur_row, 1, "Tax payable after credit u/s 115JAA", bold=True)
    
    _cell(ws, cur_row, COL_ROI, f"={b}{tax_ref_row}-{b}{credit_115_row}", bold=True, num_fmt=NUM_FMT)
    if has_143_1:
        _cell(ws, cur_row, COL_C1, f"={c}{tax_ref_row}-{c}{credit_115_row}", bold=True, num_fmt=NUM_FMT)
    _cell(ws, cur_row, COL_C3, f"={d}{tax_ref_row}-{d}{credit_115_row}", bold=True, num_fmt=NUM_FMT)
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, cur_row, COL_CITA, f"={e}{tax_ref_row}-{e}{credit_115_row}", bold=True, num_fmt=NUM_FMT)
    _cell(ws, cur_row, COL_CORRECTED, 0, num_fmt=NUM_FMT)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Interest Section ─────────────────────────────────────
    _cell(ws, cur_row, 1, "Add:")
    cur_row += 1

    int_start = cur_row
    
    # helper for interest rows
    def _int_row(label, key):
        nonlocal cur_row
        formula_e = None
        cita_val = None
        if has_cita:
            if cita_data.get(key) is not None:
                cita_val = cita_data.get(key)
            else:
                formula_e = f"={cl(COL_C3)}{cur_row}"
                
        data_row(cur_row, label, key, key, key,
                 cita_val=cita_val, formula_e=formula_e)
        cur_row += 1

    _int_row("       Interest U/s 234A", "interest_234a")
    _int_row("       Interest U/s 234B", "interest_234b")
    _int_row("       Interest U/s 234C", "interest_234c")
    _int_row("       Interest U/s 234D", "interest_234d")
    
    int_end = cur_row
    _int_row("       FEE FOR DEFAULT IN FURNISHING \nRETURN OF INCOME (SECTION 234F)", "fee_234f")

    # Total interest
    total_int_row = cur_row
    _cell(ws, total_int_row, 1, "TOTAL INTEREST AND FEE PAYABLE", bold=True)
    _cell(ws, total_int_row, COL_ROI,
          f"=SUM({b}{int_start}:{b}{int_end})", num_fmt=NUM_FMT)
    if has_143_1:
        _cell(ws, total_int_row, COL_C1,
              f"=SUM({c}{int_start}:{c}{int_end})", num_fmt=NUM_FMT)
    _cell(ws, total_int_row, COL_C3,
          f"=SUM({cl(COL_C3)}{int_start}:{cl(COL_C3)}{int_end})", num_fmt=NUM_FMT)
    if has_cita:
        _cell(ws, total_int_row, COL_CITA,
              f"=SUM({cl(COL_CITA)}{int_start}:{cl(COL_CITA)}{int_end})", num_fmt=NUM_FMT)

    total_int = _val(c3, "total_interest_fee")
    if total_int > 0:
        _cell(ws, total_int_row, COL_C3, total_int, bold=True, num_fmt=NUM_FMT)
        _cell(ws, total_int_row, COL_REMARKS,
              f"Interest of Rs. {int(total_int):,} levied by AO")
    else:
        _cell(ws, total_int_row, COL_C3,
              f"=SUM({d}{int_start}:{d}{int_end})", bold=True, num_fmt=NUM_FMT)

    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, total_int_row, COL_CITA,
              f"=SUM({e}{int_start}:{e}{int_end})", bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Total Tax Payable ────────────────────────────────────
    ttp_row = cur_row
    data_row(ttp_row, "Total Tax Payable ", None, None, None,
             bold=True,
             formula_b=f"={b}{tax_after_credit_row}+{b}{total_int_row}",
             formula_c=f"={c}{tax_after_credit_row}+{c}{total_int_row}" if has_143_1 else None,
             formula_d=f"={d}{tax_after_credit_row}+{d}{total_int_row}")
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, ttp_row, COL_CITA,
              f"={e}{tax_after_credit_row}+{e}{total_int_row}", bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Taxes Paid ───────────────────────────────────────────
    _cell(ws, cur_row, 1, "Less:", bold=True)
    cur_row += 1

    tax_paid_start = cur_row
    
    # We use hardcoded values here because pre-paid taxes don't use formulas based on income.
    tds_roi = _val(roi, "tds")
    tds_c1 = _val(c1, "tds") if has_143_1 else None
    tds_c3 = _val(c3, "tds")

    data_row(cur_row, "         Tax Deducted at Source",
             roi_val=tds_roi,
             c1_val=tds_c1,
             c3_val=tds_c3,
             cita_val=tds_c3 if has_cita else None)
    cur_row += 1

    data_row(cur_row, "         Tax Collected at Source",
             "tcs", "tcs", "tcs", auto_remark=True)
    if has_cita:
        _cell(ws, cur_row, COL_CITA,
              f"={cl(COL_C3)}{cur_row}", num_fmt=NUM_FMT)
    cur_row += 1

    data_row(cur_row, "         Advance Tax",
             "advance_tax", "advance_tax", "advance_tax")
    if has_cita:
        _cell(ws, cur_row, COL_CITA,
              f"={cl(COL_C3)}{cur_row}", num_fmt=NUM_FMT)
    cur_row += 1

    data_row(cur_row, "         Self Assessment Tax",
             "self_assessment_tax", "self_assessment_tax", "self_assessment_tax")
    if has_cita:
        _cell(ws, cur_row, COL_CITA,
              _val(roi, "self_assessment_tax"), num_fmt=NUM_FMT)
    cur_row += 1

    data_row(cur_row, "         Regular Assessment Tax",
             "regular_tax", "regular_tax", "regular_tax")
    if has_cita:
        cita_rt = _val(cita_data, "regular_tax")
        if cita_rt:
            _cell(ws, cur_row, COL_CITA, cita_rt, num_fmt=NUM_FMT)
        else:
            _cell(ws, cur_row, COL_CITA, f"={cl(COL_C3)}{cur_row}", num_fmt=NUM_FMT)
    tax_paid_end = cur_row
    cur_row += 1

    # Total Taxes Paid
    ttp2_row = cur_row
    data_row(ttp2_row, "Total Taxes Paid", None, None, None,
             bold=True,
             formula_b=f"=SUM({b}{tax_paid_start}:{b}{tax_paid_end})",
             formula_c=f"=SUM({c}{tax_paid_start}:{c}{tax_paid_end})" if has_143_1 else None,
             formula_d=f"=SUM({d}{tax_paid_start}:{d}{tax_paid_end})")
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, ttp2_row, COL_CITA,
              f"=SUM({e}{tax_paid_start}:{e}{tax_paid_end})",
              bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Skip a row
    cur_row += 1

    # ── Net Tax Payable/Refundable ───────────────────────────
    net_row = cur_row
    data_row(net_row, "Net Tax Payable/Refundable", None, None, None,
             bold=True,
             formula_b=f"=ROUND({b}{ttp_row}-SUM({b}{tax_paid_start}:{b}{tax_paid_end}),-1)",
             formula_c=f"=ROUND({c}{ttp_row}-SUM({c}{tax_paid_start}:{c}{tax_paid_end}),-1)" if has_143_1 else None,
             formula_d=f"=ROUND({d}{ttp_row}-SUM({d}{tax_paid_start}:{d}{tax_paid_end}),-1)")
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, net_row, COL_CITA,
              f"=ROUND({e}{ttp_row}-SUM({e}{tax_paid_start}:{e}{tax_paid_end}),-1)",
              bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Interest 244A
    int244a_row = cur_row
    # Interest u/s 244A is granted by the revenue upon processing refunds.
    # ROI: always 0 (taxpayer never claims it).
    # C1: negated — added to Refund.
    # C3: negated — the Payable formula adds 244A to Net, so negative = more refund.
    int244a_roi = 0
    int244a_c1_raw = _val(c1, "interest_244a") if has_143_1 else 0
    int244a_c1 = -abs(int244a_c1_raw) if int244a_c1_raw else 0
    int244a_c3_raw = _val(c3, "interest_244a")
    int244a_c3 = -abs(int244a_c3_raw) if int244a_c3_raw else 0

    data_row(cur_row, "Add: Interest u/s 244A",
             roi_val=int244a_roi,
             c1_val=int244a_c1,
             c3_val=int244a_c3,
             cita_val=int244a_c3 if has_cita else None)
    cur_row += 1

    # Refund Already Issued
    ref_row = cur_row
    _cell(ws, cur_row, 1, "Less: Refund Already Issued")
    _cell(ws, cur_row, COL_ROI, 0, num_fmt=NUM_FMT)
    
    ref_issued_c1_raw = _val(c1, "refund_already_issued") if has_143_1 else 0
    ref_issued_c1 = -abs(ref_issued_c1_raw) if ref_issued_c1_raw else 0
    if has_143_1:
        _cell(ws, cur_row, COL_C1, ref_issued_c1, num_fmt=NUM_FMT)
        
    ref_issued_c3_raw = _val(c3, "refund_already_issued")
    ref_issued_c3 = -abs(ref_issued_c3_raw) if ref_issued_c3_raw else 0
    _cell(ws, cur_row, COL_C3, ref_issued_c3, num_fmt=NUM_FMT)
    
    if abs(ref_issued_c3) > 0:
        _cell(ws, cur_row, COL_REMARKS,
              f"Refund of Rs. {int(abs(ref_issued_c3)):,} already issued and adjusted")
    if has_cita:
        _cell(ws, cur_row, COL_CITA, ref_issued_c3, num_fmt=NUM_FMT)
    cur_row += 1

    # Payable/(Refund)
    pay_row = cur_row
    data_row(pay_row, "Payable /(Refund)", None, None, None,
             bold=True,
             formula_b=f"={b}{net_row}+{b}{int244a_row}-{b}{ref_row}",
             formula_c=f"={c}{net_row}+{c}{int244a_row}-{c}{ref_row}" if has_143_1 else None,
             formula_d=f"={d}{net_row}+{d}{int244a_row}-{d}{ref_row}")
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, pay_row, COL_CITA,
              f"={e}{net_row}+{e}{int244a_row}-{e}{ref_row}",
              bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Refund Adjusted
    refadj_row = cur_row
    _cell(ws, cur_row, 1, "Refund Adjusted")
    _cell(ws, cur_row, COL_ROI, 0, bold=True, num_fmt=NUM_FMT)
    if has_cita:
        _cell(ws, cur_row, COL_CITA, 0, bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Payable/(Refund) - Round off (A)
    final_row = cur_row
    data_row(final_row, "Payable /(Refund) - Round off  (A)", None, None, None,
             bold=True,
             formula_b=f"=ROUND({b}{pay_row}+{b}{refadj_row},-1)",
             formula_c=f"=ROUND({c}{pay_row}+{c}{refadj_row},-1)",
             formula_d=f"=ROUND({d}{pay_row}+{d}{refadj_row},-1)")
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, final_row, COL_CITA,
              f"=ROUND({e}{pay_row}+{e}{refadj_row},-1)",
              bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # ── Calculate Dynamic Rates ───────────────────────────────
    def _calculate_rates(sources):
        """Deduce tax/surcharge/cess rates from extracted data.
        Returns multiple rates as clean floats plus formatted percentage strings.
        """
        n_rate = n_roi_rate = m_rate = -1.0
        s_rate = s_roi_rate = -1.0
        c_rate = c_roi_rate = -1.0
        
        s_on_special = False
        s_roi_on_special = False

        for data in sources:
            if not data:
                continue
            
            is_roi = (data is roi) or (has_143_1 and data is c1)

            # MAT Rate
            if m_rate == -1.0:
                inc_mat = _val(data, "income_115jb")
                tax_mat = _val(data, "tax_115jb")
                if inc_mat and tax_mat:
                    m_rate = tax_mat / inc_mat

            # Surcharge Rate
            surcharge = _val(data, "surcharge_total") or 0
            tax_special = _val(data, "tax_special_rates") or 0
            tax_normal = (_val(data, "tax_normal_rates") or _val(data, "tax_on_total_income") or 0) + tax_special
            tax_115jb = _val(data, "tax_115jb") or 0
            tax_base = max(tax_normal, tax_115jb)
            
            computed_s_rate = -1.0
            is_special_surcharge = False
            
            if surcharge:
                rates_to_try = []
                if tax_special: rates_to_try.append((surcharge / tax_special, True))
                if tax_base: rates_to_try.append((surcharge / tax_base, False))
                if tax_normal: rates_to_try.append((surcharge / tax_normal, False))
                if tax_115jb: rates_to_try.append((surcharge / tax_115jb, False))
                
                # Standard Indian surcharge rates
                standard_rates = [0.02, 0.05, 0.07, 0.10, 0.12, 0.15, 0.25, 0.37]
                best_rate = -1.0
                best_diff = 1.0
                for r, is_spec in rates_to_try:
                    for sr in standard_rates:
                        diff = abs(r - sr)
                        if diff < best_diff and diff < 0.01: # Within 1%
                            best_rate = sr
                            best_diff = diff
                            is_special_surcharge = is_spec
                            
                if best_rate >= 0:
                    computed_s_rate = best_rate
                elif tax_base:
                    # Bound the fallback rate to a maximum of 37% (the highest Indian surcharge)
                    fallback_s_rate = surcharge / tax_base
                    if fallback_s_rate <= 0.40:
                        computed_s_rate = fallback_s_rate
                        is_special_surcharge = False
            else:
                computed_s_rate = 0.0
                is_special_surcharge = False

            if computed_s_rate >= 0:
                if is_roi and s_roi_rate == -1.0:
                    s_roi_rate = computed_s_rate
                    s_roi_on_special = is_special_surcharge
                elif not is_roi and s_rate == -1.0:
                    s_rate = computed_s_rate
                    s_on_special = is_special_surcharge

            # Cess Rate
            cess = _val(data, "cess") or 0
            computed_c_rate = -1.0
            if cess:
                rates_to_try = []
                if tax_base: rates_to_try.append(cess / (tax_base + surcharge))
                if tax_normal: rates_to_try.append(cess / (tax_normal + surcharge))
                if tax_115jb: rates_to_try.append(cess / (tax_115jb + surcharge))
                
                if computed_s_rate >= 0:
                    if tax_base: rates_to_try.append(cess / (tax_base * (1 + computed_s_rate)))
                    if tax_normal: rates_to_try.append(cess / (tax_normal * (1 + computed_s_rate)))
                    if tax_115jb: rates_to_try.append(cess / (tax_115jb * (1 + computed_s_rate)))

                standard_cess = [0.03, 0.04]
                best_c_rate = -1.0
                best_diff = 1.0
                for r in rates_to_try:
                    for sr in standard_cess:
                        diff = abs(r - sr)
                        if diff < best_diff and diff < 0.005: # Within 0.5%
                            best_c_rate = sr
                            best_diff = diff
                            
                if best_c_rate > 0:
                    computed_c_rate = best_c_rate
                elif tax_base:
                    fallback_c_rate = cess / (tax_base + surcharge)
                    # Bound the fallback cess to a maximum of 5% to avoid absurd rates
                    if fallback_c_rate <= 0.05:
                        computed_c_rate = fallback_c_rate
            else:
                computed_c_rate = 0.0

            if computed_c_rate >= 0:
                if is_roi and c_roi_rate == -1.0:
                    c_roi_rate = computed_c_rate
                elif not is_roi and c_rate == -1.0:
                    c_rate = computed_c_rate

            # Normal Rate
            tax_normal_val = _val(data, "tax_normal_rates") or _val(data, "tax_on_total_income") or 0
            inc_normal_raw = data.get("income_normal_rates")

            if inc_normal_raw is not None and inc_normal_raw != 0:
                inc_normal = inc_normal_raw
            else:
                inc_total = _val(data, "total_income") or 0
                inc_special = _val(data, "income_special_rates") or 0
                inc_normal = inc_total - inc_special
                if inc_normal < 0:
                    inc_normal = 0

            computed_rate = -1.0
            if inc_normal > 0 and tax_normal_val >= 0:
                computed_rate = tax_normal_val / inc_normal
                
            if computed_rate >= 0:
                if data is roi:
                    n_roi_rate = computed_rate
                elif n_rate == -1.0:
                    n_rate = computed_rate

        # Fallbacks
        m_rate = m_rate if m_rate >= 0 else 0.185
        s_rate = s_rate if s_rate >= 0 else 0.0
        s_roi_rate = s_roi_rate if s_roi_rate >= 0 else s_rate

        # AY-based cess default: 3% for AY <= 2018-19, 4% for AY >= 2019-20
        default_cess = 0.04
        try:
            ay_str = (comp_data.get("assessment_year") or intim_data.get("assessment_year") or "").strip()
            if ay_str:
                # Extract starting year from formats like "2018-19" or "2018-2019"
                ay_start = int(ay_str.split("-")[0])
                if ay_start <= 2018:
                    default_cess = 0.03
        except (ValueError, IndexError):
            pass

        c_rate = c_rate if c_rate >= 0 else default_cess
        c_roi_rate = c_roi_rate if c_roi_rate >= 0 else c_rate
        n_rate = n_rate if n_rate >= 0 else 0.30
        n_roi_rate = n_roi_rate if n_roi_rate >= 0 else n_rate

        # Round to nearest 0.5%
        def _snap(r):
            pct = r * 100
            snapped = round(pct * 2) / 2
            return snapped / 100

        m_rate = _snap(m_rate)
        s_rate = _snap(s_rate)
        s_roi_rate = _snap(s_roi_rate)
        c_rate = _snap(c_rate)
        c_roi_rate = _snap(c_roi_rate)
        n_rate = _snap(n_rate)
        n_roi_rate = _snap(n_roi_rate)

        def fmt(r):
            v = r * 100
            return f"{v:g}%"

        return (n_rate, n_roi_rate, m_rate, s_rate, s_roi_rate, c_rate, c_roi_rate,
                fmt(n_rate), fmt(n_roi_rate), fmt(m_rate), fmt(s_rate), fmt(s_roi_rate), fmt(c_rate), fmt(c_roi_rate),
                s_on_special, s_roi_on_special)

    (n_val, n_roi_val, m_val, s_val, s_roi_val, c_val, c_roi_val,
     n_str, n_roi_str, m_str, s_str, s_roi_str, c_str, c_roi_str,
     s_on_special, s_roi_on_special) = _calculate_rates([roi, c1, c3])

    # ── Note-1: Calculation of Tax ───────────────────────────
    if progress_cb:
        progress_cb("generating", "Building tax calculation note...", 0.85)

    cur_row += 2  # Leave blank rows

    note_start = cur_row
    _cell(ws, cur_row, 1,
          "Note-1 : Calculation of tax liability as per Normal provisions", bold=True)
    cur_row += 1

    # Note headers
    note_headers = ["Particulars", "As per ROI"]
    if has_143_1:
        note_headers.append("As per 143(1)")
    note_headers.append("As per 143(3)")
    if has_cita:
        note_headers.append("As per CIT(A)\nu/s 250")
    note_headers.append("Corrected\nComputation")
    for i, h in enumerate(note_headers, 1):
        _cell(ws, cur_row, i, h, bold=True)
    cur_row += 1

    # Build column list for Note-1 formulas
    note_cols = [cl(COL_ROI), cl(COL_C3)]
    if has_143_1:
        note_cols.insert(1, cl(COL_C1))
    if has_cita:
        note_cols.append(cl(COL_CITA))
    note_cols.append(cl(COL_CORRECTED))

    # Tax at normal rates
    tax_normal_row = cur_row
    _cell(ws, cur_row, 1, "Tax at normal rates")
    for nc in note_cols:
        col_idx = ord(nc) - 64 if len(nc) == 1 else None
        if col_idx:
            rate_str = n_roi_str if col_idx == COL_ROI else n_str
            _cell(ws, cur_row, col_idx, f"={nc}{normal_inc_row}*{rate_str}", num_fmt=NUM_FMT)
    cur_row += 1

    # Tax at special rates (punched from extracted data)
    tax_special_row = cur_row
    _cell(ws, cur_row, 1, "Tax at special rates")
    roi_tax_special = _val(roi, "tax_special_rates")
    c1_tax_special = _val(c1, "tax_special_rates") if has_143_1 else 0
    c3_tax_special = _val(c3, "tax_special_rates")
    _cell(ws, cur_row, COL_ROI, roi_tax_special, num_fmt=NUM_FMT)
    if has_143_1:
        # If C1 has its own value, use it; otherwise copy from ROI
        _cell(ws, cur_row, COL_C1, c1_tax_special if c1_tax_special else roi_tax_special, num_fmt=NUM_FMT)
    _cell(ws, cur_row, COL_C3, c3_tax_special, num_fmt=NUM_FMT)
    if has_cita:
        _cell(ws, cur_row, COL_CITA, c3_tax_special, num_fmt=NUM_FMT)
    _cell(ws, cur_row, COL_CORRECTED, 0, num_fmt=NUM_FMT)
    cur_row += 1

    # Total Normal Tax
    tax_total_normal_row = cur_row
    _cell(ws, cur_row, 1, "Total Tax as per Normal Provisions")
    for nc in note_cols:
        col_idx = ord(nc) - 64 if len(nc) == 1 else None
        if col_idx:
            _cell(ws, cur_row, col_idx,
                  f"=SUM({nc}{tax_normal_row}:{nc}{tax_special_row})",
                  num_fmt=NUM_FMT)
    cur_row += 1

    # Tax u/s 115JB
    tax_115jb_row = cur_row
    _cell(ws, cur_row, 1, "Tax u/s 115JB (MAT)")
    for nc in note_cols:
        col_idx = ord(nc) - 64 if len(nc) == 1 else None
        if col_idx:
            _cell(ws, cur_row, col_idx, f"={nc}{mat_inc_row}*{m_str}", num_fmt=NUM_FMT)
    cur_row += 1

    # Higher of Normal or 115JB
    tax_higher_row = cur_row
    _cell(ws, cur_row, 1, "Tax (Higher of Normal or 115JB)", bold=True)
    for nc in note_cols:
        col_idx = ord(nc) - 64 if len(nc) == 1 else None
        if col_idx:
            _cell(ws, cur_row, col_idx,
                  f"=MAX({nc}{tax_total_normal_row},{nc}{tax_115jb_row})",
                  bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Surcharge
    surcharge_row = cur_row
    
    if s_str == s_roi_str and s_on_special == s_roi_on_special:
        label_suffix = " (on 115BBE)" if s_on_special else ""
        rate_text = f"{s_str}{label_suffix}"
    else:
        roi_suffix = " (on 115BBE)" if s_roi_on_special else ""
        ao_suffix = " (on 115BBE)" if s_on_special else ""
        rate_text = f"ROI: {s_roi_str}{roi_suffix}, 143(3): {s_str}{ao_suffix}"
        
    _cell(ws, cur_row, 1, f"Surcharge @ {rate_text}")
    for nc in note_cols:
        col_idx = ord(nc) - 64 if len(nc) == 1 else None
        if col_idx:
            is_roi_col = col_idx in [COL_ROI, COL_C1]
            s_rate_str = s_roi_str if is_roi_col else s_str
            is_spec_col = s_roi_on_special if is_roi_col else s_on_special
            
            base_row = tax_special_row if is_spec_col else tax_higher_row
            _cell(ws, cur_row, col_idx,
                  f"={nc}{base_row}*{s_rate_str}", num_fmt=NUM_FMT)
    cur_row += 1

    # Cess
    cess_row = cur_row
    rate_text = f"{c_str}" if c_str == c_roi_str else f"ROI: {c_roi_str}, 143(3): {c_str}"
    _cell(ws, cur_row, 1, f"Cess @ {rate_text}")
    for nc in note_cols:
        col_idx = ord(nc) - 64 if len(nc) == 1 else None
        if col_idx:
            c_rate_str = c_roi_str if col_idx in [COL_ROI, COL_C1] else c_str
            _cell(ws, cur_row, col_idx,
                  f"=({nc}{surcharge_row}+{nc}{tax_higher_row})*{c_rate_str}",
                  num_fmt=NUM_FMT)
    cur_row += 1

    # Grand total
    grand_total_row = cur_row
    _cell(ws, cur_row, 1, "Gross Tax Liability (Total)", bold=True)
    for nc in note_cols:
        col_idx = ord(nc) - 64 if len(nc) == 1 else None
        if col_idx:
            _cell(ws, cur_row, col_idx,
                  f"=+{nc}{surcharge_row}+{nc}{cess_row}+{nc}{tax_higher_row}",
                  bold=True, num_fmt=NUM_FMT)
    cur_row += 1

    # Add extracted Credit u/s 115JAA to Note-1
    note_credit_115_row = cur_row
    _cell(ws, cur_row, 1, "Credit u/s 115JAA of tax paid in earlier years")
    _cell(ws, cur_row, COL_ROI, roi_credit_115, num_fmt=NUM_FMT)
    if has_143_1:
        c1_val = c1_credit_115 if c1_credit_115 else roi_credit_115
        _cell(ws, cur_row, COL_C1, c1_val, num_fmt=NUM_FMT)
    _cell(ws, cur_row, COL_C3, c3_credit_115, num_fmt=NUM_FMT)
    if has_cita:
        _cell(ws, cur_row, COL_CITA, c3_credit_115, num_fmt=NUM_FMT)
    cur_row += 1

    # ── Now fill in the Tax reference row with Note-1 total ──
    _cell(ws, tax_ref_row, COL_ROI,
          f"={b}{grand_total_row}", bold=True, num_fmt=NUM_FMT)
    if has_143_1:
        _cell(ws, tax_ref_row, COL_C1,
              f"={c}{grand_total_row}", bold=True, num_fmt=NUM_FMT)
    _cell(ws, tax_ref_row, COL_C3,
          f"={d}{grand_total_row}", bold=True, num_fmt=NUM_FMT)
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, tax_ref_row, COL_CITA,
              f"={e}{grand_total_row}", bold=True, num_fmt=NUM_FMT)

    # ── Now fill in the Credit 115JAA formulas with Note-1 dependencies ──
    _cell(ws, credit_115_row, COL_ROI, f'=IF({b}{tax_total_normal_row}>{b}{tax_115jb_row}, {b}{note_credit_115_row}, 0)', num_fmt=NUM_FMT)
    if has_143_1:
        _cell(ws, credit_115_row, COL_C1, f'=IF({c}{tax_total_normal_row}>{c}{tax_115jb_row}, {c}{note_credit_115_row}, 0)', num_fmt=NUM_FMT)
    _cell(ws, credit_115_row, COL_C3, f'=IF({d}{tax_total_normal_row}>{d}{tax_115jb_row}, {d}{note_credit_115_row}, 0)', num_fmt=NUM_FMT)
    if has_cita:
        e = cl(COL_CITA)
        _cell(ws, credit_115_row, COL_CITA, f'=IF({e}{tax_total_normal_row}>{e}{tax_115jb_row}, {e}{note_credit_115_row}, 0)', num_fmt=NUM_FMT)
    _cell(ws, credit_115_row, COL_CORRECTED, 0, num_fmt=NUM_FMT)

    # ── Apply number format to all data cells ────────────────
    max_col = len(headers)
    for row in range(8, cur_row + 1):
        for col in range(2, max_col + 1):
            c_cell = ws.cell(row, col)
            if c_cell.value is not None and not c_cell.number_format.startswith("DD"):
                if c_cell.number_format == "General":
                    c_cell.number_format = NUM_FMT
            c_cell.alignment = _align()
            if not c_cell.font.name:
                c_cell.font = _font()

    # ── Save ─────────────────────────────────────────────────
    if progress_cb:
        progress_cb("generating", "Saving Excel file...", 0.95)

    wb.save(output_path)
    logger.info(f"Order Scrutiny Excel saved: {output_path}")
    return output_path
