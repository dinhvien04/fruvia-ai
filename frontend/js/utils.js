/**
 * Fruvia AI — Utility Functions & Security Helpers
 */
const Utils = {
  /**
   * Escape HTML special characters to prevent XSS.
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
  },

  /**
   * Validate image URL using URL() parsing against approved hostnames and protocols.
   * Prevents XSS, javascript: injection, and arbitrary untrusted external image hosts.
   * @param {string|null|undefined} url
   * @returns {boolean}
   */
  isSafeImageUrl(url) {
    if (!url || typeof url !== "string") return false;
    const trimmed = url.trim();

    // 1. Safe relative URLs and data: image URLs
    if (trimmed.startsWith("data:image/jpeg;") ||
        trimmed.startsWith("data:image/png;") ||
        trimmed.startsWith("data:image/webp;")) {
      return true;
    }
    if (trimmed.startsWith("/") && !trimmed.startsWith("//")) {
      return true;
    }

    // 2. Full URL validation via URL object
    try {
      const parsed = new URL(trimmed, window.location.origin);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        const hostname = parsed.hostname.toLowerCase();

        // Same origin is always allowed
        if (hostname === window.location.hostname) {
          return true;
        }

        // Local development hostnames
        if (hostname === "localhost" || hostname === "127.0.0.1") {
          return true;
        }

        // Check against CONFIG.ALLOWED_IMAGE_HOSTS
        const allowedHosts = CONFIG.ALLOWED_IMAGE_HOSTS || [];
        for (const allowed of allowedHosts) {
          const cleanAllowed = allowed.toLowerCase().trim();
          if (hostname === cleanAllowed || hostname.endsWith("." + cleanAllowed)) {
            return true;
          }
        }
      }
    } catch {
      return false;
    }

    return false;
  },

  /**
   * Safe image URL fallback handler
   * @param {string|null|undefined} url
   * @param {string} fallback
   * @returns {string}
   */
  getSafeImageUrl(url, fallback = "assets/svg/fruit-placeholder.svg") {
    if (this.isSafeImageUrl(url)) {
      return url;
    }
    return fallback;
  },

  /**
   * Format similarity score into user-facing percentage text and progress visual width.
   * User-facing label: "Mức độ tương đồng"
   * @param {number} similarity
   * @returns {{percentageText: string, visualWidth: string, levelClass: string, labelVi: string}}
   */
  formatSimilarity(similarity) {
    const rawNum = typeof similarity === "number" ? similarity : 0.0;
    const percentageVal = (rawNum * 100).toFixed(1);
    const percentageText = `${percentageVal}%`;
    const clampedWidth = Math.max(0, Math.min(100, rawNum * 100)).toFixed(1);
    const visualWidth = `${clampedWidth}%`;

    let levelClass = "level-low";
    let labelVi = "Tương đồng thấp";

    if (rawNum >= 0.75) {
      levelClass = "level-high";
      labelVi = "Rất tương đồng";
    } else if (rawNum >= CONFIG.LOW_SIMILARITY_THRESHOLD) {
      levelClass = "level-moderate";
      labelVi = "Tương đồng khá";
    }

    return { percentageText, visualWidth, levelClass, labelVi };
  },

  /**
   * Format relative timestamp (e.g., "5 phút trước", "Hôm nay")
   * @param {number|string} timestamp
   * @returns {string}
   */
  formatRelativeTime(timestamp) {
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return "";

    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);

    if (diffSec < 60) return "Vừa xong";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)} phút trước`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} giờ trước`;
    return date.toLocaleDateString("vi-VN", { day: "numeric", month: "numeric", year: "numeric" });
  },

  /**
   * Map API errors into clear, non-technical Vietnamese user messages.
   * @param {Error} error
   * @returns {{title: string, message: string}}
   */
  getFriendlyErrorMessage(error) {
    const code = error.errorCode || "";
    const status = error.status;

    if (code === "FILE_TOO_LARGE" || status === 413) {
      return {
        title: "Tệp ảnh quá lớn",
        message: "Dung lượng ảnh vượt quá giới hạn 10 MB. Vui lòng chọn ảnh nhỏ hơn."
      };
    }

    if (code === "UNSUPPORTED_FORMAT" || status === 415) {
      return {
        title: "Định dạng không hỗ trợ",
        message: "Vui lòng chọn ảnh định dạng JPG, JPEG, PNG hoặc WEBP."
      };
    }

    if (code === "INVALID_IMAGE" || status === 400) {
      return {
        title: "Ảnh không hợp lệ",
        message: "Tệp được chọn bị hỏng hoặc không phải là hình ảnh hợp lệ. Vui lòng thử ảnh khác."
      };
    }

    if (code === "MODEL_NOT_LOADED") {
      return {
        title: "Hệ thống AI đang khởi động",
        message: "Mô hình xử lý hình ảnh đang sẵn sàng. Vui lòng thử lại sau vài giây."
      };
    }

    if (code === "QDRANT_UNAVAILABLE") {
      return {
        title: "Dịch vụ tìm kiếm đang bận",
        message: "Hệ thống tạm thời không phản hồi. Vui lòng kiểm tra lại kết nối mạng."
      };
    }

    if (code === "TIMEOUT") {
      return {
        title: "Hết thời gian chờ",
        message: "Quá trình tìm kiếm mất nhiều thời gian hơn dự kiến. Vui lòng thử lại."
      };
    }

    if (status === 0 || (error.message && error.message.includes("Failed to fetch"))) {
      return {
        title: "Không có kết nối máy chủ",
        message: "Vui lòng đảm bảo hệ thống Fruvia backend đang hoạt động."
      };
    }

    return {
      title: "Chưa thể thực hiện tìm kiếm",
      message: error.message || "Đã xảy ra sự cố không xác định. Vui lòng thử lại sau."
    };
  }
};

// Freeze Utils
Object.freeze(Utils);
