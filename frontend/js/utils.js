/**
 * Fruvia AI — Utility Functions & Error Mappings
 */
const Utils = {
  /**
   * Validate image URL to prevent XSS / malicious protocol injection.
   * Accepts http://, https://, or relative URLs.
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
   * Format similarity score into percentage text and visual progress width.
   * @param {number} similarity
   * @returns {{percentageText: string, visualWidth: string, levelClass: string}}
   */
  formatSimilarity(similarity) {
    const rawNum = typeof similarity === "number" ? similarity : 0.0;
    const percentageVal = (rawNum * 100).toFixed(2);
    const percentageText = `${percentageVal}%`;

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
   * Map API errors into clear, professional Vietnamese user messages.
   * @param {Error} error
   * @returns {{title: string, message: string}}
   */
  getFriendlyErrorMessage(error) {
    const code = error.errorCode || "";
    const status = error.status;

    if (code === "FILE_TOO_LARGE" || status === 413) {
      return {
        title: "Tệp hình ảnh quá lớn",
        message: "Dung lượng ảnh vượt quá giới hạn 10 MB. Vui lòng chọn ảnh nhỏ hơn."
      };
    }

    if (code === "UNSUPPORTED_FORMAT" || status === 415) {
      return {
        title: "Định dạng không được hỗ trợ",
        message: "Vui lòng sử dụng hình ảnh định dạng JPG, JPEG, PNG hoặc WEBP."
      };
    }

    if (code === "INVALID_IMAGE" || status === 400) {
      return {
        title: "Không thể xử lý hình ảnh",
        message: "Tệp ảnh được chọn bị hỏng hoặc không hợp lệ. Vui lòng chọn tệp ảnh khác."
      };
    }

    if (code === "MODEL_NOT_LOADED") {
      return {
        title: "Hệ thống AI đang khởi tạo",
        message: "Mô hình DINOv2 đang được tải lên bộ nhớ. Vui lòng thử lại sau giây lát."
      };
    }

    if (code === "QDRANT_UNAVAILABLE") {
      return {
        title: "Không thể kết nối Qdrant Vector DB",
        message: "Cơ sở dữ liệu vector tạm thời không phản hồi. Vui lòng kiểm tra lại kết nối mạng."
      };
    }

    if (code === "TIMEOUT") {
      return {
        title: "Yêu cầu quá thời gian xử lý",
        message: "Thời gian phản hồi vượt quá giới hạn cho phép. Vui lòng thử lại."
      };
    }

    if (status === 0 || (error.message && error.message.includes("Failed to fetch"))) {
      return {
        title: "Không thể kết nối đến máy chủ",
        message: "Vui lòng kiểm tra dịch vụ backend đang chạy tại " + CONFIG.API_BASE_URL
      };
    }

    return {
      title: "Lỗi truy vấn",
      message: error.message || "Đã xảy ra lỗi không xác định. Vui lòng thử lại sau."
    };
  }
};
