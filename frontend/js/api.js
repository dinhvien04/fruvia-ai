/**
 * Fruvia AI — API Client Module
 */
const ApiClient = {
  /**
   * Fetch health status from backend
   * @returns {Promise<{status: string, model_loaded: boolean, qdrant_connected: boolean, collection_available: boolean, version: string}>}
   */
  async getHealth() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${CONFIG.API_BASE_URL}/api/health`, {
        method: "GET",
        headers: { "Accept": "application/json" },
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  },

  /**
   * Submit query image for similarity retrieval
   * @param {File} file
   * @param {number} topK
   * @returns {Promise<{query: {filename: string}, results: Array<any>, result_count: number, processing_time_ms: number}>}
   */
  async retrieveImage(file, topK = 5) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.API_TIMEOUT_MS);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("top_k", String(topK));

    try {
      const response = await fetch(`${CONFIG.API_BASE_URL}/api/retrieve`, {
        method: "POST",
        body: formData,
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const error = new Error(data?.message || `HTTP error ${response.status}`);
        error.status = response.status;
        error.errorCode = data?.error_code || "UNKNOWN_ERROR";
        error.detail = data?.detail;
        throw error;
      }

      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        const timeoutError = new Error("The request timed out. Please try again.");
        timeoutError.errorCode = "TIMEOUT";
        throw timeoutError;
      }
      throw error;
    }
  }
};
