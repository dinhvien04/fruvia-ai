/**
 * Fruvia AI — Utility Functions
 */
const Utils = {
  /**
   * Validate image URL to prevent XSS / malicious protocol injection.
   * Only accepts http://, https://, or relative URLs. Rejects javascript:, data:, file:, etc.
   * @param {string|null|undefined} url
   * @returns {boolean}
   */
  isSafeImageUrl(url) {
    if (!url || typeof url !== "string") return false;
    const trimmed = url.trim().toLowerCase();
    return (
      trimmed.startsWith("https://") ||
      trimmed.startsWith("http://localhost") ||
      trimmed.startsWith("http://127.0.0.1") ||
      trimmed.startsWith("/")
    );
  },

  /**
   * Format similarity score (0.0 to 1.0 or negative) into percentage text safely.
   * Keeps negative similarity layout safe by clamping visual percentage to 0%.
   * @param {number} similarity
   * @returns {{percentageText: string, visualWidth: string, levelClass: string}}
   */
  formatSimilarity(similarity) {
    const rawNum = typeof similarity === "number" ? similarity : 0.0;
    const percentageVal = (rawNum * 100).toFixed(2);
    const percentageText = `${percentageVal}%`;

    // Clamp width percentage to 0% - 100% for layout safety
    const clampedWidth = Math.max(0, Math.min(100, rawNum * 100)).toFixed(2);
    const visualWidth = `${clampedWidth}%`;

    let levelClass = "level-low";
    if (rawNum >= CONFIG.HIGH_SIMILARITY_THRESHOLD) {
      levelClass = "level-high";
    } else if (rawNum >= CONFIG.LOW_SIMILARITY_THRESHOLD) {
      levelClass = "level-moderate";
    }

    return { percentageText, visualWidth, levelClass };
  },

  /**
   * Map domain & API error codes into friendly user messages.
   * Checks specific error_code prior to falling back to HTTP status codes.
   * @param {Error} error
   * @returns {{title: string, message: string}}
   */
  getFriendlyErrorMessage(error) {
    const code = error.errorCode || "";
    const status = error.status;

    if (code === "FILE_TOO_LARGE" || status === 413) {
      return {
        title: "File Too Large",
        message: "The uploaded image exceeds the 10 MB size limit. Please choose a smaller image."
      };
    }

    if (code === "UNSUPPORTED_FORMAT" || status === 415) {
      return {
        title: "Unsupported Format",
        message: "Please upload a valid image in JPG, JPEG, PNG, or WEBP format."
      };
    }

    if (code === "INVALID_IMAGE" || status === 400) {
      return {
        title: "Invalid Image File",
        message: "The selected file appears to be corrupted or invalid. Please select another image."
      };
    }

    if (code === "MODEL_NOT_LOADED") {
      return {
        title: "Feature Encoder Offline",
        message: "The DINOv2 feature encoder model is still initializing or unavailable. Please try again shortly."
      };
    }

    if (code === "ENCODING_FAILED") {
      return {
        title: "Feature Extraction Failed",
        message: "Failed to extract deep feature embeddings from the image. Please try another image."
      };
    }

    if (code === "QDRANT_UNAVAILABLE") {
      return {
        title: "Vector Search Offline",
        message: "Could not connect to Qdrant vector database. Please verify your connection."
      };
    }

    if (code === "COLLECTION_NOT_FOUND") {
      return {
        title: "Search Collection Missing",
        message: "Target vector collection is missing in Qdrant Cloud. Please verify configuration."
      };
    }

    if (code === "TIMEOUT") {
      return {
        title: "Request Timeout",
        message: "The request took too long to complete. Please try again."
      };
    }

    if (code === "INTERNAL_ERROR" || status === 500) {
      return {
        title: "Internal Server Error",
        message: "An internal server error occurred while processing retrieval. Please try again later."
      };
    }

    if (status === 503) {
      return {
        title: "Service Unavailable",
        message: "The image retrieval service is currently unavailable or initializing. Please try again in a few moments."
      };
    }

    if (status === 0 || (error.message && error.message.includes("Failed to fetch"))) {
      return {
        title: "Backend Unreachable",
        message: "Cannot connect to Fruvia AI backend server. Please verify backend is running at " + CONFIG.API_BASE_URL
      };
    }

    return {
      title: "Retrieval Error",
      message: error.message || "An unexpected error occurred while processing your request. Please try again."
    };
  }
};
