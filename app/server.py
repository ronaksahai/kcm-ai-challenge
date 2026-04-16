"""
KCM AI Suite — Flask Server
Provides the HTTP API for the desktop application frontend.
Handles file uploads, orchestrates the OCR→Translate→Export pipeline,
and serves the web UI.
"""

import os
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
# Structure: {job_id: {status, stage, detail, progress, error, output_pdf, output_rtf, ...}}
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
            "output_pdf": None,
            "output_rtf": None,
            "extracted_text": None,
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
        "error": job["error"],
        "has_pdf": job["output_pdf"] is not None,
        "has_rtf": job["output_rtf"] is not None,
    })


@app.route("/api/translate/download/<job_id>/<file_format>")
def download_translation(job_id, file_format):
    """Download the translated document as PDF or RTF."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    if job["status"] != "completed":
        return jsonify({"error": "Job is not yet complete."}), 400

    if file_format == "pdf":
        file_path = job.get("output_pdf")
        mimetype = "application/pdf"
    elif file_format == "rtf":
        file_path = job.get("output_rtf")
        mimetype = "application/rtf"
    else:
        return jsonify({"error": "Invalid format. Use 'pdf' or 'rtf'."}), 400

    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": f"{file_format.upper()} file not found."}), 404

    original_name = job.get("original_filename", "document")
    base_name = os.path.splitext(original_name)[0]
    download_name = f"{base_name}_translated.{file_format}"

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


@app.route("/api/translate/preview/<job_id>")
def preview_translation(job_id):
    """Get the translated text for preview."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    return jsonify({
        "translated_text": job.get("translated_text", ""),
        "extracted_text": job.get("extracted_text", ""),
    })


# ── Pipeline Execution ───────────────────────────────────────

def _run_pipeline(job_id: str):
    """Execute the full OCR → Translate → Export pipeline in a background thread."""
    try:
        job = _jobs[job_id]
        upload_path = job["upload_path"]
        original_filename = job["original_filename"]
        base_name = os.path.splitext(original_filename)[0]

        # ── Stage 1: OCR (Extract text) ──────────────────────
        _update_job(job_id, stage="extracting", detail="Extracting text from document…", progress=0.05)

        from app.services.ocr_service import extract_text_from_pdf
        extracted_text = extract_text_from_pdf(
            upload_path,
            progress_callback=lambda stage, detail, pct: _update_job(
                job_id, stage=stage, detail=detail, progress=pct * 0.4  # 0-40%
            ),
        )

        _update_job(job_id, stage="extracting", detail="Text extraction complete.", progress=0.40)
        with _jobs_lock:
            _jobs[job_id]["extracted_text"] = extracted_text

        if not extracted_text.strip():
            raise ValueError("No text could be extracted from the document. "
                           "Please ensure the PDF contains readable text or scanned images.")

        # ── Stage 2: Translate ───────────────────────────────
        _update_job(job_id, stage="translating", detail="Translating to English…", progress=0.42)

        from app.services.translate_service import translate_markdown
        translated_text = translate_markdown(
            extracted_text,
            progress_callback=lambda stage, detail, pct: _update_job(
                job_id, stage=stage, detail=detail, progress=0.42 + pct * 0.38  # 42-80%
            ),
        )

        _update_job(job_id, stage="translating", detail="Translation complete.", progress=0.80)
        with _jobs_lock:
            _jobs[job_id]["translated_text"] = translated_text

        # ── Stage 3: Generate output files ───────────────────
        _update_job(job_id, stage="generating", detail="Generating PDF…", progress=0.82)

        from app.services.pdf_service import generate_pdf
        from app.services.rtf_service import generate_rtf

        # Generate PDF
        pdf_path = os.path.join(OUTPUT_DIR, f"{job_id}_{base_name}_translated.pdf")
        generate_pdf(translated_text, pdf_path, original_filename)
        with _jobs_lock:
            _jobs[job_id]["output_pdf"] = pdf_path

        _update_job(job_id, stage="generating", detail="Generating RTF…", progress=0.90)

        # Generate RTF
        rtf_path = os.path.join(OUTPUT_DIR, f"{job_id}_{base_name}_translated.rtf")
        generate_rtf(translated_text, rtf_path, original_filename)
        with _jobs_lock:
            _jobs[job_id]["output_rtf"] = rtf_path

        # ── Done ─────────────────────────────────────────────
        _update_job(job_id, status="completed", stage="completed",
                    detail="Translation complete! Your documents are ready for download.",
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
