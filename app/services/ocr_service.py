"""
KCM AI Suite — OCR Service
Integrates with Sarvam AI Document Intelligence API to extract text from scanned PDFs.
Uses the async job-based workflow: Create → Upload → Start → Poll → Download.
"""

import os
import time
import logging
import requests

from app.config import (
    SARVAM_API_KEY,
    SARVAM_DOC_INTEL_URL,
    MAX_PAGES_PER_JOB,
)

logger = logging.getLogger(__name__)

# ── Headers ──────────────────────────────────────────────────
def _headers():
    return {"api-subscription-key": SARVAM_API_KEY}


# ── Public API ───────────────────────────────────────────────
def extract_text_from_pdf(pdf_path: str, progress_callback=None) -> str:
    """
    Extract text from a scanned PDF using Sarvam Document Intelligence.
    Handles PDFs > 10 pages by splitting into batches.
    Returns extracted text in Markdown format.
    
    Args:
        pdf_path: Absolute path to the PDF file.
        progress_callback: Optional callable(stage: str, detail: str, pct: float)
    """
    from app.services.pdf_service import split_pdf, get_page_count

    page_count = get_page_count(pdf_path)
    logger.info(f"PDF has {page_count} pages")

    if page_count <= MAX_PAGES_PER_JOB:
        # Single job — process the entire PDF
        if progress_callback:
            progress_callback("extracting", f"Processing {page_count} pages…", 0.1)
        return _process_single_pdf(pdf_path, progress_callback, 0.1, 0.9)
    else:
        # Multi-batch — split and process each batch
        batches = split_pdf(pdf_path, MAX_PAGES_PER_JOB)
        logger.info(f"Split into {len(batches)} batches")
        all_text_parts = []

        for idx, batch_path in enumerate(batches):
            batch_num = idx + 1
            pct_start = 0.1 + (idx / len(batches)) * 0.8
            pct_end = 0.1 + ((idx + 1) / len(batches)) * 0.8

            if progress_callback:
                progress_callback(
                    "extracting",
                    f"Batch {batch_num}/{len(batches)} — extracting text…",
                    pct_start,
                )

            text = _process_single_pdf(batch_path, progress_callback, pct_start, pct_end)
            all_text_parts.append(text)

            # Clean up temp batch file
            try:
                os.remove(batch_path)
            except OSError:
                pass

        return "\n\n".join(all_text_parts)


# ── Private helpers ──────────────────────────────────────────
def _process_single_pdf(pdf_path: str, progress_callback, pct_start, pct_end) -> str:
    """Run the full Sarvam Document Intelligence job workflow for one PDF."""

    filename = os.path.basename(pdf_path)

    # 1. Create job
    logger.info("Creating Document Intelligence job…")
    create_resp = requests.post(
        SARVAM_DOC_INTEL_URL,
        headers=_headers(),
        json={
            "job_parameters": {
                "language": "gu-IN",           # Gujarati documents
                "output_format": "md",         # Markdown preserves structure
            }
        },
        timeout=30,
    )
    create_resp.raise_for_status()
    job_id = create_resp.json()["job_id"]
    logger.info(f"Job created: {job_id}")

    # 2. Get upload URL
    logger.info("Getting upload URL…")
    upload_resp = requests.post(
        f"{SARVAM_DOC_INTEL_URL}/upload-files",
        headers=_headers(),
        json={"job_id": job_id, "files": [filename]},
        timeout=30,
    )
    upload_resp.raise_for_status()
    upload_data = upload_resp.json()

    # Navigate the response to find the presigned URL
    # The API may transform the filename (e.g. Windows short names), so we
    # iterate over all entries rather than doing an exact key lookup.
    upload_urls = upload_data.get("upload_urls", {})
    presigned_url = ""

    for file_key, file_info in upload_urls.items():
        if isinstance(file_info, dict):
            # API uses 'file_url' (not 'url')
            presigned_url = file_info.get("file_url") or file_info.get("url", "")
        elif isinstance(file_info, str):
            presigned_url = file_info
        if presigned_url:
            break

    if not presigned_url:
        raise RuntimeError(f"Could not get upload URL. Response: {upload_data}")

    # 3. Upload the PDF to Azure Blob Storage
    logger.info("Uploading PDF…")
    upload_headers = {
        "x-ms-blob-type": "BlockBlob",
        "Content-Type": "application/pdf",
    }
    with open(pdf_path, "rb") as f:
        put_resp = requests.put(presigned_url, data=f, headers=upload_headers, timeout=120)
    put_resp.raise_for_status()
    logger.info("Upload complete.")

    # 4. Start the job
    logger.info("Starting job…")
    start_resp = requests.post(
        f"{SARVAM_DOC_INTEL_URL}/{job_id}/start",
        headers=_headers(),
        timeout=30,
    )
    start_resp.raise_for_status()

    # 5. Poll for completion
    logger.info("Polling for completion…")
    poll_interval = 3          # seconds
    max_wait = 300             # 5 minutes
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        status_resp = requests.get(
            f"{SARVAM_DOC_INTEL_URL}/{job_id}/status",
            headers=_headers(),
            timeout=30,
        )
        status_resp.raise_for_status()
        state = status_resp.json().get("job_state", "Unknown")
        logger.info(f"  Job state: {state}")

        # Update progress proportionally within our allocated range
        progress_frac = min(elapsed / max_wait, 0.95)
        if progress_callback:
            pct = pct_start + progress_frac * (pct_end - pct_start)
            progress_callback("extracting", f"OCR in progress ({state})…", pct)

        if state in ("Completed", "PartiallyCompleted"):
            break
        elif state == "Failed":
            error_detail = status_resp.json().get("error_message", "Unknown error")
            raise RuntimeError(f"Document Intelligence job failed: {error_detail}")
    else:
        raise TimeoutError(f"Job {job_id} did not complete within {max_wait}s")

    # 6. Download results
    logger.info("Downloading extracted text…")
    download_resp = requests.post(
        f"{SARVAM_DOC_INTEL_URL}/{job_id}/download-files",
        headers=_headers(),
        timeout=30,
    )
    download_resp.raise_for_status()
    download_data = download_resp.json()

    # Fetch the actual markdown content
    extracted_text = _fetch_results(download_data)
    logger.info(f"Extracted {len(extracted_text)} characters of text.")

    if progress_callback:
        progress_callback("extracting", "Text extraction complete.", pct_end)

    return extracted_text


def _fetch_results(download_data: dict) -> str:
    """
    Download the actual extracted content from the presigned result URLs.
    Sarvam delivers results as ZIP files containing .md / .html / .json files.
    If the output is JSON (structured blocks), we extract text from each block.
    """
    import zipfile
    import io

    download_urls = download_data.get("download_urls", {})
    all_text = []

    # Collect all URLs from the response
    urls_to_fetch = []
    if isinstance(download_urls, dict):
        for file_key, file_info in download_urls.items():
            url = ""
            if isinstance(file_info, dict):
                url = file_info.get("file_url") or file_info.get("url", "")
            elif isinstance(file_info, str):
                url = file_info
            if url:
                urls_to_fetch.append((file_key, url))
    elif isinstance(download_urls, list):
        for idx, item in enumerate(download_urls):
            url = ""
            if isinstance(item, dict):
                url = item.get("file_url") or item.get("url", "")
            elif isinstance(item, str):
                url = item
            if url:
                urls_to_fetch.append((f"file_{idx}", url))

    logger.info(f"Fetching {len(urls_to_fetch)} result file(s)")

    for file_key, url in urls_to_fetch:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()

        content_bytes = resp.content

        # Check if the response is a ZIP file (first 2 bytes = PK)
        if content_bytes[:2] == b'PK':
            logger.info(f"  {file_key}: ZIP detected ({len(content_bytes)} bytes)")
            try:
                with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                    names = sorted(zf.namelist())

                    # Prefer .md files, then .json, then .html
                    md_files = [n for n in names if n.lower().endswith('.md') and not n.startswith('__')]
                    json_files = [n for n in names if n.lower().endswith('.json') and not n.startswith('__')]
                    html_files = [n for n in names if n.lower().endswith('.html') and not n.startswith('__')]

                    if md_files:
                        for name in md_files:
                            text = zf.read(name).decode('utf-8', errors='replace')
                            if text.strip():
                                logger.info(f"    MD file: {name} ({len(text)} chars)")
                                all_text.append(text)
                    elif json_files:
                        for name in json_files:
                            raw = zf.read(name).decode('utf-8', errors='replace')
                            logger.info(f"    JSON file: {name}")
                            extracted = _extract_text_from_json(raw)
                            if extracted.strip():
                                all_text.append(extracted)
                    elif html_files:
                        for name in html_files:
                            text = zf.read(name).decode('utf-8', errors='replace')
                            if text.strip():
                                logger.info(f"    HTML file: {name} ({len(text)} chars)")
                                all_text.append(text)
            except zipfile.BadZipFile:
                logger.warning(f"  {file_key}: Bad ZIP, treating as text")
                text = content_bytes.decode('utf-8', errors='replace')
                if text.strip():
                    all_text.append(_try_parse_text(text))
        else:
            text = content_bytes.decode('utf-8', errors='replace')
            if text.strip():
                logger.info(f"  {file_key}: Non-ZIP ({len(text)} chars)")
                all_text.append(_try_parse_text(text))

    if not all_text:
        result = download_data.get("result", "")
        if result:
            return result
        raise RuntimeError(f"No downloadable results found. Response: {download_data}")

    return "\n\n".join(all_text)


def _extract_text_from_json(raw_json: str) -> str:
    """
    Parse Sarvam Document Intelligence JSON and extract text from blocks
    in reading order.
    """
    import json

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        logger.warning("  Could not parse JSON, returning raw text")
        return raw_json

    blocks = data.get("blocks", [])
    if not blocks:
        # Try returning any text field directly
        if isinstance(data, dict):
            for key in ("text", "Text", "content", "markdown"):
                if key in data and isinstance(data[key], str):
                    return data[key]
        return ""

    # Sort by reading_order
    blocks.sort(key=lambda b: b.get("reading_order", 999))

    text_parts = []
    for block in blocks:
        block_text = block.get("text") or block.get("Text", "")
        if not block_text:
            continue

        layout_tag = block.get("layout_tag", "")

        # Skip page numbers
        if layout_tag == "page-number":
            continue

        text_parts.append(block_text.strip())

    return "\n\n".join(text_parts)


def _try_parse_text(text: str) -> str:
    """Try to parse text as JSON blocks, otherwise return as-is."""
    text = text.strip()
    if text.startswith('{'):
        try:
            return _extract_text_from_json(text)
        except Exception:
            pass
    return text
