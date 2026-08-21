/**
 * Fruvia AI — Accessible Result Detail Modal Module
 * Supports focus trap, ESC close, scroll locking, and clean VI/EN/Dataset metadata layout.
 */
const ResultModal = {
  modalEl: null,
  closeBtn: null,
  previousActiveElement: null,

  init() {
    this.modalEl = document.getElementById("image-modal");
    if (!this.modalEl) return;

    this.closeBtn = document.getElementById("modal-close");

    // Close button event
    if (this.closeBtn) {
      this.closeBtn.addEventListener("click", () => this.close());
    }

    // Backdrop click
    this.modalEl.addEventListener("click", (e) => {
      if (e.target === this.modalEl) {
        this.close();
      }
    });

    // Keyboard ESC & Tab focus trap
    document.addEventListener("keydown", (e) => {
      if (!this.isOpen()) return;

      if (e.key === "Escape") {
        e.preventDefault();
        this.close();
      }

      if (e.key === "Tab") {
        this.handleFocusTrap(e);
      }
    });
  },

  isOpen() {
    return this.modalEl && this.modalEl.style.display !== "none";
  },

  /**
   * Open modal with result data
   * @param {Object} item - Result item object from backend
   */
  open(item) {
    if (!this.modalEl || !item) return;

    this.previousActiveElement = document.activeElement;

    // 1. Image
    const mediaWrapper = document.getElementById("modal-media-wrapper");
    const safeUrl = Utils.getSafeImageUrl(item.image_url);
    if (mediaWrapper) {
      mediaWrapper.innerHTML = `
        <img src="${Utils.escapeHtml(safeUrl)}" alt="${Utils.escapeHtml(item.display_name_vi || item.display_name)}" class="modal-img">
      `;
    }

    // 2. Main Title & Display Names
    const titleEl = document.getElementById("modal-title");
    if (titleEl) {
      titleEl.textContent = item.display_name_vi || item.display_name || "Chi tiết mẫu trái cây";
    }

    const subTitleEl = document.getElementById("modal-subtitle");
    if (subTitleEl) {
      subTitleEl.textContent = item.display_name ? `English: ${item.display_name}` : "";
    }

    // 3. Similarity Meter
    const simBox = document.getElementById("modal-similarity-box");
    if (simBox) {
      const sim = Utils.formatSimilarity(item.similarity);
      simBox.innerHTML = `
        <div class="similarity-header">
          <span class="similarity-title">Mức độ tương đồng thị giác</span>
          <span class="similarity-score ${sim.levelClass}">${sim.percentageText}</span>
        </div>
        <div class="similarity-bar-bg">
          <div class="similarity-bar-fill ${sim.levelClass}" style="width: ${sim.visualWidth}"></div>
        </div>
        <div class="similarity-footnote">${sim.labelVi} dựa trên trích xuất đặc trưng DINOv2</div>
      `;
    }

    // 4. Primary Information
    const catEl = document.getElementById("modal-category");
    if (catEl) {
      const catMap = {
        fruit: "Trái cây",
        vegetable: "Rau củ",
        nut: "Hạt dinh dưỡng",
        seed: "Hạt giống",
        other: "Khác"
      };
      catEl.textContent = catMap[item.category] || item.category || "Trái cây";
    }

    const hitCountEl = document.getElementById("modal-hit-count");
    if (hitCountEl) {
      if (item.hit_count) {
        hitCountEl.textContent = `Xuất hiện ${item.hit_count} lần trong các mẫu gần nhất`;
        hitCountEl.style.display = "block";
      } else {
        hitCountEl.style.display = "none";
      }
    }

    // 5. Technical Data (Secondary Accordion / Section)
    const canonicalEl = document.getElementById("modal-canonical-class");
    if (canonicalEl) canonicalEl.textContent = item.canonical_class || "—";

    const originalEl = document.getElementById("modal-original-class");
    if (originalEl) originalEl.textContent = item.original_class || "—";

    const datasetEl = document.getElementById("modal-dataset");
    if (datasetEl) datasetEl.textContent = item.dataset_name || "—";

    const filenameEl = document.getElementById("modal-filename");
    if (filenameEl) filenameEl.textContent = item.filename || "—";

    // Show modal & prevent body scroll
    this.modalEl.style.display = "flex";
    document.body.style.overflow = "hidden";

    // Focus close button for accessibility
    if (this.closeBtn) {
      this.closeBtn.focus();
    }
  },

  close() {
    if (!this.modalEl) return;
    this.modalEl.style.display = "none";
    document.body.style.overflow = "";

    if (this.previousActiveElement && typeof this.previousActiveElement.focus === "function") {
      this.previousActiveElement.focus();
    }
  },

  handleFocusTrap(e) {
    const focusables = this.modalEl.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusables.length) return;

    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        last.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === last) {
        first.focus();
        e.preventDefault();
      }
    }
  }
};
