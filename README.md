# Fruvia AI

AI-powered fruit recognition and image retrieval system using deep learning.

## Project Goal

Fruvia AI provides two independent AI capabilities:

1. **Fruit Classification** — Upload an image, get top-3 fruit predictions with confidence scores
2. **Image Retrieval** — Upload an image, find visually similar fruit images via vector search (*Implemented & Active*)

> **Note on Implementation Status**: The **Image Retrieval backend** is fully implemented and hardened (DINOv2 embeddings + Qdrant Cloud collection `fruvia_fruits360_original_dinov2_base_v1`). Fruit Classification endpoints and Frontend web application are currently **NOT YET IMPLEMENTED** (scheduled for future phases).

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                     Frontend                         │
│  index.html │ classify.html │ retrieval.html         │
│         HTML + CSS + Vanilla JavaScript              │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (JSON + multipart)
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI Backend                     │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │  /health │  │ /classify │  │   /retrieve      │  │
│  └──────────┘  └─────┬─────┘  └────────┬─────────┘  │
│                      │                 │             │
│         ┌────────────▼───┐   ┌─────────▼──────────┐ │
│         │  ConvNeXt-Tiny │   │  DINOv2 Encoder    │ │
│         │  Classifier    │   │  (768-dim vectors) │ │
│         └────────────────┘   └─────────┬──────────┘ │
│                                        │             │
│                              ┌─────────▼──────────┐ │
│                              │  Qdrant Repository  │ │
│                              └─────────┬──────────┘ │
└────────────────────────────────────────┼────────────┘
                                         │
                               ┌─────────▼──────────┐
                               │   Qdrant Cloud     │
                               │ (Vector Database)  │
                               └────────────────────┘
```

### Classification Flow

```
User uploads image
    → Validate (format, size, integrity)
    → Preprocess (resize 224×224, normalize)
    → ConvNeXt-Tiny inference
    → Softmax → Top-3 predictions
    → Confidence threshold check
    → Return predictions + accepted flag
```

### Retrieval Flow

```
User uploads image
    → Validate (format, size, integrity)
    → DINOv2 encode → 768-dim vector (L2 normalized)
    → Query Qdrant Cloud (cosine similarity)
    → Return Top-K similar images with similarity scores
```

## Project Structure

```
fruvia-ai/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── api/                    # Route handlers
│   │   │   ├── routes_health.py
│   │   │   ├── routes_classification.py
│   │   │   ├── routes_retrieval.py
│   │   │   └── routes_fruits.py
│   │   ├── core/                   # Config, logging, exceptions
│   │   ├── ml/                     # ML models and preprocessing
│   │   ├── services/               # Business logic
│   │   ├── repositories/           # Data access (Qdrant)
│   │   ├── schemas/                # Pydantic request/response models
│   │   └── utils/                  # Image validation, file helpers
│   ├── tests/
│   │   ├── unit/                   # No external deps
│   │   └── integration/            # May need model/Qdrant
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                       # Static HTML/CSS/JS
├── notebooks/                      # Colab notebooks (01–07)
├── scripts/                        # Dataset audit, manifest, export
├── configs/                        # YAML configuration
│   ├── classes.yaml                # Target class list
│   ├── class_mapping.yaml          # Original → target mapping
│   └── training.yaml               # Training hyperparameters
├── data/                           # Dataset files (not committed)
├── models/                         # Trained model artifacts
├── .env.example                    # Environment variable template
├── docker-compose.yml
├── pyproject.toml
└── Makefile
```

## Getting Started

### Prerequisites

- Python 3.10+
- pip

### Local Setup

```bash
# Clone repository
git clone https://github.com/dinhvien04/fruvia-ai.git
cd fruvia-ai

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r backend/requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env with your Qdrant Cloud credentials
```

### Run Backend

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Or use Make:

```bash
make run-backend
```

### Run Frontend

```bash
make run-frontend
# Opens at http://localhost:3000
```

### Run Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# Integration tests only
make test-integration
```

### Docker

```bash
# Build and start
make docker-build
make docker-up

# Stop
make docker-down
```

## Qdrant Cloud Configuration

1. Create an account at [Qdrant Cloud](https://cloud.qdrant.io)
2. Create a cluster
3. Copy the endpoint URL and API key
4. Set in your `.env`:

```
QDRANT_URL=https://your-cluster.qdrant.io:6333
QDRANT_API_KEY=your-api-key-here
```

**Never commit `.env` or API keys to the repository.**

## Colab Notebooks

> **Notebooks are authored in the repository and executed on Google Colab.**
> They are never run locally or in CI.

### Workflow

```
GitHub repository
  → Open notebook in Google Colab
  → Enable T4 GPU (for embedding/training notebooks)
  → Read KAGGLE_API_TOKEN from Colab Secrets
  → Download Fruits-360 into /content/fruits360
  → Process and embed on Colab
  → Upload vectors to Qdrant Cloud
  → Save checkpoints to Google Drive
```

| Notebook | Purpose | Runtime |
|---|---|---|
| `01_explore_fruits360.ipynb` | Explore and visualize the dataset | CPU |
| `02_prepare_dataset.ipynb` | Create retrieval + classification manifests | CPU |
| `03_train_efficientnet_baseline.ipynb` | Train EfficientNet-B0 baseline | GPU |
| `04_train_convnext.ipynb` | Train ConvNeXt-Tiny (primary) | GPU |
| `05_evaluate_models.ipynb` | Compare models on test set | GPU |
| `06_generate_dinov2_embeddings.ipynb` | Generate DINOv2 image embeddings | GPU (T4) |
| `07_upload_qdrant.ipynb` | Upload vectors to Qdrant Cloud | CPU |

### Colab Secrets Required

| Secret | Description / Used by |
|---|---|
| `KAGGLE_API_TOKEN` (or `KAGGLE_USERNAME` & `KAGGLE_KEY`) | Kaggle API credentials for downloading Fruits-360 |
| `QDRANT_URL` | Qdrant Cloud endpoint URL (Collection: `fruvia_fruits360_original_dinov2_base_v1`) |
| `QDRANT_API_KEY` | Qdrant Cloud API key |

All data paths use `/content/` (Colab default) or Google Drive. No Windows paths.

## Data Conventions

- **Raw data** is never modified — stored in `data/raw/`
- **Class mapping** is defined in `configs/class_mapping.yaml`
- **Manifest CSV** tracks every image with metadata and split assignment
- **Splits**: Train 70% / Validation 15% / Test 15%
- **Random seed**: 42 (configurable in `configs/training.yaml`)
- SHA-256 is used for duplicate detection and data-leakage mitigation

## Models

| Model | Role | Input | Output |
|---|---|---|---|
| ConvNeXt-Tiny | Classification (primary) | 224×224 RGB | Class probabilities |
| EfficientNet-B0 | Classification (baseline) | 224×224 RGB | Class probabilities |
| DINOv2-Base | Image embedding | Variable RGB | 768-dim L2 vector |

### Confidence vs Similarity

- **Confidence** (classification): Probability from softmax — how sure the model is about the predicted class. Range 0-1.
- **Cosine Similarity** (retrieval): Geometric distance between embedding vectors — how visually similar two images are. Range 0-1 (after L2 normalization). This is NOT "accuracy."

## Current Limitations

- Model artifacts (`.pth` files) are not included in the repository — must be trained via Colab notebooks
- Retrieval requires Qdrant Cloud connection — offline mode not yet supported
- Frontend is static HTML/CSS/JS — no framework
- No user authentication
- No rate limiting (planned for production)
- Model accuracy claims will be added only after Phase 3 evaluation is complete

## Dataset

This project uses the [Fruits-360 Original Size](https://www.kaggle.com/datasets/moltean/fruits) dataset.

**Citation**: Horea Muresan, Mihai Oltean, Fruit recognition from images using deep learning, Acta Univ. Sapientiae, Informatica Vol. 10, Issue 1, pp. 26-42, 2018.

## License

MIT
