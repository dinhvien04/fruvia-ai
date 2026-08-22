# Fruvia AI

AI-powered multi-dataset fruit recognition, taxonomy resolution, and visual image retrieval system using DINOv2 deep learning embeddings and Qdrant Cloud.

---

## 🌟 Feature Overview & Status

| Capability | Status | Details |
|---|---|---|
| **DINOv2 Feature Extractor** | ✅ Implemented | `facebook/dinov2-base`, CLS token, 768-dim L2-normalized vectors |
| **Qdrant Vector Database** | ✅ Implemented | Cosine similarity vector search over ~328,190 gallery images |
| **Cloudflare R2 Storage** | ✅ Implemented | High-performance WebP thumbnail storage and public CDN links |
| **Multi-Dataset Support** | ✅ Implemented | Supports Fruits-360 Original & Fruits-262 datasets concurrently |
| **Taxonomy & Translation** | ✅ Implemented | 410 raw dataset classes normalized to canonical species with Vietnamese + English display names |
| **Dual Search Modes** | ✅ Implemented | `mode=image` (Top-K images) & `mode=class` (Top-K deduplicated species with hit count) |
| **Category Filtering** | ✅ Implemented | Filter retrieval by `fruit`, `vegetable`, `nut`, `seed`, or `all` |
| **Fruvia Web V2 (Frontend)** | ✅ Implemented | Mobile-first visual search UX, Hero Search Widget, PWA/Offline support, Explore taxonomy browser & Search History |
| **Fruit Classifier (ConvNeXt)** | 🔄 Planned / In Progress | Model training scripts present in notebooks; classification API in progress |

---

## 📱 Fruvia Web V2 Frontend Architecture

The Fruvia Web V2 frontend is a competition-quality visual search web application built with vanilla HTML5, modern modular CSS (Design Tokens), and vanilla ES6 JavaScript modules:

- **Hero Search Widget (`/`)**: Directly select or drop an image on the homepage to start searching. Seamless client-side state transfer to `/search`.
- **Mobile-First Touch & Camera Support**: Dedicated camera input trigger (`capture="environment"`) and gallery selection touch buttons (≥44px target sizes).
- **Mobile Bottom Navigation Bar**: Fixed bottom navigation bar for mobile viewports (`Trang chủ`, `Tìm kiếm`, `Khám phá`) respecting iOS `safe-area-inset-bottom`.
- **Collapsible Search Controls**: Technical controls (search mode, category filter, Top-K slider) collapsed under an intuitive "Tùy chọn tìm kiếm" accordion.
- **Visual Comparison (Query vs Top Match)**: Side-by-side thumbnail comparison with clear non-jargon labels ("Ảnh của bạn" vs "Kết quả gần nhất #1").
- **Client-Only Recent History**: `localStorage`-based search history capped at 10 items with thumbnail previews, relative timestamps, and one-tap restore/clear.
- **Taxonomy Explorer (`/explore`)**: Browse ground-truth canonical species from `configs/taxonomy.yaml` with search & category filters.
- **PWA & Offline Capability**: Web App Manifest (`manifest.webmanifest`), Service Worker (`service-worker.js`), and offline fallback UI (`offline.html`).

---

## 📊 Datasets & Gallery Index

Fruvia AI indexes multiple datasets within a unified 768-dimensional embedding space:

- **Fruits-360 Original Size**: ~102,551 images across 131 original classes
- **Fruits-262**: 225,639 images across 262 classes (100% embedded, 0 errors)
- **Total Gallery Size**: **~328,190 indexed vectors** across 410 raw dataset labels

> **Note on Taxonomy**: 410 raw dataset labels (e.g., `Apple Red 1`, `apple_red_2`, `Pear 10`) do **not** represent 410 distinct biological species. Fruvia AI's taxonomy layer normalizes these into canonical species (e.g., `apple`, `pear`, `durian`, `dragon_fruit`) with human-friendly English and Vietnamese names.

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────┐
│               Fruvia Web V2 Frontend                    │
│     index.html (Home) │ retrieval.html (/search)        │
│     explore.html (/explore) │ species.html              │
│    Modular JS │ PWA SW │ Mobile Bottom Nav │ SVG Assets   │
└────────────────────────────┬────────────────────────────┘
                             │ HTTP Multipart (POST /api/retrieve)
┌────────────────────────────▼────────────────────────────┐
│                    FastAPI Backend                      │
│  ┌───────────────────────┐   ┌───────────────────────┐  │
│  │   RequestIdMiddleware │   │  RateLimitMiddleware  │  │
│  └───────────────────────┘   └───────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │   Bounded Upload Reader & Pixel Guard (25M px)    │  │
│  └───────────────────────────┬───────────────────────┘  │
│                              │ Threadpool Offloading    │
│  ┌───────────────────────────▼───────────────────────┐  │
│  │       DINOv2 Base Image Encoder (PyTorch)          │  │
│  │         768-dim L2-Normalized Vector              │  │
│  └───────────────────────────┬───────────────────────┘  │
│                              │ Cosine Similarity Query  │
│  ┌───────────────────────────▼───────────────────────┐  │
│  │   QdrantRepository + Taxonomy Layer               │  │
│  │   configs/taxonomy.yaml (EN/VI names + Category)  │  │
│  └───────────────────────────┬───────────────────────┘  │
└──────────────────────────────┼──────────────────────────┘
                               │ HTTPS API
                     ┌─────────▼─────────┐
                     │   Qdrant Cloud    │
                     │  (~328k Vectors)  │
                     └─────────┬─────────┘
                               │ Thumbnail Key
                     ┌─────────▼─────────┐
                     │   Cloudflare R2   │
                     │  (WebP CDN Images)│
                     └───────────────────┘
```

---

## 🔍 Search Modes & API Contract

### `POST /api/retrieve`

Send a `multipart/form-data` request with an image file.

#### Parameters

- `file` (UploadFile, required): Image file (JPG, PNG, WEBP, max 10 MB).
- `top_k` (int, optional, default: 5): Number of items to return (1 to 20).
- `mode` (str, optional, default: `"image"`):
  - `"image"`: Returns Top-K nearest individual gallery images.
  - `"class"`: Groups results by canonical species class, returning Top-K distinct species sorted by best similarity.
- `category` (str, optional, default: `"all"`): Filter results by category: `"fruit"`, `"vegetable"`, `"nut"`, `"seed"`, or `"all"`.

#### Example Response Body

```json
{
  "query": {
    "filename": "query_durian.jpg"
  },
  "mode": "class",
  "category": "fruit",
  "results": [
    {
      "original_class": "durian",
      "canonical_class": "durian",
      "display_name": "Durian",
      "display_name_vi": "Sầu riêng",
      "category": "fruit",
      "dataset_name": "fruits262_full_original_v7",
      "dataset_version": "7",
      "filename": "durian_001.jpg",
      "relative_path": "gallery/durian/durian_001.jpg",
      "original_split": "gallery",
      "similarity": 0.8432,
      "image_url": "https://pub-r2.fruvia.ai/thumbnails/durian_001.webp",
      "hit_count": 8
    }
  ],
  "result_count": 1,
  "processing_time_ms": 112.4
}
```

---

## 📁 Repository Structure

```
fruvia-ai/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, static mounts & clean URL routes
│   │   ├── api/                    # Route handlers (/health, /ready, /live, /species, /retrieve)
│   │   ├── core/                   # Config, rate limiting, logging, exceptions
│   │   ├── ml/                     # DINOv2 ImageEncoder (768D L2)
│   │   ├── services/               # RetrievalService orchestration
│   │   ├── repositories/           # QdrantRepository (Vector DB access & schema validation)
│   │   ├── schemas/                # Multi-dataset Pydantic models
│   │   └── utils/                  # TaxonomyManager, class_resolver, image_validation
│   ├── tests/                      # 181 unit & integration tests
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                       # Fruvia Web V2 Application UI
│   ├── index.html                  # Homepage with Hero Search Widget
│   ├── retrieval.html              # Search page (/search)
│   ├── explore.html                # Species taxonomy browser (/explore)
│   ├── species.html                # Single species view
│   ├── offline.html                # PWA offline fallback page
│   ├── manifest.webmanifest        # PWA Web App Manifest
│   ├── service-worker.js           # PWA static asset caching service worker
│   ├── css/                        # Responsive CSS design system (variables, base, components, home, retrieval, explore)
│   ├── js/                         # Modular JS (config, api, utils, upload, results, modal, history, explore, navigation, pwa, retrieval)
│   ├── data/
│   │   └── species.json            # Generated ground-truth taxonomy species export
│   └── assets/svg/                 # Custom brand, SVG icons, and illustrations
├── configs/                        # System Configurations
│   └── taxonomy.yaml               # 410-class taxonomy (EN/VI names + categories)
├── scripts/                        # Utility & Evaluation Scripts
│   ├── export_taxonomy_frontend.py # Export taxonomy.yaml to frontend/data/species.json
│   ├── evaluate_retrieval.py       # Retrieval precision & recall evaluator
│   └── audit_dataset.py            # Dataset integrity auditor
├── .github/workflows/ci.yml        # GitHub Actions automated test & lint pipeline
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## 🛠️ Local Development & Running

### Prerequisites

- Python 3.10+
- Virtual environment (`venv`)

### Installation

```bash
# Clone the repository
git clone https://github.com/dinhvien04/fruvia-ai.git
cd fruvia-ai

# Activate virtual environment
.venv\Scripts\activate       # Windows
# or: source .venv/bin/activate # Linux/Mac

# Install backend dependencies
pip install -r backend/requirements.txt
```

### Export Taxonomy Data

```bash
python scripts/export_taxonomy_frontend.py
```

### Running the Application

```bash
# Start FastAPI backend & serve integrated Web V2 frontend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## 📦 Collection Architecture & Migration Roadmap

### 1. CURRENT Architecture (Production State)
- **Active Production Collection**: `fruvia_fruits360_original_dinov2_base_v1`
- **Embedding Dimensions & Metric**: 768-dim CLS token vectors (`facebook/dinov2-base`), Cosine distance.
- **Indexed Datasets**: Fruits-360 (~102,551 vectors) + Fruits-262 (~225,639 vectors) = **~328,190 vectors**.
- **Collection Configuration**: Dynamically overrideable via `FRUVIA_GALLERY_COLLECTION` environment variable, safely defaulting to `QDRANT_COLLECTION`.
- **Hybrid Filtering**: Native payload filtering on indexed fields (`category`, `canonical_class`, `source_dataset`, `dataset_name`) with automated fallback to Python-level filtering for legacy collections.

### 2. IN PROGRESS (External Processing & Staging)
- **PackEat Staging Dataset**: 103,440 total points staged in collection `fruvia_packeat_dinov2_base_v1` (103,412 high-quality eligible points across 65/65 classes + 28 non-official records safely excluded via `gallery_eligible=False`, 768-dim DINOv2 Base, Cosine distance). Expected unified gallery size: ~328,190 + 103,412 = **431,602 vectors**.
- **Taxonomy Alignment**: `configs/taxonomy.yaml` canonical source of truth synchronized with 100% PackEat classes (90 canonical species total).
- **Migration & Payload Tooling**: 
  - `scripts/create_qdrant_payload_indexes.py` (Payload index automation with fail-closed schema validation and post-creation verification).
  - `scripts/prepare_gallery_v2.py` (Resumable batch migration pipeline with schema v1 atomic checkpointing, `--skip-invalid` reporting, and `--dry-run`).
  - `scripts/validate_gallery_v2.py` (Read-only pre-flight validator for geometry, index health, uppercase taxonomy status normalization, and payload distribution).
  - `scripts/build_packeat_taxonomy_mapping.py` (Composite key join and structured PackEat record alignment).

### 3. FUTURE (Unified Gallery V2 Deployment)
- **Unified Target Collection**: `fruvia_gallery_dinov2_base_v2`
- **Standardized Payload Schema**:
  ```json
  {
    "canonical_class": "apple",
    "original_class": "apple_crimson_snow_1",
    "display_name": "Apple",
    "display_name_en": "Apple",
    "display_name_vi": "Táo",
    "category": "fruit",
    "source_dataset": "fruits360",
    "dataset_name": "fruits360_original",
    "dataset_version": "1",
    "filename": "apple_001.jpg",
    "relative_path": "gallery/apple/apple_001.jpg",
    "original_split": "gallery",
    "image_url": "https://pub-r2.fruvia.ai/thumbnails/apple_001.webp",
    "thumbnail_url": "https://pub-r2.fruvia.ai/thumbnails/apple_001.webp",
    "r2_key": "thumbnails/apple_001.webp",
    "embedding_model": "facebook/dinov2-base",
    "embedding_dimension": 768,
    "embedding_pooling": "cls",
    "embedding_normalization": "l2",
    "taxonomy_status": "EXACT",
    "source_collection": "fruvia_fruits360_original_dinov2_base_v1",
    "source_point_id": "1001",
    "gallery_schema_version": 2,
    "attributes": {}
  }
  ```
- **Live Cutover Process**: Zero-downtime transition via `FRUVIA_GALLERY_COLLECTION=fruvia_gallery_dinov2_base_v2` after full vector and schema validation.

---

## 🔍 Search Modes & API Contract

### `POST /api/retrieve`
Send a `multipart/form-data` request with an image file.

#### Parameters
- `file` (UploadFile, required): Image file (JPG, PNG, WEBP, max 10 MB).
- `top_k` (int, optional, default: 5): Number of items to return (1 to 20).
- `mode` (str, optional, default: `"image"`):
  - `"image"`: Returns Top-K nearest individual gallery images.
  - `"class"`: Groups results by canonical species class, returning Top-K distinct species with candidate expansion.
- `category` (str, optional, default: `"all"`): Filter results by category: `"fruit"`, `"vegetable"`, `"nut"`, `"seed"`, or `"all"`.

#### Response Body (Full Backward Compatibility + V2 Telemetry)
```json
{
  "query": {
    "filename": "query_durian.jpg"
  },
  "mode": "class",
  "category": "fruit",
  "results": [
    {
      "original_class": "durian",
      "canonical_class": "durian",
      "display_name": "Durian",
      "display_name_vi": "Sầu riêng",
      "category": "fruit",
      "dataset_name": "fruits262_full_original_v7",
      "dataset_version": "7",
      "filename": "durian_001.jpg",
      "relative_path": "gallery/durian/durian_001.jpg",
      "original_split": "gallery",
      "similarity": 0.8432,
      "image_url": "https://pub-r2.fruvia.ai/thumbnails/durian_001.webp",
      "hit_count": 8
    }
  ],
  "result_count": 1,
  "processing_time_ms": 112.4,
  "timing": {
    "validation_ms": 1.2,
    "embedding_ms": 78.4,
    "vector_search_ms": 32.8,
    "total_ms": 112.4
  },
  "quality_meta": {
    "top_similarity": 0.8432,
    "quality": "high_similarity"
  }
}
```

### Additional Backend V2 Endpoints
- `GET /api/live`: Lightweight process liveness probe for Kubernetes / health monitors.
- `GET /api/ready`: Full readiness probe verifying DINOv2 model state and Qdrant cluster connectivity.
- `GET /api/species`: Taxonomy lookup endpoint listing canonical species with category filtering and keyword search.
- `GET /api/species/{canonical_class}`: Detailed canonical species metadata, English/Vietnamese names, and aliases.

---

## 🔒 Production Security & Hardening Architecture

Fruvia AI implements a zero-trust, multi-layered defensive security architecture across the ASGI pipeline, ML inference engine, vector database layer, and frontend client:

1. **ASGI Raw Request Body Limiter (`RequestBodyLimitMiddleware`)**:
   - Inspects `Content-Length` headers and streams ASGI `receive()` byte chunks.
   - Aborts oversized payloads with HTTP 413 *before* multipart/form-data parsing occurs in Python memory.
2. **Restricted Pillow Decoders & Pre-Decode Geometry Guard**:
   - Explicitly restricts decoding formats to `["JPEG", "PNG", "WEBP"]` to block untrusted multi-frame decoders (GIF, TIFF, ICO, SVG, etc.).
   - Traps `Image.DecompressionBombWarning` as fatal exceptions and strictly validates `width > 0`, `height > 0`, width/height limits (4096px), and total pixels (25,000,000 px) *before* invoking `Image.load()`.
3. **Memory-Bounded Rate Limiting (`RateLimitMiddleware`)**:
   - Sliding-window rate limiter with active TTL cleanup and client capacity caps (`max_clients = 10,000`) preventing memory exhaustion under adversary IP-scanning.
4. **Least-Privilege Network & CORS Policies**:
   - `CORSMiddleware` configured with `allow_credentials=False` and restricted HTTP verbs (`GET`, `POST`, `OPTIONS`).
   - `TrustedHostMiddleware` enforcing explicit domain allowlists in production.
5. **Defense-in-Depth Security Headers**:
   - Automated injection of `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and restrictive `Permissions-Policy`.
   - Strict `Content-Security-Policy` isolating static assets and preventing inline script injection.
6. **Production Configuration Fail-Closed Validation**:
   - Pydantic validation rejecting wildcards (`*`) for CORS origins or allowed hosts, unpinned model revisions (`main`), plaintext HTTP Qdrant endpoints, or unconfigured proxy header trusts in `APP_ENV=production`.
7. **Qdrant Least-Privilege Key Separation**:
   - Strict separation between `QDRANT_API_KEY` (read-only search runtime) and `QDRANT_MIGRATION_API_KEY` (admin migration/indexing scripts).
8. **Client-Side Data Privacy & Image Host Validation**:
   - Client search history persists only public gallery result URLs—never private query image DataURLs.
   - Image URLs are verified via strict `URL` parsing against configured CDN hosts (`CONFIG.ALLOWED_IMAGE_HOSTS`).
9. **Service Worker Scoping**:
   - Service Worker caches strictly same-origin static GET assets (`url.origin === self.location.origin`), explicitly bypassing all `/api/` endpoints.
10. **Supply-Chain & Dependency Audit**:
    - Automated dependency CVE scanning via `pip-audit` integrated directly into GitHub Actions CI pipeline.

---

## 🧪 Testing & Code Quality

Run the test suite, vulnerability scanner, and linters locally:

```bash
# Run pytest unit & integration tests
python -m pytest

# Run pip-audit vulnerability check
pip-audit --requirement backend/requirements.txt

# Run Ruff linter
python -m ruff check backend/ configs/ scripts/

# Run Ruff format check
python -m ruff format --check backend/ configs/ scripts/
```

---

## 📄 License

MIT License © 2026 Fruvia AI
