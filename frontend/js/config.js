/**
 * Fruvia AI — Configuration Settings
 */
const CONFIG = {
  API_BASE_URL:
    window.FRUVIA_API_BASE_URL ||
    (location.hostname === "localhost" || location.hostname === "127.0.0.1"
      ? "http://localhost:8000"
      : ""),
  API_TIMEOUT_MS: 60000,
  MAX_UPLOAD_MB: 10,
  MAX_UPLOAD_BYTES: 10 * 1024 * 1024,
  HEALTH_CHECK_INTERVAL_MS: 30000,
  LOW_SIMILARITY_THRESHOLD: 0.55,
  HIGH_SIMILARITY_THRESHOLD: 0.70,
  ALLOWED_EXTENSIONS: [".jpg", ".jpeg", ".png", ".webp"],
  ALLOWED_MIME_TYPES: ["image/jpeg", "image/png", "image/webp"]
};
