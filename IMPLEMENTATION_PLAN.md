# Fruvia AI Implementation Plan

## Overview

Fruvia AI is an AI-powered fruit recognition and image retrieval system.
This document tracks the phased implementation plan.

---

## Phase 1: Foundation (Current)

**Status: IN PROGRESS**

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

**Status: NOT STARTED**

- [ ] Notebook 01: Explore Fruits-360 dataset
  - Mount Google Drive
  - Count images per class
  - Visualize sample images
  - Distribution chart (matplotlib, not seaborn)
  - Detect corrupt images
- [ ] Notebook 02: Prepare dataset
  - Read classes.yaml and class_mapping.yaml
  - Create manifest CSV
  - Remove duplicates and corrupt images
  - Stratified train/validation/test split
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

**Status: NOT STARTED**

- [ ] Notebook 06: Generate DINOv2 embeddings
  - facebook/dinov2-base, CLS token, L2 normalize
  - Batch inference, skip corrupt images
  - Mixed precision
- [ ] Notebook 07: Upload to Qdrant Cloud
  - Stable point IDs (UUID5)
  - Structured payload
  - No recreate_collection by default
  - RESET_COLLECTION flag for intentional reset

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
