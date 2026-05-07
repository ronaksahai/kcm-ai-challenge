"""
KCM AI Suite — Configuration
Loads settings from environment variables (.env file).
"""

import os
from dotenv import load_dotenv

# Load .env file from project root, overriding any stale session variables
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path, override=True)

# ── App Identity ──────────────────────────────────────────────
APP_NAME = "KCM AI Suite"
APP_VERSION = "1.0.0"

# ── Sarvam AI API ────────────────────────────────────────────
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_BASE_URL = "https://api.sarvam.ai"
SARVAM_DOC_INTEL_URL = f"{SARVAM_BASE_URL}/doc-digitization/job/v1"
SARVAM_TRANSLATE_URL = f"{SARVAM_BASE_URL}/translate"

# ── Google Gemini API (Order Scrutiny) ───────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

# ── Sarvam Translate Settings ────────────────────────────────
TRANSLATE_MODEL = "mayura:v1"
TRANSLATE_MODE = "formal"          # formal, modern-colloquial, classic-colloquial
TRANSLATE_CHUNK_LIMIT = 900        # mayura:v1 limit is 1000 chars
TARGET_LANGUAGE = "en-IN"

# ── Supported Source Languages ───────────────────────────────
SUPPORTED_LANGUAGES = {
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "mr-IN": "Marathi",
}

# ── File / Directory Settings ────────────────────────────────
APPDATA_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), APP_NAME)
TEMP_DIR = os.path.join(APPDATA_DIR, "temp")
OUTPUT_DIR = os.path.join(APPDATA_DIR, "output")
MAX_PAGES_PER_JOB = 10         # Sarvam Document Intelligence limit
MAX_FILE_SIZE_MB = 200         # Sarvam upload limit

# Ensure directories exist
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Flask Settings ───────────────────────────────────────────
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5767              # local-only port
UPLOAD_FOLDER = os.path.join(TEMP_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
