# ============================================================
# Fruvia AI Backend Dockerfile
# ============================================================
# Multi-stage build for optimized production image.
# Does NOT include raw data, notebooks, or secrets.
# ============================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# ---------- Dependencies ----------
FROM base AS deps

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---------- Application ----------
FROM deps AS app

# Copy application code
COPY backend/app/ /app/app/
COPY configs/ /app/configs/

# Models directory (mount or copy at deploy time)
RUN mkdir -p /app/models/classifier

# Switch to non-root
USER appuser

# Expose port
EXPOSE 8000

# Health check with increased start-period for ML model downloading/loading
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
