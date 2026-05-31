"""
Order Scrutiny — Main Service
Orchestrates PDF extraction and Excel generation for the Order Scrutiny module.
Supports proceedings up to CIT(A) order u/s 250.
"""

import os
import logging

from app.services.scrutiny_extract import (
    extract_computation_sheet,
    extract_intimation_order,
    extract_assessment_order,
    extract_cita_order,
)
from app.services.scrutiny_excel import generate_scrutiny_excel

logger = logging.getLogger(__name__)


def run_scrutiny_pipeline(comp_path: str, intim_path: str, intim_password: str,
                          ao_path: str, output_path: str,
                          cita_path: str = None,
                          progress_callback=None):
    """
    Full Order Scrutiny pipeline:
    1. Extract data from Computation Sheet
    2. Extract data from Intimation Order (with password)
    3. Extract data from Assessment Order (required)
    4. Optionally extract data from CIT(A) Order u/s 250
    5. Generate the Order Scrutiny Excel

    Returns the path to the generated Excel file.
    """
    def pcb(stage, detail, pct):
        if progress_callback:
            progress_callback(stage, detail, pct)

    # Step 1: Computation Sheet
    pcb("extracting", "Processing Computation Sheet...", 0.05)
    comp_data = extract_computation_sheet(comp_path, progress_cb=pcb)

    # Step 2: Intimation Order
    pcb("extracting", "Processing Intimation Order...", 0.25)
    intim_data = extract_intimation_order(intim_path, intim_password, progress_cb=pcb)

    # Step 3: Assessment Order (required)
    pcb("extracting", "Processing Assessment Order...", 0.40)
    ao_data = extract_assessment_order(ao_path, progress_cb=pcb)

    # Step 4: CIT(A) Order (optional)
    cita_data = {}
    if cita_path and os.path.exists(cita_path):
        pcb("extracting", "Processing CIT(A) Order u/s 250...", 0.55)
        cita_data = extract_cita_order(cita_path, progress_cb=pcb)

    # Step 5: Generate Excel
    pcb("generating", "Generating Order Scrutiny Excel...", 0.65)
    result = generate_scrutiny_excel(comp_data, intim_data, ao_data, output_path,
                                     cita_data=cita_data, progress_cb=pcb)

    pcb("generating", "Order Scrutiny complete!", 1.0)
    return result
