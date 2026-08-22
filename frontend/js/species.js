/**
 * Fruvia AI — Species Detail & Knowledge Integration Module
 * Sourced from GET /api/species/{canonical_class} and POST /api/knowledge/search
 * with graceful offline fallback, nutritional facts rendering, scientific taxonomy, and source provenance.
 */

const SpeciesPage = {
  knowledgeCache: new Map(),

  async init() {
    // Await public runtime configuration
    if (typeof RuntimeConfig !== "undefined" && typeof RuntimeConfig.load === "function") {
      await RuntimeConfig.load();
    }

    const container = document.getElementById("species-detail-container");
    if (!container) return;

    const params = new URLSearchParams(window.location.search);
    const speciesId = params.get("id");

    if (!speciesId || !speciesId.trim()) {
      this.renderNotFound(container, "Chưa cung cấp mã định danh loài.");
      return;
    }

    const canonicalClass = speciesId.trim().toLowerCase();

    // 1. Fetch species taxonomy details (Primary: GET /api/species/{canonicalClass}, Fallback: data/species.json)
    let speciesItem = null;
    try {
      if (typeof ApiClient !== "undefined" && typeof ApiClient.getSpecies === "function") {
        const apiData = await ApiClient.getSpecies(canonicalClass);
        if (apiData && apiData.canonical_class) {
          speciesItem = {
            id: apiData.canonical_class,
            name_en: apiData.name_en,
            name_vi: apiData.name_vi,
            category: apiData.category,
            is_fruit: apiData.is_fruit,
            aliases: apiData.aliases || []
          };
        }
      }
    } catch (err) {
      console.warn("Fruvia: API species lookup failed or returned error, attempting offline fallback", err);
      if (err.status === 404) {
        this.renderNotFound(container, `Không tìm thấy loài "${Utils.escapeHtml(canonicalClass)}" trong hệ thống danh mục.`);
        return;
      }
    }

    // Fallback to static data/species.json if API failed or was unreachable (offline mode)
    if (!speciesItem) {
      try {
        const response = await fetch("data/species.json");
        if (response.ok) {
          const list = await response.json();
          const found = list.find((s) => s.id === canonicalClass);
          if (found) {
            speciesItem = found;
          }
        }
      } catch (fallbackErr) {
        console.warn("Fruvia: Offline species.json fallback failed", fallbackErr);
      }
    }

    if (!speciesItem) {
      this.renderNotFound(container, `Không tìm thấy thông tin loài "${Utils.escapeHtml(canonicalClass)}".`);
      return;
    }

    // Update document title safely
    const titleVi = speciesItem.name_vi || speciesItem.name_en || canonicalClass;
    const titleEn = speciesItem.name_en || canonicalClass;
    document.title = `${titleVi} (${titleEn}) | Tri thức sinh học & Dinh dưỡng | Fruvia AI`;

    // 2. Render Base Species Card Skeleton (Immediate UX)
    this.renderBaseLayout(container, speciesItem);

    // 3. Fetch Knowledge in Parallel (Overview/Encyclopedia, Scientific Taxonomy, Nutrition)
    await this.loadKnowledgeSections(speciesItem);
  },

  renderNotFound(container, message) {
    container.innerHTML = `
      <div class="card empty-state">
        <img src="assets/svg/error-state.svg" alt="" class="empty-state-icon" aria-hidden="true">
        <h3>Không tìm thấy loài</h3>
        <p>${Utils.escapeHtml(message)}</p>
        <a href="/explore" class="btn btn-primary btn-sm" style="margin-top: 16px;">Về trang khám phá</a>
      </div>
    `;
  },

  renderBaseLayout(container, item) {
    const catMap = {
      fruit: "Trái cây",
      vegetable: "Rau củ",
      nut: "Hạt dinh dưỡng",
      seed: "Hạt giống",
      other: "Khác"
    };
    const catLabel = catMap[item.category] || item.category || "Trái cây";

    container.innerHTML = `
      <div class="species-detail-content">
        <!-- Header & Primary Taxonomy Information -->
        <div class="card species-header-card">
          <div class="species-detail-header">
            <div>
              <h1 class="species-detail-title">${Utils.escapeHtml(item.name_vi || item.name_en)}</h1>
              <p class="species-detail-subtitle">${Utils.escapeHtml(item.name_en || "")}</p>
            </div>
            <span class="badge badge-primary">${Utils.escapeHtml(catLabel)}</span>
          </div>

          <div class="species-detail-grid" style="margin-top: var(--space-lg);">
            <div class="species-info-card">
              <span class="species-info-label">Mã định danh loài (Canonical Key)</span>
              <strong class="species-info-value">${Utils.escapeHtml(item.id)}</strong>
            </div>
            <div class="species-info-card">
              <span class="species-info-label">Phân nhóm nông sản</span>
              <strong class="species-info-value">${item.is_fruit ? "Trái cây chuẩn hóa" : "Nông sản / Rau củ"}</strong>
            </div>
          </div>

          ${
            item.aliases && item.aliases.length > 0
              ? `
            <div class="species-aliases-section" style="margin-top: var(--space-lg);">
              <h4 class="species-aliases-title">Các biến thể nhãn trong dữ liệu huấn luyện</h4>
              <div class="species-aliases-list">
                ${item.aliases.map((a) => `<span class="badge badge-neutral">${Utils.escapeHtml(a)}</span>`).join("")}
              </div>
            </div>
          `
              : ""
          }
        </div>

        <!-- Section A: Tổng quan / Encyclopedia -->
        <section id="section-overview" class="card knowledge-section" aria-labelledby="heading-overview">
          <div class="knowledge-section-header">
            <h2 id="heading-overview" class="knowledge-section-title">
              <span class="section-icon">📖</span> Tổng quan & Đặc tính sinh học
            </h2>
          </div>
          <div id="overview-content" class="knowledge-section-body">
            <div class="knowledge-loading">
              <span class="spinner" aria-hidden="true"></span>
              <span>Đang tra cứu cơ sở tri thức bách khoa...</span>
            </div>
          </div>
        </section>

        <!-- Section B: Phân loại khoa học / Scientific Taxonomy -->
        <section id="section-taxonomy" class="card knowledge-section" aria-labelledby="heading-taxonomy">
          <div class="knowledge-section-header">
            <h2 id="heading-taxonomy" class="knowledge-section-title">
              <span class="section-icon">🔬</span> Phân loại khoa học & Danh pháp
            </h2>
          </div>
          <div id="taxonomy-content" class="knowledge-section-body">
            <div class="knowledge-loading">
              <span class="spinner" aria-hidden="true"></span>
              <span>Đang kiểm tra danh pháp thực vật học...</span>
            </div>
          </div>
        </section>

        <!-- Section C: Dinh dưỡng / Nutrition -->
        <section id="section-nutrition" class="card knowledge-section" aria-labelledby="heading-nutrition">
          <div class="knowledge-section-header">
            <h2 id="heading-nutrition" class="knowledge-section-title">
              <span class="section-icon">🥗</span> Thành phần dinh dưỡng (USDA / FDC)
            </h2>
          </div>
          <div id="nutrition-content" class="knowledge-section-body">
            <div class="knowledge-loading">
              <span class="spinner" aria-hidden="true"></span>
              <span>Đang tải thông số dinh dưỡng chuẩn hóa...</span>
            </div>
          </div>
        </section>

        <!-- Section D: Nguồn tham khảo / Sources Provenance -->
        <section id="section-sources" class="card knowledge-section" aria-labelledby="heading-sources">
          <div class="knowledge-section-header">
            <h2 id="heading-sources" class="knowledge-section-title">
              <span class="section-icon">📚</span> Nguồn tham khảo & Dẫn chứng
            </h2>
          </div>
          <div id="sources-content" class="knowledge-section-body">
            <div class="knowledge-loading">
              <span class="spinner" aria-hidden="true"></span>
              <span>Đang tổng hợp danh mục dẫn chứng...</span>
            </div>
          </div>
        </section>

        <!-- Navigation Actions -->
        <div class="species-detail-actions">
          <a href="/explore" class="btn btn-secondary btn-sm">← Xem toàn bộ danh mục</a>
          <a href="/search" class="btn btn-primary btn-sm">Nhận diện ảnh tương đồng →</a>
        </div>
      </div>
    `;
  },

  async loadKnowledgeSections(speciesItem) {
    const canonicalClass = speciesItem.id;
    const nameVi = speciesItem.name_vi || speciesItem.name_en || canonicalClass;
    const nameEn = speciesItem.name_en || canonicalClass;

    // Check in-memory session cache to avoid duplicate queries
    if (this.knowledgeCache.has(canonicalClass)) {
      const cached = this.knowledgeCache.get(canonicalClass);
      this.renderAllKnowledgeData(cached);
      return;
    }

    const overviewQuery = `Nguồn gốc, đặc điểm và thông tin tổng quan về ${nameVi} (${nameEn})`;
    const taxonomyQuery = `Tên khoa học, chi, họ và phân loại của ${nameVi} (${nameEn})`;
    const nutritionQuery = `Thành phần dinh dưỡng của ${nameVi} (${nameEn})`;

    try {
      // Execute 3 focused queries in parallel via searchKnowledge for type-specific precision
      const [overviewRes, taxonomyRes, nutritionRes] = await Promise.allSettled([
        ApiClient.searchKnowledge({
          query: overviewQuery,
          canonical_class: canonicalClass,
          document_type: "encyclopedia",
          limit: 5
        }),
        ApiClient.searchKnowledge({
          query: taxonomyQuery,
          canonical_class: canonicalClass,
          document_type: "taxonomy_scientific",
          limit: 5
        }),
        ApiClient.searchKnowledge({
          query: nutritionQuery,
          canonical_class: canonicalClass,
          document_type: "nutrition",
          limit: 5
        })
      ]);

      // Check if knowledge subsystem returned disabled (503)
      const isKnowledgeDisabled =
        (overviewRes.status === "rejected" && overviewRes.reason?.status === 503) ||
        (taxonomyRes.status === "rejected" && taxonomyRes.reason?.status === 503) ||
        (nutritionRes.status === "rejected" && nutritionRes.reason?.status === 503);

      if (isKnowledgeDisabled) {
        this.renderKnowledgeDisabledState();
        return;
      }

      const overviewData = overviewRes.status === "fulfilled" ? overviewRes.value : null;
      const taxonomyData = taxonomyRes.status === "fulfilled" ? taxonomyRes.value : null;
      const nutritionData = nutritionRes.status === "fulfilled" ? nutritionRes.value : null;

      // Fallback: If type-filtered searches yielded empty results, attempt general species knowledge query
      let generalDocs = [];
      const hasAnyDocs =
        (overviewData?.results?.length || 0) +
        (taxonomyData?.results?.length || 0) +
        (nutritionData?.results?.length || 0) > 0;

      if (!hasAnyDocs) {
        try {
          const genRes = await ApiClient.getSpeciesKnowledge(canonicalClass, 10);
          if (genRes && genRes.documents) {
            generalDocs = genRes.documents;
          }
        } catch (genErr) {
          console.warn("Fruvia: General species knowledge query failed", genErr);
        }
      }

      const aggregatedData = {
        overview: overviewData,
        taxonomy: taxonomyData,
        nutrition: nutritionData,
        generalDocs: generalDocs
      };

      this.knowledgeCache.set(canonicalClass, aggregatedData);
      this.renderAllKnowledgeData(aggregatedData);
    } catch (e) {
      console.error("Fruvia: Knowledge loading error", e);
      this.renderKnowledgeUnavailableState("Đã xảy ra sự cố khi tải tri thức.");
    }
  },

  renderKnowledgeDisabledState() {
    const disabledMsg = `
      <div class="knowledge-alert knowledge-alert-info">
        <span class="alert-icon">ℹ️</span>
        <div>
          <strong>Hệ thống tri thức AI đang bảo trì hoặc tạm thời tắt.</strong>
          <p>Thông tin danh mục chuẩn hóa vẫn hoạt động bình thường. Dữ liệu bách khoa và bảng dinh dưỡng sẽ sớm khả dụng.</p>
        </div>
      </div>
    `;
    const overviewEl = document.getElementById("overview-content");
    const taxonomyEl = document.getElementById("taxonomy-content");
    const nutritionEl = document.getElementById("nutrition-content");
    const sourcesEl = document.getElementById("sources-content");

    if (overviewEl) overviewEl.innerHTML = disabledMsg;
    if (taxonomyEl) taxonomyEl.innerHTML = disabledMsg;
    if (nutritionEl) nutritionEl.innerHTML = disabledMsg;
    if (sourcesEl) sourcesEl.innerHTML = `<p class="text-muted">Chưa có nguồn dẫn chứng khi dịch vụ tri thức bị tắt.</p>`;
  },

  renderKnowledgeUnavailableState(detail) {
    const errorMsg = `
      <div class="knowledge-alert knowledge-alert-warning">
        <span class="alert-icon">⚠️</span>
        <div>
          <strong>Chưa thể kết nối tới cơ sở tri thức BGE-M3 / Qdrant.</strong>
          <p>${Utils.escapeHtml(detail || "Vui lòng kiểm tra kết nối mạng và thử lại sau.")}</p>
        </div>
      </div>
    `;
    const overviewEl = document.getElementById("overview-content");
    const taxonomyEl = document.getElementById("taxonomy-content");
    const nutritionEl = document.getElementById("nutrition-content");
    const sourcesEl = document.getElementById("sources-content");

    if (overviewEl) overviewEl.innerHTML = errorMsg;
    if (taxonomyEl) taxonomyEl.innerHTML = errorMsg;
    if (nutritionEl) nutritionEl.innerHTML = errorMsg;
    if (sourcesEl) sourcesEl.innerHTML = `<p class="text-muted">Không có dẫn chứng khả dụng.</p>`;
  },

  renderAllKnowledgeData(data) {
    const allDocs = [];

    // Collect all documents for sources section
    if (data.overview?.results) allDocs.push(...data.overview.results);
    if (data.taxonomy?.results) allDocs.push(...data.taxonomy.results);
    if (data.nutrition?.results) allDocs.push(...data.nutrition.results);
    if (data.generalDocs) allDocs.push(...data.generalDocs);

    // 1. Render Overview
    this.renderOverviewSection(data.overview, data.generalDocs);

    // 2. Render Scientific Taxonomy
    this.renderTaxonomySection(data.taxonomy, data.generalDocs);

    // 3. Render Nutrition Facts
    this.renderNutritionSection(data.nutrition, data.generalDocs);

    // 4. Render Sources Provenance
    this.renderSourcesSection(allDocs);
  },

  renderOverviewSection(overviewData, generalDocs) {
    const container = document.getElementById("overview-content");
    if (!container) return;

    let docs = overviewData?.results || [];
    if (!docs.length && generalDocs) {
      docs = generalDocs.filter((d) => d.document_type === "encyclopedia" || d.document_type === "general");
    }

    if (!docs.length) {
      container.innerHTML = `
        <div class="knowledge-empty">
          <p>Chưa có dữ liệu tổng quan bách khoa cho loài này trong cơ sở tri thức.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = docs
      .map((doc) => {
        const title = Utils.escapeHtml(doc.title || "Tổng quan");
        const text = Utils.escapeHtml(doc.text || "");
        const sourceName = Utils.escapeHtml(doc.source || doc.source_dataset || "Wikipedia");
        const safeUrl = this.getSafeSourceUrl(doc.source_url);

        return `
        <article class="knowledge-doc-card">
          <h3 class="knowledge-doc-title">${title}</h3>
          <div class="knowledge-doc-text">${text}</div>
          <div class="knowledge-doc-footer">
            <span class="knowledge-source-badge">Nguồn: ${sourceName}</span>
            ${
              safeUrl
                ? `<a href="${Utils.escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="knowledge-source-link">Xem tài liệu gốc ↗</a>`
                : ""
            }
          </div>
        </article>
      `;
      })
      .join("");
  },

  renderTaxonomySection(taxonomyData, generalDocs) {
    const container = document.getElementById("taxonomy-content");
    if (!container) return;

    let docs = taxonomyData?.results || [];
    if (!docs.length && generalDocs) {
      docs = generalDocs.filter((d) => d.document_type === "taxonomy_scientific" || d.taxonomy || d.scientific_name);
    }

    // Extract best scientific structure
    let scientificName = null;
    let taxObj = null;
    let docSource = null;
    let docUrl = null;
    let docSnippet = null;

    for (const doc of docs) {
      if (doc.scientific_name && !scientificName) {
        scientificName = doc.scientific_name;
      }
      if (doc.taxonomy && typeof doc.taxonomy === "object" && !taxObj) {
        taxObj = doc.taxonomy;
      }
      if (doc.source && !docSource) {
        docSource = doc.source;
      }
      if (doc.source_url && !docUrl) {
        docUrl = doc.source_url;
      }
      if (doc.text && !docSnippet) {
        docSnippet = doc.text;
      }
    }

    if (!scientificName && !taxObj && !docs.length) {
      container.innerHTML = `
        <div class="knowledge-empty">
          <p>Chưa có thông tin phân loại thực vật học chi tiết cho loài này.</p>
        </div>
      `;
      return;
    }

    const safeUrl = this.getSafeSourceUrl(docUrl);
    const sourceLabel = Utils.escapeHtml(docSource || "Wikidata Taxon / GBIF");

    let taxonomyRowsHtml = "";
    if (taxObj) {
      const fieldLabels = {
        kingdom: "Giới (Kingdom)",
        clade: "Nhánh (Clade)",
        order: "Bộ (Order)",
        family: "Họ (Family)",
        subfamily: "Phân họ (Subfamily)",
        genus: "Chi (Genus)",
        species: "Loài (Species)"
      };

      for (const [key, label] of Object.entries(fieldLabels)) {
        if (taxObj[key]) {
          taxonomyRowsHtml += `
            <div class="taxonomy-grid-item">
              <span class="taxonomy-key">${Utils.escapeHtml(label)}</span>
              <span class="taxonomy-val">${Utils.escapeHtml(taxObj[key])}</span>
            </div>
          `;
        }
      }
    }

    container.innerHTML = `
      <div class="taxonomy-display-card">
        ${
          scientificName
            ? `
          <div class="scientific-name-block">
            <span class="scientific-label">Danh pháp khoa học (Latin)</span>
            <div class="scientific-name-val"><em>${Utils.escapeHtml(scientificName)}</em></div>
          </div>
        `
            : ""
        }

        ${taxonomyRowsHtml ? `<div class="taxonomy-grid">${taxonomyRowsHtml}</div>` : ""}

        ${docSnippet ? `<div class="knowledge-doc-text" style="margin-top: var(--space-md);">${Utils.escapeHtml(docSnippet)}</div>` : ""}

        <div class="knowledge-doc-footer" style="margin-top: var(--space-md);">
          <span class="knowledge-source-badge">Nguồn phân loại: ${sourceLabel}</span>
          ${
            safeUrl
              ? `<a href="${Utils.escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="knowledge-source-link">Dẫn chứng phân loại ↗</a>`
              : ""
          }
        </div>
      </div>
    `;
  },

  renderNutritionSection(nutritionData, generalDocs) {
    const container = document.getElementById("nutrition-content");
    if (!container) return;

    let docs = nutritionData?.results || [];
    if (!docs.length && generalDocs) {
      docs = generalDocs.filter((d) => d.document_type === "nutrition" || d.nutrients);
    }

    // Filter docs that actually have nutrient dictionaries
    const nutrientDocs = docs.filter((d) => d.nutrients && typeof d.nutrients === "object" && Object.keys(d.nutrients).length > 0);

    if (!nutrientDocs.length) {
      container.innerHTML = `
        <div class="knowledge-empty">
          <p>Chưa có bảng thành phần dinh dưỡng chi tiết từ USDA/FDC cho loài này.</p>
        </div>
      `;
      return;
    }

    // Render distinct USDA food records without fabricated averaging
    container.innerHTML = nutrientDocs
      .map((doc) => {
        const title = Utils.escapeHtml(doc.title || "Bảng giá trị dinh dưỡng");
        const sourceName = Utils.escapeHtml(doc.source || doc.source_dataset || "USDA FoodData Central");
        const safeUrl = this.getSafeSourceUrl(doc.source_url);
        const nutrients = doc.nutrients || {};

        let nutrientItemsHtml = "";
        for (const [nutrientName, valObj] of Object.entries(nutrients)) {
          let amountStr = "—";
          let unitStr = "";

          if (valObj !== null && typeof valObj === "object") {
            if (valObj.amount !== undefined && valObj.amount !== null) {
              const num = Number(valObj.amount);
              amountStr = isNaN(num) ? String(valObj.amount) : num % 1 === 0 ? num.toString() : num.toFixed(3);
            }
            if (valObj.unit) {
              unitStr = String(valObj.unit);
            }
          } else if (typeof valObj === "number" || typeof valObj === "string") {
            amountStr = String(valObj);
          }

          nutrientItemsHtml += `
            <div class="nutrient-item">
              <span class="nutrient-name">${Utils.escapeHtml(nutrientName)}</span>
              <span class="nutrient-amount"><strong>${Utils.escapeHtml(amountStr)}</strong> <small>${Utils.escapeHtml(unitStr)}</small></span>
            </div>
          `;
        }

        return `
        <div class="nutrition-record-card">
          <div class="nutrition-record-header">
            <h3 class="nutrition-record-title">${title}</h3>
            <span class="badge badge-neutral">100g tiêu chuẩn</span>
          </div>

          <div class="nutrient-grid">
            ${nutrientItemsHtml}
          </div>

          <div class="knowledge-doc-footer" style="margin-top: var(--space-md);">
            <span class="knowledge-source-badge">Nguồn: ${sourceName}</span>
            ${
              safeUrl
                ? `<a href="${Utils.escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="knowledge-source-link">Hồ sơ USDA FDC gốc ↗</a>`
                : ""
            }
          </div>
        </div>
      `;
      })
      .join("");
  },

  renderSourcesSection(allDocs) {
    const container = document.getElementById("sources-content");
    if (!container) return;

    if (!allDocs || !allDocs.length) {
      container.innerHTML = `
        <div class="knowledge-empty">
          <p>Chưa có danh mục nguồn tham khảo trực tiếp.</p>
        </div>
      `;
      return;
    }

    // Deduplicate by document_id or title
    const seen = new Set();
    const uniqueDocs = [];

    for (const doc of allDocs) {
      const key = (doc.document_id || doc.title || "").toLowerCase().trim();
      if (key && !seen.has(key)) {
        seen.add(key);
        uniqueDocs.push(doc);
      }
    }

    container.innerHTML = `
      <ul class="sources-list">
        ${uniqueDocs
          .map((doc) => {
            const title = Utils.escapeHtml(doc.title || "Tài liệu không tiêu đề");
            const source = Utils.escapeHtml(doc.source || doc.source_dataset || "Dữ liệu tri thức");
            const lang = doc.language ? `<span class="source-lang-badge">${Utils.escapeHtml(doc.language.toUpperCase())}</span>` : "";
            const safeUrl = this.getSafeSourceUrl(doc.source_url);

            return `
            <li class="source-list-item">
              <div class="source-item-meta">
                <strong>${title}</strong>
                <span class="source-meta-sub">${source} ${lang}</span>
              </div>
              ${
                safeUrl
                  ? `<a href="${Utils.escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm source-action-btn">Mở liên kết ↗</a>`
                  : `<span class="badge badge-neutral">Trích lục nội bộ</span>`
              }
            </li>
          `;
          })
          .join("")}
      </ul>
    `;
  },

  /**
   * Safe URL protocol validator ensuring only http: and https: links are accepted.
   * Rejects javascript:, data:, file:, etc.
   */
  getSafeSourceUrl(url) {
    if (!url || typeof url !== "string") return null;
    const trimmed = url.trim();
    if (!trimmed) return null;

    try {
      const parsed = new URL(trimmed);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        return parsed.href;
      }
    } catch {
      return null;
    }
    return null;
  }
};

document.addEventListener("DOMContentLoaded", () => SpeciesPage.init());

