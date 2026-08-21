/**
 * Fruvia AI — Search Results Renderer Module
 * Prioritizes Vietnamese display names, English subheadings, similarity meters ("Mức độ tương đồng"),
 * hit_count for class mode, query vs top match comparison, and low-similarity warnings.
 */
const ResultsRenderer = {
  render(data, queryDataUrl, currentOptions = {}) {
    const gridEl = document.getElementById("results-grid");
    const headerEl = document.getElementById("results-header");
    const countEl = document.getElementById("res-count");
    const timeEl = document.getElementById("res-time");
    const compContainer = document.getElementById("comparison-container");
    const warningContainer = document.getElementById("warning-banner-container");
    const errorContainer = document.getElementById("error-banner-container");

    if (!gridEl) return;

    // Clear previous banners & grid
    if (errorContainer) errorContainer.style.display = "none";
    if (warningContainer) warningContainer.style.display = "none";

    const results = data.results || [];
    const count = data.result_count || results.length;
    const timeMs = data.processing_time_ms ? data.processing_time_ms.toFixed(0) : "0";

    // 1. Update Header Stats
    if (headerEl) headerEl.style.display = "flex";
    if (countEl) countEl.textContent = count;
    if (timeEl) timeEl.textContent = timeMs;

    // 2. Handle Zero Results
    if (!results || results.length === 0) {
      this.renderEmptyState(gridEl);
      if (compContainer) compContainer.style.display = "none";
      return;
    }

    // 3. Render Query vs Top Result Comparison (#1 match)
    this.renderComparison(queryDataUrl, results[0], compContainer);

    // 4. Check for Low Similarity Warning (OOD / no close match)
    const topSimilarity = results[0]?.similarity || 0;
    if (topSimilarity < CONFIG.LOW_SIMILARITY_THRESHOLD && warningContainer) {
      this.renderLowSimilarityWarning(warningContainer, topSimilarity);
    }

    // 5. Render Result Cards Grid
    gridEl.innerHTML = "";
    results.forEach((item, index) => {
      const card = this.createCardElement(item, index + 1);
      gridEl.appendChild(card);
    });
  },

  createCardElement(item, rank) {
    const card = document.createElement("article");
    card.className = "result-card";
    card.setAttribute("tabindex", "0");
    card.setAttribute("role", "button");

    const safeUrl = Utils.getSafeImageUrl(item.image_url);
    const nameVi = Utils.escapeHtml(item.display_name_vi || item.display_name || "Trái cây");
    const nameEn = item.display_name ? Utils.escapeHtml(item.display_name) : "";
    const sim = Utils.formatSimilarity(item.similarity);

    // Category label mapping
    const catMap = {
      fruit: "Trái cây",
      vegetable: "Rau củ",
      nut: "Hạt dinh dưỡng",
      seed: "Hạt giống",
      other: "Khác"
    };
    const catLabel = catMap[item.category] || item.category || "Trái cây";

    // Hit count secondary label for class mode
    let hitCountHtml = "";
    if (item.hit_count) {
      hitCountHtml = `<span class="result-hit-count">Tìm thấy trong <strong>${item.hit_count}</strong> mẫu gần nhất</span>`;
    }

    card.innerHTML = `
      <div class="result-card-badge">#${rank}</div>
      <div class="result-card-media">
        <img src="${Utils.escapeHtml(safeUrl)}" alt="${nameVi}" loading="lazy" decoding="async" class="result-img">
      </div>
      <div class="result-card-content">
        <div class="result-card-header">
          <h3 class="result-title-vi">${nameVi}</h3>
          ${nameEn ? `<span class="result-title-en">${nameEn}</span>` : ""}
        </div>

        <div class="result-similarity-block">
          <div class="result-sim-header">
            <span class="result-sim-label">Mức độ tương đồng</span>
            <span class="result-sim-score ${sim.levelClass}">${sim.percentageText}</span>
          </div>
          <div class="result-sim-bar-bg">
            <div class="result-sim-bar-fill ${sim.levelClass}" style="width: ${sim.visualWidth}"></div>
          </div>
        </div>

        <div class="result-meta-row">
          <span class="badge badge-neutral">${Utils.escapeHtml(catLabel)}</span>
          ${hitCountHtml}
        </div>

        <button type="button" class="btn btn-secondary btn-sm btn-detail-trigger" aria-label="Xem chi tiết ${nameVi}">
          Xem chi tiết
        </button>
      </div>
    `;

    // Click or Keyboard to open detail modal
    const openDetails = () => ResultModal.open(item);

    card.addEventListener("click", openDetails);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openDetails();
      }
    });

    return card;
  },

  renderComparison(queryDataUrl, topMatch, container) {
    if (!container) return;
    if (!queryDataUrl || !topMatch) {
      container.style.display = "none";
      return;
    }

    const queryImg = document.getElementById("query-comparison-img");
    const topMedia = document.getElementById("top-match-media");

    if (queryImg) {
      queryImg.src = queryDataUrl;
    }

    if (topMedia) {
      const safeUrl = Utils.getSafeImageUrl(topMatch.image_url);
      const nameVi = Utils.escapeHtml(topMatch.display_name_vi || topMatch.display_name || "Trái cây");
      const sim = Utils.formatSimilarity(topMatch.similarity);

      topMedia.innerHTML = `
        <img src="${Utils.escapeHtml(safeUrl)}" alt="${nameVi}" class="top-match-img">
        <div class="top-match-overlay">
          <span class="top-match-name">${nameVi}</span>
          <span class="top-match-sim ${sim.levelClass}">${sim.percentageText}</span>
        </div>
      `;
    }

    container.style.display = "flex";
  },

  renderLowSimilarityWarning(container, topSimilarity) {
    const percent = (topSimilarity * 100).toFixed(1);
    container.innerHTML = `
      <div class="alert-banner alert-banner-warning" role="region" aria-label="Cảnh báo mức độ tương đồng">
        <img src="assets/svg/error-state.svg" alt="" class="alert-icon" aria-hidden="true">
        <div class="alert-content">
          <h4>Fruvia chưa tìm thấy kết quả đủ gần (${percent}%)</h4>
          <p>Ảnh có thể không thuộc các nhóm hiện được hỗ trợ hoặc chưa có mẫu tương tự trong dữ liệu gallery.</p>
          <div class="alert-actions" style="margin-top: 8px;">
            <button type="button" id="btn-low-sim-clear" class="btn btn-secondary btn-sm">Thử chọn ảnh khác</button>
          </div>
        </div>
      </div>
    `;

    const clearBtn = container.querySelector("#btn-low-sim-clear");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => UploadManager.clear());
    }

    container.style.display = "block";
  },

  renderEmptyState(container) {
    container.innerHTML = `
      <div class="empty-state">
        <img src="assets/svg/no-results.svg" alt="" class="empty-state-icon" aria-hidden="true">
        <h3>Chưa tìm thấy mẫu phù hợp</h3>
        <p>Thử tải lên một hình ảnh rõ nét hơn hoặc thay đổi danh mục lọc.</p>
      </div>
    `;
  }
};
