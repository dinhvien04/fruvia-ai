/**
 * Fruvia AI — Frontend Configuration
 */
const CONFIG = {
  // Base API Endpoint
  API_BASE_URL: "", // Same origin default for production/ FastAPI deployment

  // Search Defaults
  DEFAULT_TOP_K: 5,
  DEFAULT_MODE: "image", // "image" | "class"
  DEFAULT_CATEGORY: "all", // "all" | "fruit" | "vegetable" | "nut" | "seed"

  // Timeout settings
  API_TIMEOUT_MS: 30000,

  // Thresholds
  LOW_SIMILARITY_THRESHOLD: 0.60,

  // LocalStorage Keys
  STORAGE_HISTORY_KEY: "fruvia_recent_searches_v2",
  MAX_HISTORY_ITEMS: 10,

  // Image Host Security Allowlist (Exact hostnames; do NOT allow arbitrary *.r2.dev)
  ALLOWED_IMAGE_HOSTS: [
    "localhost",
    "127.0.0.1"
  ],

  // Product Stats (Single source of truth to avoid scattered hardcoded numbers)
  STATS: {
    VECTOR_COUNT_TEXT: "Hàng trăm nghìn",
    VECTOR_EXACT_LABEL: "328,190+",
    SPECIES_COUNT_LABEL: "284+",
    DATASET_COUNT_LABEL: "2 datasets",
    FEATURE_DIM_LABEL: "768D DINOv2"
  }
};

// Freeze config to avoid accidental runtime mutations
Object.freeze(CONFIG);
