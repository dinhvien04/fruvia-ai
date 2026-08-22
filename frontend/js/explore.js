/**
 * Fruvia AI — Explore & Species Browsing Module
 * Loads real taxonomy and representative gallery images from GET /api/species.
 * Gracefully falls back to static data/species.json and placeholder icons on failure.
 * Supports client-side text search, category filters, and responsive grid.
 */
const ExplorePage = {
  speciesList: [],

  async init() {
    const gridEl = document.getElementById("species-grid");
    if (!gridEl) return;

    // Start the versioned static fallback immediately. Besides offline taxonomy,
    // it carries deterministic representative URLs for API/config outages.
    const staticSpeciesPromise = this.loadStaticSpecies();

    // Await public runtime configuration
    if (typeof RuntimeConfig !== "undefined" && typeof RuntimeConfig.load === "function") {
      await RuntimeConfig.load();
    }

    // Load species data from the API and enrich missing images from the bundled
    // deterministic fallback. This also supports an older/stale backend process.
    try {
      if (typeof ApiClient !== "undefined" && typeof ApiClient.listSpecies === "function") {
        const apiData = await ApiClient.listSpecies({ category: "all" });
        if (apiData && Array.isArray(apiData.items) && apiData.items.length > 0) {
          this.speciesList = apiData.items.map((item) => ({
            id: item.canonical_class,
            canonical_class: item.canonical_class,
            name_en: item.name_en,
            name_vi: item.name_vi,
            category: item.category,
            is_fruit: item.is_fruit,
            aliases: item.aliases || [],
            representative_image_url: item.representative_image_url || null
          }));
        }
      }
    } catch (apiErr) {
      console.warn("Fruvia: Could not load species from API, falling back to static species.json", apiErr);
    }

    const staticSpecies = await staticSpeciesPromise;
    if (!this.speciesList || this.speciesList.length === 0) {
      this.speciesList = staticSpecies;
    } else if (staticSpecies.length > 0) {
      const staticByClass = new Map(
        staticSpecies.map((item) => [item.canonical_class || item.id, item])
      );
      this.speciesList = this.speciesList.map((item) => {
        const fallback = staticByClass.get(item.canonical_class || item.id);
        return {
          ...item,
          representative_image_url:
            item.representative_image_url || fallback?.representative_image_url || null
        };
      });
    }

    if (!this.speciesList || this.speciesList.length === 0) {
      this.renderError(gridEl);
      return;
    }

    this.bindEvents();
    this.render();
  },

  async loadStaticSpecies() {
    try {
      const response = await fetch("data/species.json", { cache: "no-cache" });
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const rawJson = await response.json();
      if (!Array.isArray(rawJson)) throw new Error("Invalid species taxonomy payload");
      return rawJson.map((item) => ({
        ...item,
        canonical_class: item.id || item.canonical_class,
        representative_image_url: item.representative_image_url || null
      }));
    } catch (error) {
      console.warn("Fruvia: Could not load static species.json", error);
      return [];
    }
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
        const idMatch = (item.id || item.canonical_class || "").toLowerCase().includes(query);
        const nameEnMatch = (item.name_en || "").toLowerCase().includes(query);
        const nameViMatch = (item.name_vi || "").toLowerCase().includes(query);
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

    const getSafeUrl = typeof Utils !== "undefined" && typeof Utils.isSafeImageUrl === "function"
      ? (u) => (Utils.isSafeImageUrl(u) ? u : null)
      : (typeof KnowledgeUtils !== "undefined" && typeof KnowledgeUtils.getSafeHttpUrl === "function"
        ? KnowledgeUtils.getSafeHttpUrl
        : (u) => null);

    const escapeStr = typeof Utils !== "undefined" && typeof Utils.escapeHtml === "function"
      ? Utils.escapeHtml
      : (str) => String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

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
        const speciesId = item.id || item.canonical_class || "";

        const safeImgUrl = getSafeUrl(item.representative_image_url);
        const altText = item.name_vi || item.name_en || speciesId;

        const mediaHtml = safeImgUrl
          ? `<img src="${escapeStr(safeImgUrl)}" alt="${escapeStr(altText)}" loading="lazy" decoding="async" class="species-card-image">
             <img src="assets/svg/brand-mark.svg" alt="" class="species-placeholder-icon" style="display: none;" aria-hidden="true">`
          : `<img src="assets/svg/brand-mark.svg" alt="" class="species-placeholder-icon" aria-hidden="true">`;

        return `
        <article class="species-card card" tabindex="0" role="button" data-species-id="${escapeStr(speciesId)}">
          <div class="species-card-media">
            ${mediaHtml}
          </div>
          <div class="species-card-content">
            <h3 class="species-title-vi">${escapeStr(item.name_vi || item.name_en)}</h3>
            <span class="species-title-en">${escapeStr(item.name_en)}</span>
            <div class="species-meta-row">
              <span class="badge badge-neutral">${escapeStr(catLabel)}</span>
              ${aliasCount > 0 ? `<span class="species-alias-count">${aliasCount} biến thể nhãn</span>` : ""}
            </div>
          </div>
        </article>
      `;
      })
      .join("");

    // Attach card click navigation & image error fallbacks safely via DOM listeners
    gridEl.querySelectorAll(".species-card").forEach((card) => {
      const speciesId = card.getAttribute("data-species-id");
      const navigate = () => {
        if (speciesId) {
          window.location.href = `/species?id=${encodeURIComponent(speciesId.trim().toLowerCase())}`;
        }
      };
      card.addEventListener("click", navigate);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          navigate();
        }
      });

      // Handle image load error gracefully without inline event attributes
      const imgEl = card.querySelector(".species-card-image");
      const placeholderEl = card.querySelector(".species-placeholder-icon");
      if (imgEl && placeholderEl) {
        imgEl.addEventListener("error", () => {
          imgEl.style.display = "none";
          placeholderEl.style.display = "block";
        });
      }
    });
  },

  renderError(container) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <img src="assets/svg/error-state.svg" alt="" class="empty-state-icon" aria-hidden="true">
        <h3>Không thể tải dữ liệu danh mục</h3>
        <p>Vui lòng đảm bảo máy chủ hoặc tệp species.json đang hoạt động.</p>
      </div>
    `;
  }
};

document.addEventListener("DOMContentLoaded", () => ExplorePage.init());
