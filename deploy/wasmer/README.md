# Fruvia AI — Wasmer Deployment Guide

Guide to deploying Fruvia AI to Wasmer Edge / Wasmer Cloud.

---

## ⚠️ Important Compatibility Note: PyTorch & WASIX

Fruvia AI relies on `PyTorch` (`torch`), `torchvision`, and `transformers` for on-demand DINOv2 feature extraction. 
Native PyTorch binary dependencies (`.so` / C++ extensions) may exceed execution limits or require full Linux container runtime on Wasmer.

If deploying as a **Full Python Application** on Wasmer Cloud (Linux Container runtime):
Follow **Option A** below.

If deploying to **Wasmer Static Edge** (Static Frontend only while hosting Python ML Backend on a separate Linux GPU/CPU server):
Follow **Option B (Static Fallback)**.

---

## Option A: Full App Deployment (FastAPI + DINOv2 + Qdrant)

Wasmer Cloud dashboard settings:

### Preset & Commands
- **Project Preset**: Python
- **Install Command**: `OFF` (Wasmer automatically reads runtime dependencies from `pyproject.toml`)
- **Build Command**: `OFF`
- **Start Command**: `ON`
  ```bash
  python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
  ```
  *(Note: Run inside `backend/` working directory or pass `PYTHONPATH=.` if executing from root)*

- **Enable Database**: `OFF` (Fruvia AI connects directly to Qdrant Cloud via HTTPS)

### Required Environment Variables (Set in Wasmer UI Dashboard Secrets)

| Variable | Recommended Value | Description |
|---|---|---|
| `APP_ENV` | `production` | Enables production mode |
| `QDRANT_URL` | `https://your-cluster.qdrant.io:6333` | Qdrant Cloud Cluster Endpoint |
| `QDRANT_API_KEY` | `<your-secret-api-key>` | Qdrant Cloud API Key |
| `QDRANT_COLLECTION` | `fruvia_fruits360_original_dinov2_base_v1` | Production Qdrant collection |
| `DINOV2_MODEL_NAME` | `facebook/dinov2-base` | DINOv2 Hugging Face model ID |
| `DINOV2_REVISION` | `main` | Pinned model revision |
| `LOG_LEVEL` | `INFO` | Output log verbosity |
| `MAX_UPLOAD_MB` | `10` | Maximum upload size limit |

---

## Option B: Static Edge Fallback Deployment

If Wasmer environment fails on C-extension PyTorch binaries:

1. Build static assets from `frontend/` into `deploy/wasmer-static/public/`.
2. Set Wasmer UI Preset: **Static Website**.
3. Configure `window.FRUVIA_API_BASE_URL` in `js/config.js` to point to your external FastAPI ML server URL.
