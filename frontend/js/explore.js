/**
 * Fruvia AI — Explore & Species Browsing Module
 * Loads real taxonomy data from frontend/data/species.json.
 * Supports text search, category filters, and responsive grid.
 */
const ExplorePage = {
  speciesList: [],

  async init() {
    // Load public runtime configuration
    if (typeof RuntimeConfig !== "undefined" && typeof RuntimeConfig.load === "function") {
      RuntimeConfig.load();
    }

    const gridEl = document.getElementById("species-grid");
    if (!gridEl) return;

    // Load static ground-truth species data
    try {
      const response = await fetch("data/species.json");
      if (!response.ok) throw new Error("Failed to load species taxonomy");
      this.speciesList = await response.json();
    } catch (e) {
      console.warn("Fruvia: Could not load species.json", e);
      this.renderError(gridEl);
      return;
    }

    this.bindEvents();
    this.render();
  },

  bindEvents() {
    const searchInput = document.getElementById("explore-search-input");
    const categorySelect = document.getElementById("explore-category-select");

    if (searchInput) {
      searchInput.addEventListener("input", () => this.render());
    }

    if (categorySelect) {
      categorySelect.addEventListener("change", () => this.render());
    }
  },

  filterSpecies() {
    const searchInput = document.getElementById("explore-search-input");
    const categorySelect = document.getElementById("explore-category-select");

    const query = searchInput ? searchInput.value.trim().toLowerCase() : "";
    const category = categorySelect ? categorySelect.value : "all";

    return this.speciesList.filter((item) => {
      // 1. Category Filter
      if (category !== "all" && item.category !== category) {
        return false;
      }

      // 2. Text Search
      if (query) {
        const idMatch = item.id.toLowerCase().includes(query);
        const nameEnMatch = item.name_en.toLowerCase().includes(query);
        const nameViMatch = item.name_vi.toLowerCase().includes(query);
        const aliasMatch = item.aliases && item.aliases.some((a) => a.toLowerCase().includes(query));

        return idMatch || nameEnMatch || nameViMatch || aliasMatch;
      }

      return true;
    });
  },

  render() {
    const gridEl = document.getElementById("species-grid");
    const countEl = document.getElementById("explore-count");

    if (!gridEl) return;

    const items = this.filterSpecies();

    if (countEl) {
      countEl.textContent = `${items.length} loài`;
    }

    if (items.length === 0) {
      gridEl.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          <img src="assets/svg/no-results.svg" alt="" class="empty-state-icon" aria-hidden="true">
          <h3>Không tìm thấy loài phù hợp</h3>
          <p>Thử tìm kiếm với từ khóa khác hoặc bỏ chọn bộ lọc danh mục.</p>
        </div>
      `;
      return;
    }

    gridEl.innerHTML = items
      .map((item) => {
        const catMap = {
          fruit: "Trái cây",
          vegetable: "Rau củ",
          nut: "Hạt dinh dưỡng",
          seed: "Hạt giống",
          other: "Khác"
        };
        const catLabel = catMap[item.category] || item.category || "Trái cây";
        const aliasCount = item.aliases ? item.aliases.length : 0;

        return `
        <article class="species-card card" tabindex="0" role="button" data-species-id="${item.id}">
          <div class="species-card-media">
            <img src="assets/svg/brand-mark.svg" alt="" class="species-placeholder-icon" aria-hidden="true">
          </div>
          <div class="species-card-content">
            <h3 class="species-title-vi">${Utils.escapeHtml(item.name_vi)}</h3>
            <span class="species-title-en">${Utils.escapeHtml(item.name_en)}</span>
            <div class="species-meta-row">
              <span class="badge badge-neutral">${Utils.escapeHtml(catLabel)}</span>
              ${aliasCount > 0 ? `<span class="species-alias-count">${aliasCount} biến thể nhãn</span>` : ""}
            </div>
          </div>
        </article>
      `;
      })
      .join("");

    gridEl.querySelectorAll(".species-card").forEach((card) => {
      const speciesId = card.getAttribute("data-species-id");
      const navigate = () => {
        if (speciesId) window.location.href = `species.html?id=${speciesId}`;
      };
      card.addEventListener("click", navigate);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          navigate();
        }
      });
    });
  },

  renderError(container) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <img src="assets/svg/error-state.svg" alt="" class="empty-state-icon" aria-hidden="true">
        <h3>Không thể tải dữ liệu danh mục</h3>
        <p>Vui lòng đảm bảo tệp species.json đã được tạo thành công.</p>
      </div>
    `;
  }
};

document.addEventListener("DOMContentLoaded", () => ExplorePage.init());
