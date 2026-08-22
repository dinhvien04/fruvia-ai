/**
 * Fruvia AI — History UI Module
 * Handles rendering search history items and wire up clear/remove handlers.
 */

function renderHistoryUI() {
  const container = document.getElementById("history-items-container");
  if (!container) return;
  const history = typeof SearchHistory !== "undefined" ? SearchHistory.getHistory() : [];
  if (!history || history.length === 0) {
    container.innerHTML = `<span class="history-empty">Chưa có lịch sử tìm kiếm.</span>`;
    return;
  }
  container.innerHTML = history.map(item => `
    <div class="history-pill">
      ${item.thumbnailUrl && typeof Utils !== "undefined" && Utils.isSafeImageUrl(item.thumbnailUrl) ? `<img src="${item.thumbnailUrl}" alt="" class="history-thumb">` : ""}
      <span class="history-name">${typeof Utils !== "undefined" ? Utils.escapeHtml(item.topResultNameVi || item.filename) : item.filename}</span>
      <span class="history-time">${typeof Utils !== "undefined" ? Utils.formatRelativeTime(item.timestamp) : ""}</span>
      <button type="button" class="history-remove-btn" data-history-id="${item.id}" aria-label="Xóa">×</button>
    </div>
  `).join("");

  container.querySelectorAll(".history-remove-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-history-id");
      if (id && typeof SearchHistory !== "undefined") {
        SearchHistory.removeEntry(id);
        renderHistoryUI();
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const uploadForm = document.getElementById("upload-form");
  if (uploadForm) {
    uploadForm.addEventListener("submit", (e) => e.preventDefault());
  }

  const btnClearHistory = document.getElementById("btn-clear-history");
  if (btnClearHistory) {
    btnClearHistory.addEventListener("click", () => {
      if (typeof SearchHistory !== "undefined") {
        SearchHistory.clearHistory();
        renderHistoryUI();
      }
    });
  }

  renderHistoryUI();
});
