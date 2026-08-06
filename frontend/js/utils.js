/**
 * Fruvia AI — Utility Functions
 */
const Utils = {
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
    if (rawNum >= 0.70) {
      levelClass = "level-high";
    } else if (rawNum >= 0.55) {
      levelClass = "level-moderate";
    }

    return { percentageText, visualWidth, levelClass };
  },

  /**
   * Map domain & API error codes into friendly user messages.
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

    if (code === "MODEL_NOT_LOADED" || status === 503) {
      return {
        title: "Feature Encoder Offline",
        message: "The DINOv2 feature encoder model is still initializing or unavailable. Please try again shortly."
      };
    }

    if (code === "QDRANT_UNAVAILABLE" || code === "COLLECTION_NOT_FOUND") {
      return {
        title: "Vector Search Offline",
        message: "Could not connect to Qdrant vector database or collection is unavailable. Please check backend connection."
      };
    }

    if (code === "TIMEOUT") {
      return {
        title: "Request Timeout",
        message: "The request took too long to complete. Please try again."
      };
    }

    if (status === 0 || error.message.includes("Failed to fetch")) {
      return {
        title: "Backend Unreachable",
        message: "Cannot connect to Fruvia AI backend server. Please verify the backend is running at http://localhost:8000."
      };
    }

    return {
      title: "Retrieval Error",
      message: error.message || "An unexpected error occurred while processing your request. Please try again."
    };
  },

  /**
   * Escape text to prevent XSS when inserting dynamic content
   * @param {string} str
   * @returns {string}
   */
  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
};
