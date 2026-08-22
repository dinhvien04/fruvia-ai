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
   * Fetch public runtime configuration (safe non-sensitive parameters)
   * @returns {Promise<{app_version: string, allowed_image_hosts: string[]}>}
   */
  async getPublicConfig() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${CONFIG.API_BASE_URL}/api/public-config`, {
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
   * @param {string} mode
   * @param {string} category
   * @returns {Promise<{query: {filename: string}, mode: string, category: string, results: Array<any>, result_count: number, processing_time_ms: number}>}
   */
  async retrieveImage(file, topK = 5, mode = "image", category = "fruit") {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.API_TIMEOUT_MS);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("top_k", String(topK));
    formData.append("mode", mode);
    formData.append("category", category);

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
  },

  /**
   * Fetch canonical species taxonomy information by canonical class
   * @param {string} canonicalClass
   * @returns {Promise<{canonical_class: string, name_en: string, name_vi: string|null, category: string, is_fruit: boolean, aliases: string[]}>}
   */
  async getSpecies(canonicalClass) {
    if (!canonicalClass || typeof canonicalClass !== "string") {
      throw new Error("canonical_class is required.");
    }
    const cleanClass = canonicalClass.trim().toLowerCase();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.API_TIMEOUT_MS || 8000);

    try {
      const response = await fetch(
        `${CONFIG.API_BASE_URL}/api/species/${encodeURIComponent(cleanClass)}`,
        {
          method: "GET",
          headers: { "Accept": "application/json" },
          signal: controller.signal
        }
      );
      clearTimeout(timeoutId);

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const error = new Error(data?.detail || data?.message || `HTTP error ${response.status}`);
        error.status = response.status;
        error.errorCode = data?.error_code || "SPECIES_ERROR";
        error.detail = data?.detail;
        throw error;
      }

      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        const timeoutError = new Error("Yêu cầu thông tin loài đã hết thời gian chờ.");
        timeoutError.errorCode = "TIMEOUT";
        throw timeoutError;
      }
      throw error;
    }
  },

  /**
   * Fetch general knowledge documents and nutrition profile for a canonical species
   * @param {string} canonicalClass
   * @param {number} limit
   * @returns {Promise<{canonical_class: string, display_name: string, display_name_vi: string|null, category: string, documents: Array<any>, document_count: number, processing_time_ms: number}>}
   */
  async getSpeciesKnowledge(canonicalClass, limit = 10) {
    if (!canonicalClass || typeof canonicalClass !== "string") {
      throw new Error("canonical_class is required.");
    }
    const cleanClass = canonicalClass.trim().toLowerCase();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.API_TIMEOUT_MS || 8000);

    try {
      const queryLimit = Math.max(1, Math.min(50, Number(limit) || 10));
      const response = await fetch(
        `${CONFIG.API_BASE_URL}/api/species/${encodeURIComponent(cleanClass)}/knowledge?limit=${queryLimit}`,
        {
          method: "GET",
          headers: { "Accept": "application/json" },
          signal: controller.signal
        }
      );
      clearTimeout(timeoutId);

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const error = new Error(data?.message || data?.detail || `HTTP error ${response.status}`);
        error.status = response.status;
        error.errorCode = data?.error_code || "KNOWLEDGE_ERROR";
        error.detail = data?.detail;
        throw error;
      }

      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        const timeoutError = new Error("Yêu cầu tri thức loài đã hết thời gian chờ.");
        timeoutError.errorCode = "TIMEOUT";
        throw timeoutError;
      }
      throw error;
    }
  },

  /**
   * Execute semantic knowledge search with optional document_type filtering
   * @param {{query: string, canonical_class: string, document_type?: string, limit?: number}} params
   * @returns {Promise<{query: string, canonical_class: string, document_type: string|null, results: Array<any>, result_count: number, processing_time_ms: number, timing?: any}>}
   */
  async searchKnowledge({ query, canonical_class, document_type, limit = 5 }) {
    if (!query || typeof query !== "string" || !query.trim()) {
      throw new Error("query is required.");
    }
    if (!canonical_class || typeof canonical_class !== "string" || !canonical_class.trim()) {
      throw new Error("canonical_class is required.");
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.API_TIMEOUT_MS || 8000);

    const body = {
      query: query.trim(),
      canonical_class: canonical_class.trim().toLowerCase(),
      limit: Math.max(1, Math.min(50, Number(limit) || 5))
    };

    if (document_type && typeof document_type === "string" && document_type.trim()) {
      body.document_type = document_type.trim().toLowerCase();
    }

    try {
      const response = await fetch(`${CONFIG.API_BASE_URL}/api/knowledge/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        body: JSON.stringify(body),
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const error = new Error(data?.message || data?.detail || `HTTP error ${response.status}`);
        error.status = response.status;
        error.errorCode = data?.error_code || "KNOWLEDGE_SEARCH_ERROR";
        error.detail = data?.detail;
        throw error;
      }

      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        const timeoutError = new Error("Yêu cầu tìm kiếm tri thức đã hết thời gian chờ.");
        timeoutError.errorCode = "TIMEOUT";
        throw timeoutError;
      }
      throw error;
    }
  },

  /**
   * Fetch all canonical species list with optional category and search query filters
   * @param {{category?: string, q?: string}} params
   * @returns {Promise<{total: number, items: Array<{canonical_class: string, name_en: string, name_vi: string|null, category: string, is_fruit: boolean, aliases: string[], representative_image_url: string|null}>}>}
   */
  async listSpecies({ category = "all", q = "" } = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.API_TIMEOUT_MS || 8000);

    const queryParams = new URLSearchParams();
    if (category && category !== "all") {
      queryParams.set("category", category.trim());
    }
    if (q && q.trim()) {
      queryParams.set("q", q.trim());
    }

    const queryString = queryParams.toString();
    const url = `${CONFIG.API_BASE_URL}/api/species${queryString ? `?${queryString}` : ""}`;

    try {
      const response = await fetch(url, {
        method: "GET",
        headers: { "Accept": "application/json" },
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const error = new Error(data?.detail || data?.message || `HTTP error ${response.status}`);
        error.status = response.status;
        error.errorCode = data?.error_code || "SPECIES_LIST_ERROR";
        error.detail = data?.detail;
        throw error;
      }

      return data;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        const timeoutError = new Error("Yêu cầu danh sách loài đã hết thời gian chờ.");
        timeoutError.errorCode = "TIMEOUT";
        throw timeoutError;
      }
      throw error;
    }
  }
};
