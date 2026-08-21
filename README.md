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
│   │   ├── api/                    # Route handlers (/health, /ready, /retrieve)
│   │   ├── core/                   # Config, rate limiting, logging, exceptions
│   │   ├── ml/                     # DINOv2 ImageEncoder (768D L2)
│   │   ├── services/               # RetrievalService orchestration
│   │   ├── repositories/           # QdrantRepository (Vector DB access)
│   │   ├── schemas/                # Multi-dataset Pydantic models
│   │   └── utils/                  # TaxonomyManager, class_resolver, image_validation
│   ├── tests/                      # 155 unit & integration tests
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

## 🧪 Testing & Code Quality

Run the test suite and linters locally:

```bash
# Run pytest (155 unit & integration tests)
python -m pytest

# Run Ruff linter
python -m ruff check backend/ configs/ scripts/

# Run Ruff format check
python -m ruff format --check backend/ configs/ scripts/
```

---

## 📄 License

MIT License © 2026 Fruvia AI
