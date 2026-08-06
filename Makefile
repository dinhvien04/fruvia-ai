# ============================================================
# Fruvia AI Makefile
# ============================================================

.PHONY: help install test test-unit test-integration lint format \
        run-backend run-frontend docker-build docker-up docker-down \
        audit-dataset create-manifest validate-manifest clean

PYTHON ?= python
PIP ?= pip
PYTEST ?= pytest

# ---------- Help ----------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

# ---------- Setup ----------
install: ## Install Python dependencies
	$(PIP) install -r backend/requirements.txt

install-dev: ## Install dev dependencies
	$(PIP) install -r backend/requirements.txt
	$(PIP) install pytest pytest-cov ruff

# ---------- Testing ----------
test: ## Run all tests
	$(PYTEST) backend/tests/ -v

test-unit: ## Run unit tests only
	$(PYTEST) backend/tests/unit/ -v -m unit

test-integration: ## Run integration tests only
	$(PYTEST) backend/tests/integration/ -v -m integration

test-cov: ## Run tests with coverage
	$(PYTEST) backend/tests/ -v --cov=backend/app --cov-report=html

# ---------- Code Quality ----------
lint: ## Run linter
	ruff check backend/

format: ## Format code
	ruff format backend/

# ---------- Backend ----------
run-backend: ## Run FastAPI backend
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# ---------- Frontend ----------
run-frontend: ## Serve frontend (simple HTTP server)
	$(PYTHON) -m http.server 3000 --directory frontend

# ---------- Dataset Scripts ----------
audit-dataset: ## Audit raw dataset
	$(PYTHON) scripts/audit_dataset.py --data-dir data/raw --output data/metadata/audit_report.json

create-manifest: ## Create dataset manifest
	$(PYTHON) scripts/create_manifest.py --data-dir data/raw --output data/manifests/manifest.csv

validate-manifest: ## Validate existing manifest
	$(PYTHON) scripts/validate_manifest.py --manifest data/manifests/manifest.csv

# ---------- Docker ----------
docker-build: ## Build Docker images
	docker-compose build

docker-up: ## Start services
	docker-compose up -d

docker-down: ## Stop services
	docker-compose down

# ---------- Cleanup ----------
clean: ## Remove generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov .coverage
