# Fruvia AI Implementation Plan

## Overview

Fruvia AI is an AI-powered fruit recognition and image retrieval system.
This document tracks the phased implementation plan.

### Notebook Policy

> **Notebooks are authored in the repository and executed on Google Colab.**
> They are never run locally or in CI.

Workflow: GitHub repo → Open in Google Colab → Enable T4 GPU →
Read Kaggle/Qdrant credentials from Colab Secrets →
Download Fruits-360 → Process & embed on Colab →
Upload vectors to Qdrant Cloud → Save checkpoints to Google Drive.

Local tests only validate notebook structure (valid JSON, no outputs,
no secrets, no Windows paths) — they never execute notebook code.

---

## Phase 1: Foundation

**Status: COMPLETE**

- [x] Initialize repository structure
- [x] Create all directories
- [x] Configuration files (classes.yaml, class_mapping.yaml, training.yaml)
- [x] .gitignore, .env.example, pyproject.toml, Makefile
- [x] Backend core modules (config, logging, exceptions)
- [x] Pydantic schemas (classification, retrieval, fruit)
- [x] Image validation utilities
- [x] File utilities (stable UUID, YAML loaders)
- [x] Preprocessing module (reads exported config)
- [x] Dataset audit script (scripts/audit_dataset.py)
- [x] Manifest creation script (scripts/create_manifest.py)
- [x] Manifest validation script (scripts/validate_manifest.py)
- [x] Model export script (scripts/export_model.py)
- [x] FastAPI app stub with health endpoint
- [x] Unit tests for image validation, config, file utils, preprocessing, audit, manifest, exceptions
- [x] Integration test for health endpoint
- [x] Foundation README

---

## Phase 2: Data Exploration & Preparation

**Status: IN PROGRESS**

- [x] Notebook 01: Explore Fruits-360 dataset (Colab)
  - Download via Kaggle API (credentials from Colab Secrets)
  - Count images per class
  - Visualize sample images
  - Distribution chart (matplotlib, not seaborn)
  - Detect corrupt images
  - Export CSV summary
- [x] Notebook 02: Prepare dataset (Colab)
  - Read classes.yaml and class_mapping.yaml
  - Create retrieval_manifest.csv (all images for DINOv2)
  - Create classification_manifest.csv (target classes only)
  - SHA-256 duplicate removal
  - Stratified train/validation/test split (70/15/15, seed=42)
  - Pre/post statistics

---

## Phase 3: Model Training

**Status: NOT STARTED**

- [ ] Notebook 03: EfficientNet-B0 baseline
  - Freeze backbone → fine-tune
  - Early stopping, LR scheduler, mixed precision
  - Save best checkpoint by validation macro-F1
- [ ] Notebook 04: ConvNeXt-Tiny primary model
  - Same training discipline as baseline
  - Gradient clipping, class weights
- [ ] Notebook 05: Model evaluation
  - Test-set-only evaluation
  - Compare EfficientNet-B0 vs ConvNeXt-Tiny
  - Full metrics: accuracy, top-3, precision, recall, macro-F1, confusion matrix
  - Inference timing and model size
  - Export JSON report

---

## Phase 4: DINOv2 Embedding & Qdrant

**Status: IN PROGRESS**

- [x] Notebook 06: Generate DINOv2 embeddings (Colab T4 GPU)
  - facebook/dinov2-base, CLS token, L2 normalize
  - Batch inference with progress bar
  - Save embedding shards to Google Drive (not all in RAM)
  - Checkpoint/resume support
  - Mixed precision
- [x] Notebook 07: Upload to Qdrant Cloud (Colab)
  - Credentials from Colab Secrets (never hardcoded)
  - Stable point IDs (UUID5)
  - Structured payload
  - Batch upload with retry and exponential backoff
  - Resume support (skip already-uploaded points)
  - No recreate_collection by default
  - RESET_COLLECTION flag for intentional reset
  - Verification: count points, sample query

---

## Phase 5: FastAPI Backend

**Status: NOT STARTED**

- [ ] Load classifier at startup
- [ ] Load DINOv2 encoder at startup
- [ ] POST /api/classify with confidence threshold
- [ ] POST /api/retrieve with top_k
- [ ] GET /api/fruits and GET /api/fruits/{class_name}
- [ ] Dependency injection
- [ ] Request ID middleware
- [ ] Qdrant repository with timeout and retry
- [ ] Classification service
- [ ] Retrieval service
- [ ] Full integration tests

---

## Phase 6: Frontend

**Status: NOT STARTED**

- [ ] Home page with navigation
- [ ] Classification page (drag & drop, top-3 results, confidence bars)
- [ ] Retrieval page (drag & drop, top-K grid, similarity scores)
- [ ] Shared CSS (responsive, accessible)
- [ ] JavaScript modules (API client, image preview, error handling)
- [ ] Loading, empty, success, error states

---

## Phase 7: Docker & Final

**Status: NOT STARTED**

- [ ] Dockerfile for backend
- [ ] docker-compose.yml
- [ ] Security review
- [ ] Final test suite run
- [ ] Complete README documentation
- [ ] Clean up any remaining TODOs
