"""
KCM AI Suite — Application Entry Point
Launches the Flask backend server and opens a pywebview native desktop window.
"""

import sys
import os
import logging
import threading
import multiprocessing

# ── Logging Setup ────────────────────────────────────────────
import io

_handler = logging.StreamHandler(
    io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger("KCM-AI-Suite")

# ── Ensure the project root is on sys.path ───────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def start_flask():
    """Start the Flask server in a background thread."""
    from app.server import app
    from app.config import FLASK_HOST, FLASK_PORT

    logger.info(f"Starting Flask server on {FLASK_HOST}:{FLASK_PORT}")
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def main():
    """Main entry point: start Flask, then open the pywebview window."""
    multiprocessing.freeze_support()   # Required for PyInstaller on Windows

    from app.config import FLASK_HOST, FLASK_PORT, APP_NAME

    # Start Flask in a daemon thread
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # Give Flask a moment to start
    import time
    time.sleep(1)

    # Launch the native window
    try:
        import webview

        url = f"http://{FLASK_HOST}:{FLASK_PORT}"
        logger.info(f"Opening {APP_NAME} window -> {url}")

        webview.create_window(
            APP_NAME,
            url=url,
            width=1200,
            height=800,
            min_size=(900, 600),
            resizable=True,
            text_select=True,
        )
        webview.start()

    except ImportError:
        # Fallback: open in default browser if pywebview is not installed
        import webbrowser

        url = f"http://{FLASK_HOST}:{FLASK_PORT}"
        logger.warning("pywebview not installed — opening in browser instead.")
        logger.info(f"App running at: {url}")
        webbrowser.open(url)

        # Keep the main thread alive
        try:
            flask_thread.join()
        except KeyboardInterrupt:
            logger.info("Shutting down…")


if __name__ == "__main__":
    main()
