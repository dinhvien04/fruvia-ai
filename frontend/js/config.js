/**
 * Fruvia AI — Frontend Configuration
 */
const CONFIG = {
  // Dynamically resolve same-origin production deployment vs local dev fallback
  API_BASE_URL:
    window.FRUVIA_API_BASE_URL ||
    (location.origin && location.origin !== "null" && !location.origin.includes("file://")
      ? location.origin
      : "http://localhost:8000"),
  API_TIMEOUT_MS: 60000,
  MAX_UPLOAD_MB: 10,
  MAX_UPLOAD_BYTES: 10 * 1024 * 1024,
  LOW_SIMILARITY_THRESHOLD: 0.55,
  HIGH_SIMILARITY_THRESHOLD: 0.70,
  ALLOWED_EXTENSIONS: [".jpg", ".jpeg", ".png", ".webp"],
  ALLOWED_MIME_TYPES: ["image/jpeg", "image/png", "image/webp"]
};
