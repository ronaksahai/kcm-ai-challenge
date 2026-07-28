# ── Stage 1: Build ────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system-level dependencies required by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create temp directories (Cloud Run filesystem is ephemeral)
RUN mkdir -p /tmp/kcm-ai-suite/temp/uploads /tmp/kcm-ai-suite/output

# Cloud Run injects PORT env var (default 8080)
ENV PORT=8080

# Run with Gunicorn (production WSGI server)
# - 2 workers for handling concurrent requests
# - 120s timeout for long-running AI requests
# - Bind to 0.0.0.0:$PORT as required by Cloud Run
CMD exec gunicorn \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --threads 4 \
    --timeout 300 \
    --graceful-timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    "app.server:app"
