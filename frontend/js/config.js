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

// Freeze static config to prevent accidental runtime mutations
Object.freeze(CONFIG);

/**
 * Fruvia AI — Dynamic Runtime Configuration
 * Manages mutable runtime state (such as dynamic allowed image hosts from GET /api/public-config)
 * without mutating the immutable CONFIG object.
 */
const RuntimeConfig = {
  _allowedImageHosts: new Set(
    (CONFIG.ALLOWED_IMAGE_HOSTS || []).map((h) => h.toLowerCase().trim())
  ),
  _appVersion: null,
  _isLoaded: false,
  _loadPromise: null,

  /**
   * Return array of all currently approved image hostnames (lowercase).
   * @returns {string[]}
   */
  getAllowedImageHosts() {
    return Array.from(this._allowedImageHosts);
  },

  /**
   * Check if a hostname is in the approved allowlist (exact match only).
   * @param {string} hostname
   * @returns {boolean}
   */
  isHostAllowed(hostname) {
    if (!hostname || typeof hostname !== "string") return false;
    return this._allowedImageHosts.has(hostname.toLowerCase().trim());
  },

  /**
   * Fetch public runtime configuration from backend and merge allowed image hosts.
   * Safe to call multiple times; uses memoized promise and fails gracefully.
   * @returns {Promise<void>}
   */
  async load() {
    if (this._isLoaded) return;
    if (this._loadPromise) return this._loadPromise;

    this._loadPromise = (async () => {
      try {
        if (typeof ApiClient !== "undefined" && ApiClient.getPublicConfig) {
          const publicConfig = await ApiClient.getPublicConfig();
          if (publicConfig && typeof publicConfig === "object") {
            if (publicConfig.app_version) {
              this._appVersion = publicConfig.app_version;
            }
            if (Array.isArray(publicConfig.allowed_image_hosts)) {
              for (const host of publicConfig.allowed_image_hosts) {
                if (host && typeof host === "string") {
                  const cleaned = host.toLowerCase().trim();
                  if (cleaned) {
                    this._allowedImageHosts.add(cleaned);
                  }
                }
              }
            }
          }
          this._isLoaded = true;
        }
      } catch (err) {
        console.warn(
          "Fruvia: Could not fetch public runtime config; using default localhost image allowlist.",
          err.message || err
        );
      }
    })();

    return this._loadPromise;
  }
};

