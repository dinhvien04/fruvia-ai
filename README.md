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
| **Frontend Retrieval Web UI** | ✅ Implemented | Responsive web app with drag & drop, clipboard paste (Ctrl+V), lightbox, skeleton loading, and health status |
| **Fruit Classifier (ConvNeXt)** | 🔄 Planned / In Progress | Model training scripts present in notebooks; classification API in progress |

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
│                    Frontend Web UI                      │
│            retrieval.html (Vanilla JS + CSS)            │
│    Drag-and-Drop │ Clipboard Paste │ Lightbox Modal      │
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
│   │   ├── main.py                 # FastAPI application & lifecycle
│   │   ├── api/                    # Route handlers (/health, /ready, /retrieve)
│   │   ├── core/                   # Config, rate limiting, logging, exceptions
│   │   ├── ml/                     # DINOv2 ImageEncoder (768D L2)
│   │   ├── services/               # RetrievalService orchestration
│   │   ├── repositories/           # QdrantRepository (Vector DB access)
│   │   ├── schemas/                # Multi-dataset Pydantic models
│   │   └── utils/                  # TaxonomyManager, class_resolver, image_validation
│   ├── tests/
│   │   ├── unit/                   # Unit tests (mock Qdrant & DINOv2)
│   │   └── integration/            # FastAPI TestClient endpoint integration tests
│   ├── requirements.txt
│   └── Dockerfile                  # Production container with HEALTHCHECK on /api/ready
├── frontend/                       # Web Application UI
│   ├── retrieval.html              # Image Retrieval search page
│   ├── css/                        # Responsive CSS styles
│   └── js/                         # API client, UI controller, utilities
├── configs/                        # System Configurations
│   ├── taxonomy.yaml               # 410-class taxonomy (EN/VI names + categories)
│   ├── class_mapping.yaml          # Legacy Fruits-360 class mapping
│   └── classes.yaml                # Target classification classes
├── scripts/                        # Utility & Evaluation Scripts
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

### Environment Configuration

Copy `.env.example` to `.env` and provide your Qdrant Cloud credentials:

```ini
APP_ENV=development
QDRANT_URL=https://your-cluster.qdrant.io:6333
QDRANT_API_KEY=your-api-key
QDRANT_COLLECTION=fruvia_fruits360_original_dinov2_base_v1
DINOV2_REVISION=main
RATE_LIMIT_PER_MINUTE=60
MAX_CONCURRENT_INFERENCES=4
```

### Running the Application

```bash
# Start FastAPI backend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

In a separate terminal, serve the frontend:

```bash
python -m http.server 3000 --directory frontend
```

Open [http://localhost:3000/retrieval.html](http://localhost:3000/retrieval.html) in your browser.

---

## 🧪 Testing & Code Quality

Run the test suite and linters locally before pushing:

```bash
# Run pytest (154 unit & integration tests)
python -m pytest

# Run Ruff linter
python -m ruff check backend/ configs/ scripts/

# Run Ruff format check
python -m ruff format --check backend/ configs/ scripts/
```

---

## 📦 Collection Naming & Migration Strategy

- Current Production Collection: `fruvia_fruits360_original_dinov2_base_v1`
  - Note: This collection name is preserved for backward compatibility and contains both Fruits-360 and Fruits-262 embeddings.
- Recommended Collection Name for Next Index Refresh: `fruvia_gallery_dinov2_base_v2`

---

## 🔒 Security & Performance Features

1. **Decompression Bomb Protection**: Pillow pixel limits capped at 25,000,000 pixels.
2. **Bounded File Streaming**: Maximum file uploads strictly enforced in RAM before decoding.
3. **In-Memory Rate Limiting**: Capped per IP to prevent search endpoint abuse.
4. **Concurrency Limiter**: Global semaphore prevents GPU/CPU memory overflow under high concurrency.
5. **No Vector Over-Fetching**: Qdrant queries request payload only (`with_vectors=False`).
6. **Container Health Readiness**: Docker `HEALTHCHECK` queries `/api/ready` to ensure ML model & Qdrant are fully online.

---

## 📄 License

MIT License © 2026 Fruvia AI
