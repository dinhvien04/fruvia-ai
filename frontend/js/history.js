/**
 * Fruvia AI — Client-Only History Module (localStorage)
 * Stores minimal query history (thumbnails, timestamp, query metadata).
 * Does not send history to server. Caps at 10 items.
 */
const SearchHistory = {
  getHistory() {
    try {
      const raw = localStorage.getItem(CONFIG.STORAGE_HISTORY_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      console.warn("Fruvia: Failed to read search history from localStorage", e);
      return [];
    }
  },

  /**
   * Save a search record to history
   * @param {{
   *   thumbnailUrl?: string,
   *   filename?: string,
   *   topResultNameVi?: string,
   *   topResultNameEn?: string,
   *   similarity?: number,
   *   mode?: string,
   *   category?: string,
   *   timestamp?: number
   * }} entry
   */
  addEntry(entry) {
    if (!entry) return;
    try {
      let list = this.getHistory();

      const newRecord = {
        id: "hist_" + Date.now() + "_" + Math.random().toString(36).substring(2, 6),
        thumbnailUrl: entry.thumbnailUrl || null,
        filename: entry.filename || "Uploaded Image",
        topResultNameVi: entry.topResultNameVi || "Kết quả gần nhất",
        topResultNameEn: entry.topResultNameEn || "",
        similarity: typeof entry.similarity === "number" ? entry.similarity : 0,
        mode: entry.mode || "image",
        category: entry.category || "all",
        timestamp: entry.timestamp || Date.now()
      };

      // Unshift & cap at MAX_HISTORY_ITEMS
      list.unshift(newRecord);
      if (list.length > CONFIG.MAX_HISTORY_ITEMS) {
        list = list.slice(0, CONFIG.MAX_HISTORY_ITEMS);
      }

      localStorage.setItem(CONFIG.STORAGE_HISTORY_KEY, JSON.stringify(list));
    } catch (e) {
      // Handle quota exceeded gracefully (e.g. data URL thumbnail too large)
      console.warn("Fruvia: LocalStorage quota exceeded or disabled", e);
    }
  },

  removeEntry(id) {
    try {
      let list = this.getHistory();
      list = list.filter(item => item.id !== id);
      localStorage.setItem(CONFIG.STORAGE_HISTORY_KEY, JSON.stringify(list));
    } catch (e) {
      console.warn("Fruvia: Failed to remove history item", e);
    }
  },

  clearHistory() {
    try {
      localStorage.removeItem(CONFIG.STORAGE_HISTORY_KEY);
    } catch (e) {
      console.warn("Fruvia: Failed to clear history", e);
    }
  }
};
