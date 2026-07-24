"""
KCM AI Suite — Flask Server
Provides the HTTP API for the desktop application frontend.
Handles file uploads, orchestrates the OCR→Translate→Export pipeline,
and serves the web UI.
"""

import os
import json
import uuid
import logging
import threading
import traceback
from datetime import datetime

from flask import (
    Flask,
    request,
    jsonify,
    send_file,
    render_template,
)

from app.config import (
    SARVAM_API_KEY,
    GCP_PROJECT_ID,
    UPLOAD_FOLDER,
    OUTPUT_DIR,
    TEMP_DIR,
    APP_NAME,
    APP_VERSION,
    MAX_FILE_SIZE_MB,
)

logger = logging.getLogger(__name__)

# ── Flask App ────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024

# ── Job Tracking ─────────────────────────────────────────────
# In-memory store for translation jobs.
# Structure: {job_id: {status, stage, detail, progress, error, output_rtf, ...}}
_jobs = {}
_jobs_lock = threading.Lock()


# ── Routes: UI ───────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main UI page."""
    return render_template("index.html", app_name=APP_NAME, app_version=APP_VERSION)


# ── Routes: Health & Config ──────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "app": APP_NAME, "version": APP_VERSION})


@app.route("/api/config/status")
def config_status():
    """Check if the API key is configured."""
    has_key = bool(SARVAM_API_KEY and SARVAM_API_KEY != "your_sarvam_api_key_here")
    return jsonify({"configured": has_key})


# ── Routes: Translation Pipeline ─────────────────────────────

@app.route("/api/translate", methods=["POST"])
def start_translation():
    """
    Upload a PDF and start the translation pipeline.
    Returns a job_id that can be polled for progress.
    """
    # Validate API key
    if not SARVAM_API_KEY or SARVAM_API_KEY == "your_sarvam_api_key_here":
        return jsonify({"error": "Sarvam API key is not configured. "
                        "Please set SARVAM_API_KEY in the .env file."}), 400

    # Validate file
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported."}), 400

    # Save uploaded file
    job_id = str(uuid.uuid4())
    original_filename = file.filename
    safe_filename = f"{job_id}_{original_filename}"
    upload_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(upload_path)

    logger.info(f"File uploaded: {original_filename} → {upload_path}")

    # Initialize job
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "processing",
            "stage": "uploading",
            "detail": "File received, starting processing…",
            "progress": 0.0,
            "error": None,
            "original_filename": original_filename,
            "upload_path": upload_path,

            "translated_text": None,
            "started_at": datetime.now().isoformat(),
        }

    # Run pipeline in background thread
    thread = threading.Thread(
        target=_run_pipeline,
        args=(job_id,),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id, "status": "processing"})


@app.route("/api/translate/status/<job_id>")
def translation_status(job_id):
    """Poll the status of a translation job."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "stage": job["stage"],
        "detail": job["detail"],
        "progress": round(job["progress"] * 100, 1),
    })


@app.route("/api/translate/preview/<job_id>")
def preview_translation(job_id):
    """Get the translated text for preview."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    return jsonify({
        "translated_text": job.get("translated_text", ""),
    })


# ── Pipeline Execution ───────────────────────────────────────

def _run_pipeline(job_id: str):
    """Execute the Gemini Translate → Export pipeline in a background thread."""
    try:
        job = _jobs[job_id]
        upload_path = job["upload_path"]
        original_filename = job["original_filename"]
        base_name = os.path.splitext(original_filename)[0]

        # ── Stage 1: Translate (Gemini reads PDF + translates) ─
        _update_job(job_id, stage="translating", detail="Sending document to Gemini…", progress=0.05)

        from app.services.translate_service import translate_pdf
        translated_text = translate_pdf(
            upload_path,
            progress_callback=lambda stage, detail, pct: _update_job(
                job_id, stage=stage, detail=detail, progress=0.05 + pct * 0.75  # 5-80%
            ),
        )

        _update_job(job_id, stage="translating", detail="Translation complete.", progress=0.80)
        with _jobs_lock:
            _jobs[job_id]["translated_text"] = translated_text

        # ── Done ─────────────────────────────────────────────
        _update_job(job_id, status="completed", stage="completed",
                    detail="Translation complete! You can now preview and print your document.",
                    progress=1.0)

        logger.info(f"Job {job_id} completed successfully.")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed: {error_msg}\n{traceback.format_exc()}")
        _update_job(
            job_id,
            status="failed",
            stage="error",
            detail=f"An error occurred: {error_msg}",
            progress=0.0,
            error=error_msg,
        )

    finally:
        # Clean up uploaded file
        try:
            upload_path = _jobs.get(job_id, {}).get("upload_path")
            if upload_path and os.path.exists(upload_path):
                os.remove(upload_path)
        except OSError:
            pass


def _update_job(job_id: str, **kwargs):
    """Thread-safe job status update."""
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


# ── Routes: Order Scrutiny ───────────────────────────────────

@app.route("/api/scrutiny/config")
def scrutiny_config():
    """Check if GCP Project ID is configured for Order Scrutiny."""
    has_key = bool(GCP_PROJECT_ID and GCP_PROJECT_ID != "your_gcp_project_id_here")
    return jsonify({"configured": has_key})


@app.route("/api/scrutiny/classify", methods=["POST"])
def classify_scrutiny_files():
    """
    Classify uploaded PDFs into document types.
    Accepts multipart form with files named 'files'.
    Returns JSON array of classification results.
    """
    if not GCP_PROJECT_ID or GCP_PROJECT_ID == "your_gcp_project_id_here":
        return jsonify({"error": "GCP Project ID is not configured."}), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded."}), 400

    # Save files temporarily and classify
    classify_id = str(uuid.uuid4())[:8]
    file_paths = []
    for i, f in enumerate(files):
        if f.filename and f.filename.lower().endswith(".pdf"):
            saved_path = os.path.join(UPLOAD_FOLDER, f"{classify_id}_{i}_{f.filename}")
            f.save(saved_path)
            file_paths.append((f.filename, saved_path))

    if not file_paths:
        return jsonify({"error": "No valid PDF files found."}), 400

    from app.services.scrutiny_classify import classify_files
    results = classify_files(file_paths)

    # Return results (keep saved_path for later use by bulk submit)
    return jsonify({
        "classify_id": classify_id,
        "files": [{
            "filename": r["filename"],
            "saved_path": r["saved_path"],
            "type": r["type"],
            "label": r["label"],
            "confidence": r["confidence"],
            "date": r.get("date"),
            "method": r["method"],
        } for r in results]
    })


@app.route("/api/scrutiny", methods=["POST"])
def start_scrutiny():
    """
    Upload PDFs and start the Order Scrutiny pipeline.

    Supports two modes:
    1. Individual mode (original): separate fields for each document type
    2. Bulk mode: files already saved by /api/scrutiny/classify,
       submitted with type assignments as JSON
    """
    if not GCP_PROJECT_ID or GCP_PROJECT_ID == "your_gcp_project_id_here":
        return jsonify({"error": "GCP Project ID is not configured. "
                        "Please set GCP_PROJECT_ID in the .env file."}), 400

    mode = request.form.get("mode", "individual")

    if mode == "bulk":
        # Bulk mode: files are pre-saved, assignments come as JSON
        assignments_json = request.form.get("assignments", "[]")
        try:
            assignments = json.loads(assignments_json)
        except (json.JSONDecodeError, TypeError):
            return jsonify({"error": "Invalid assignments data."}), 400

        intim_password = request.form.get("intimation_password", "").strip()

        # Map assignments to paths
        comp_path = None
        intim_path = None
        ao_path = None
        cita_path = None
        cita_comp_path = None

        job_id = str(uuid.uuid4())

        for a in assignments:
            src = a.get("saved_path")
            doc_type = a.get("type")
            if not src or not doc_type or not os.path.exists(src):
                continue

            # Move file to job-specific name
            if doc_type == "computation_sheet":
                comp_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_comp.pdf")
                os.rename(src, comp_path)
            elif doc_type == "intimation_order":
                intim_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_intim.pdf")
                os.rename(src, intim_path)
            elif doc_type == "assessment_order":
                ao_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_ao.pdf")
                os.rename(src, ao_path)
            elif doc_type == "cita_order":
                cita_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_cita.pdf")
                os.rename(src, cita_path)
            elif doc_type == "cita_comp_sheet":
                cita_comp_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_cita_comp.pdf")
                os.rename(src, cita_comp_path)

        # Validate required files
        if not comp_path:
            return jsonify({"error": "Computation Sheet is required."}), 400
        if not intim_path:
            return jsonify({"error": "Intimation Order / ITR is required."}), 400
        if not ao_path:
            return jsonify({"error": "Assessment Order is required."}), 400

        logger.info(f"Scrutiny bulk upload: comp={bool(comp_path)}, "
                    f"intim={bool(intim_path)}, ao={bool(ao_path)}, "
                    f"cita={bool(cita_path)}, cita_comp={bool(cita_comp_path)}")

    else:
        # Individual mode (original flow)
        # Validate computation sheet
        if "computation_sheet" not in request.files:
            return jsonify({"error": "Computation Sheet PDF is required."}), 400
        comp_file = request.files["computation_sheet"]
        if not comp_file.filename or not comp_file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Computation Sheet must be a PDF file."}), 400

        # Validate intimation order
        if "intimation_order" not in request.files:
            return jsonify({"error": "Intimation Order PDF is required."}), 400
        intim_file = request.files["intimation_order"]
        if not intim_file.filename or not intim_file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Intimation Order must be a PDF file."}), 400

        # Validate password
        intim_password = request.form.get("intimation_password", "").strip()

        # Validate assessment order (required)
        if "assessment_order" not in request.files:
            return jsonify({"error": "Assessment Order PDF is required."}), 400
        ao_file = request.files["assessment_order"]
        if not ao_file.filename or not ao_file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Assessment Order must be a PDF file."}), 400

        # Optional CIT(A) order
        cita_file = request.files.get("cita_order")

        # Optional CIT(A) computation sheet
        cita_comp_file = request.files.get("cita_comp_sheet")

        # Save files
        job_id = str(uuid.uuid4())

        comp_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_comp.pdf")
        comp_file.save(comp_path)

        intim_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_intim.pdf")
        intim_file.save(intim_path)

        ao_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_ao.pdf")
        ao_file.save(ao_path)

        cita_path = None
        if cita_file and cita_file.filename and cita_file.filename.lower().endswith(".pdf"):
            cita_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_cita.pdf")
            cita_file.save(cita_path)

        cita_comp_path = None
        if cita_comp_file and cita_comp_file.filename and cita_comp_file.filename.lower().endswith(".pdf"):
            cita_comp_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_cita_comp.pdf")
            cita_comp_file.save(cita_comp_path)

        logger.info(f"Scrutiny files uploaded: comp={comp_file.filename}, "
                    f"intim={intim_file.filename}, ao={ao_file.filename}, "
                    f"cita={cita_file.filename if cita_file else 'N/A'}, "
                    f"cita_comp={cita_comp_file.filename if cita_comp_file else 'N/A'}")

    # Initialize job
    with _jobs_lock:
        _jobs[job_id] = {
            "type": "scrutiny",
            "status": "processing",
            "stage": "uploading",
            "detail": "Files received, starting processing…",
            "progress": 0.0,
            "error": None,
            "comp_path": comp_path,
            "intim_path": intim_path,
            "intim_password": intim_password,
            "ao_path": ao_path,
            "cita_path": cita_path,
            "cita_comp_path": cita_comp_path,
            "output_excel": None,
            "started_at": datetime.now().isoformat(),
        }

    thread = threading.Thread(target=_run_scrutiny, args=(job_id,), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "status": "processing"})


@app.route("/api/scrutiny/status/<job_id>")
def scrutiny_status(job_id):
    """Poll scrutiny job status."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "stage": job["stage"],
        "detail": job["detail"],
        "progress": round(job["progress"] * 100, 1),
        "error": job["error"],
        "has_excel": job.get("output_excel") is not None,
    })


@app.route("/api/scrutiny/download/<job_id>")
def download_scrutiny(job_id):
    """Download the generated Order Scrutiny Excel."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job["status"] != "completed":
        return jsonify({"error": "Job is not yet complete."}), 400

    file_path = job.get("output_excel")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Excel file not found."}), 404

    download_name = f"Order_Scrutiny_{job_id[:8]}.xlsx"

    _open_file_natively(file_path)

    response = send_file(
        file_path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=download_name,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


def _run_scrutiny(job_id: str):
    """Execute the Order Scrutiny pipeline in a background thread."""
    try:
        job = _jobs[job_id]
        comp_path = job["comp_path"]
        intim_path = job["intim_path"]
        intim_password = job["intim_password"]
        ao_path = job["ao_path"]
        cita_path = job.get("cita_path")
        cita_comp_path = job.get("cita_comp_path")

        output_path = os.path.join(OUTPUT_DIR, f"{job_id}_order_scrutiny.xlsx")

        from app.services.scrutiny_service import run_scrutiny_pipeline
        run_scrutiny_pipeline(
            comp_path=comp_path,
            intim_path=intim_path,
            intim_password=intim_password,
            ao_path=ao_path,
            output_path=output_path,
            cita_path=cita_path,
            cita_comp_path=cita_comp_path,
            progress_callback=lambda stage, detail, pct: _update_job(
                job_id, stage=stage, detail=detail, progress=pct
            ),
        )

        with _jobs_lock:
            _jobs[job_id]["output_excel"] = output_path

        _update_job(job_id, status="completed", stage="completed",
                    detail="Order Scrutiny complete! Your Excel is ready.",
                    progress=1.0)
        logger.info(f"Scrutiny job {job_id} completed.")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Scrutiny job {job_id} failed: {error_msg}\n{traceback.format_exc()}")
        _update_job(job_id, status="failed", stage="error",
                    detail=f"Error: {error_msg}", progress=0.0, error=error_msg)

    finally:
        # Clean up uploaded files
        for key in ("comp_path", "intim_path", "ao_path", "cita_path"):
            try:
                path = _jobs.get(job_id, {}).get(key)
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass


# ── Routes: Notice Reply ─────────────────────────────────────

@app.route("/api/notice-reply/config")
def notice_reply_config():
    """Check if GCP Project ID is configured for Notice Reply."""
    has_key = bool(GCP_PROJECT_ID and GCP_PROJECT_ID != "your_gcp_project_id_here")
    return jsonify({"configured": has_key})


@app.route("/api/notice-reply", methods=["POST"])
def start_notice_reply():
    """
    Upload a notice PDF and start the Notice Reply pipeline.
    Expects multipart form with:
    - notice_pdf (required PDF)
    """
    if not GCP_PROJECT_ID or GCP_PROJECT_ID == "your_gcp_project_id_here":
        return jsonify({"error": "GCP Project ID is not configured. "
                        "Please set GCP_PROJECT_ID in the .env file."}), 400

    # Validate file
    if "notice_pdf" not in request.files:
        return jsonify({"error": "No notice PDF uploaded."}), 400

    file = request.files["notice_pdf"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported."}), 400

    # Save uploaded file
    job_id = str(uuid.uuid4())
    original_filename = file.filename
    safe_filename = f"{job_id}_notice.pdf"
    upload_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(upload_path)

    logger.info(f"Notice uploaded: {original_filename} → {upload_path}")

    # Initialize job
    with _jobs_lock:
        _jobs[job_id] = {
            "type": "notice_reply",
            "status": "processing",
            "stage": "uploading",
            "detail": "File received, starting processing…",
            "progress": 0.0,
            "error": None,
            "original_filename": original_filename,
            "upload_path": upload_path,
            "output_docx": None,
            "output_xlsx": None,
            "email_text": None,
            "started_at": datetime.now().isoformat(),
        }

    thread = threading.Thread(target=_run_notice_reply, args=(job_id,), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "status": "processing"})


@app.route("/api/notice-reply/status/<job_id>")
def notice_reply_status(job_id):
    """Poll notice reply job status."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "stage": job["stage"],
        "detail": job["detail"],
        "progress": round(job["progress"] * 100, 1),
        "error": job["error"],
        "has_docx": job.get("output_docx") is not None,
        "has_xlsx": job.get("output_xlsx") is not None,
        "has_email": job.get("email_text") is not None,
    })


@app.route("/api/notice-reply/download/<job_id>/<file_format>")
def download_notice_reply(job_id, file_format):
    """Download the generated Notice Reply files (docx or xlsx)."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job["status"] != "completed":
        return jsonify({"error": "Job is not yet complete."}), 400

    original_name = job.get("original_filename", "notice")
    base_name = os.path.splitext(original_name)[0]

    if file_format == "docx":
        file_path = job.get("output_docx")
        mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        download_name = f"Reply_{base_name}.docx"
    elif file_format == "xlsx":
        file_path = job.get("output_xlsx")
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        download_name = f"Details_Required_{base_name}.xlsx"
    else:
        return jsonify({"error": "Invalid format. Use 'docx' or 'xlsx'."}), 400

    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": f"{file_format.upper()} file not found."}), 404

    _open_file_natively(file_path)

    response = send_file(
        file_path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=download_name,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/notice-reply/email/<job_id>")
def notice_reply_email(job_id):
    """Get the client email message text."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job["status"] != "completed":
        return jsonify({"error": "Job is not yet complete."}), 400

    return jsonify({"email_text": job.get("email_text", "")})


def _run_notice_reply(job_id: str):
    """Execute the Notice Reply pipeline in a background thread."""
    try:
        job = _jobs[job_id]
        upload_path = job["upload_path"]

        output_docx = os.path.join(OUTPUT_DIR, f"{job_id}_reply.docx")
        output_xlsx = os.path.join(OUTPUT_DIR, f"{job_id}_details.xlsx")

        from app.services.notice_service import run_notice_reply_pipeline
        result = run_notice_reply_pipeline(
            pdf_path=upload_path,
            output_docx_path=output_docx,
            output_xlsx_path=output_xlsx,
            progress_callback=lambda stage, detail, pct: _update_job(
                job_id, stage=stage, detail=detail, progress=pct
            ),
        )

        with _jobs_lock:
            _jobs[job_id]["output_docx"] = result["docx_path"]
            _jobs[job_id]["output_xlsx"] = result["xlsx_path"]
            _jobs[job_id]["email_text"] = result["email_text"]

        _update_job(job_id, status="completed", stage="completed",
                    detail="Notice Reply complete! Your files are ready.",
                    progress=1.0)
        logger.info(f"Notice Reply job {job_id} completed.")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Notice Reply job {job_id} failed: {error_msg}\n{traceback.format_exc()}")
        _update_job(job_id, status="failed", stage="error",
                    detail=f"Error: {error_msg}", progress=0.0, error=error_msg)

    finally:
        # Clean up uploaded file
        try:
            path = _jobs.get(job_id, {}).get("upload_path")
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


# ═════════════════════════════════════════════════════════════
#  CASE LAW / PRECEDENT FINDER
# ═════════════════════════════════════════════════════════════

CASELAW_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".jpg", ".jpeg", ".png"}

@app.route("/api/caselaw/search", methods=["POST"])
def caselaw_search():
    """
    Synchronous endpoint — accepts a scenario description + optional file attachments.
    Uses Gemini for discovery + Claude Fable 5 for deep analysis.
    """
    # Support both JSON and multipart/form-data
    if request.content_type and "multipart/form-data" in request.content_type:
        scenario = (request.form.get("query") or "").strip()
        court_filter = (request.form.get("court_filter") or "all").strip()
        uploaded_files = request.files.getlist("files")
    else:
        data = request.get_json(silent=True) or {}
        scenario = (data.get("query") or "").strip()
        court_filter = (data.get("court_filter") or "all").strip()
        uploaded_files = []

    if not scenario:
        return jsonify({"error": "Please describe your tax scenario."}), 400

    if len(scenario) < 15:
        return jsonify({"error": "Please provide a more detailed scenario description."}), 400

    # Extract text from uploaded files
    context_texts = []
    saved_paths = []
    try:
        from app.services.caselaw_service import search_precedents, extract_file_text

        for f in uploaded_files:
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext not in CASELAW_ALLOWED_EXTENSIONS:
                    continue
                save_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}{ext}")
                f.save(save_path)
                saved_paths.append(save_path)
                text = extract_file_text(save_path)
                if text:
                    context_texts.append(f"--- From: {f.filename} ---\n{text}")

        context_text = "\n\n".join(context_texts) if context_texts else ""

        result = search_precedents(scenario, court_filter, context_text)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Case law search failed: {e}\n{traceback.format_exc()}")
        return jsonify({"error": f"Search failed: {str(e)}"}), 500

    finally:
        # Clean up uploaded files
        for p in saved_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

