/**
 * Fruvia AI — Image Retrieval UI Logic
 */
document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const dropzonePrompt = document.getElementById("dropzone-prompt");
  const previewContainer = document.getElementById("preview-container");
  const previewImg = document.getElementById("preview-img");
  const btnChangeImage = document.getElementById("btn-change-image");
  const btnRemoveImage = document.getElementById("btn-remove-image");

  const topKSlider = document.getElementById("top-k-slider");
  const topKDisplay = document.getElementById("top-k-display");

  const btnSearch = document.getElementById("btn-search");
  const searchText = document.getElementById("search-text");
  const searchSpinner = document.getElementById("search-spinner");

  const backendStatusBadge = document.getElementById("backend-status");
  const statusText = document.getElementById("status-text");

  const errorBannerContainer = document.getElementById("error-banner-container");
  const warningBannerContainer = document.getElementById("warning-banner-container");
  const resultsHeader = document.getElementById("results-header");
  const resCount = document.getElementById("res-count");
  const resTime = document.getElementById("res-time");
  const resultsGrid = document.getElementById("results-grid");
  const initialEmptyState = document.getElementById("initial-empty-state");

  // State Variables
  let selectedFile = null;
  let isSearching = false;

  // ---------- Health Check Polling ----------
  async function checkBackendHealth() {
    try {
      const health = await ApiClient.getHealth();
      if (health.status === "ok") {
        backendStatusBadge.setAttribute("data-status", "online");
        statusText.textContent = "Backend Online";
      } else {
        backendStatusBadge.setAttribute("data-status", "degraded");
        statusText.textContent = "Backend Degraded";
      }
    } catch (err) {
      backendStatusBadge.setAttribute("data-status", "offline");
      statusText.textContent = "Backend Offline";
    }
  }

  // Initial check & interval polling (30s)
  checkBackendHealth();
  setInterval(checkBackendHealth, CONFIG.HEALTH_CHECK_INTERVAL_MS);

  // ---------- File Selection & Drag-and-Drop ----------
  function handleFileSelected(file) {
    if (!file) return;

    // Validate size
    if (file.size > CONFIG.MAX_UPLOAD_BYTES) {
      showErrorBanner(
        "File Too Large",
        `Selected image (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds the 10 MB limit.`
      );
      return;
    }

    // Validate extension
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (!CONFIG.ALLOWED_EXTENSIONS.includes(ext)) {
      showErrorBanner(
        "Unsupported File Extension",
        `File extension "${ext}" is not supported. Please select JPG, PNG, or WEBP.`
      );
      return;
    }

    clearBanners();
    selectedFile = file;

    // Show Preview
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImg.src = e.target.result;
      dropzonePrompt.style.display = "none";
      previewContainer.style.display = "flex";
      btnSearch.disabled = false;
    };
    reader.readAsDataURL(file);
  }

  function clearSelectedFile() {
    selectedFile = null;
    fileInput.value = "";
    previewImg.src = "";
    previewContainer.style.display = "none";
    dropzonePrompt.style.display = "block";
    btnSearch.disabled = true;
    clearBanners();
  }

  // Event Listeners for File Selection
  dropzone.addEventListener("click", (e) => {
    if (e.target !== btnChangeImage && e.target !== btnRemoveImage && !previewContainer.contains(e.target)) {
      fileInput.click();
    }
  });

  dropzone.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target === dropzone) {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelected(e.target.files[0]);
    }
  });

  btnChangeImage.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  btnRemoveImage.addEventListener("click", (e) => {
    e.stopPropagation();
    clearSelectedFile();
  });

  // Drag and Drop Events
  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files[0]) {
      handleFileSelected(dt.files[0]);
    }
  });

  // ---------- Top K Controls ----------
  topKSlider.addEventListener("input", (e) => {
    topKDisplay.textContent = e.target.value;
  });

  // ---------- Banner Renderers ----------
  function showErrorBanner(title, message) {
    errorBannerContainer.innerHTML = `
      <div class="alert-banner alert-banner-error" role="alert">
        <span class="alert-icon" aria-hidden="true">⚠️</span>
        <div class="alert-content">
          <h4>${Utils.escapeHtml(title)}</h4>
          <p>${Utils.escapeHtml(message)}</p>
        </div>
      </div>
    `;
    errorBannerContainer.style.display = "block";
  }

  function showWarningBanner(title, message) {
    warningBannerContainer.innerHTML = `
      <div class="alert-banner alert-banner-warning" role="alert">
        <span class="alert-icon" aria-hidden="true">⚠️</span>
        <div class="alert-content">
          <h4>${Utils.escapeHtml(title)}</h4>
          <p>${Utils.escapeHtml(message)}</p>
        </div>
      </div>
    `;
    warningBannerContainer.style.display = "block";
  }

  function clearBanners() {
    errorBannerContainer.innerHTML = "";
    errorBannerContainer.style.display = "none";
    warningBannerContainer.innerHTML = "";
    warningBannerContainer.style.display = "none";
  }

  // ---------- Search Submission ----------
  btnSearch.addEventListener("click", async () => {
    if (!selectedFile || isSearching) return;

    isSearching = true;
    btnSearch.disabled = true;
    searchSpinner.style.display = "inline-block";
    searchText.textContent = "Processing Vector Search...";
    clearBanners();

    const topK = parseInt(topKSlider.value, 10);

    try {
      const response = await ApiClient.retrieveImage(selectedFile, topK);
      renderResults(response);
    } catch (err) {
      const friendly = Utils.getFriendlyErrorMessage(err);
      showErrorBanner(friendly.title, friendly.message);
    } finally {
      isSearching = false;
      btnSearch.disabled = !selectedFile;
      searchSpinner.style.display = "none";
      searchText.textContent = "Find Similar Images";
    }
  });

  // ---------- Render Results Cards ----------
  function renderResults(response) {
    if (initialEmptyState) {
      initialEmptyState.style.display = "none";
    }

    const results = response.results || [];
    resCount.textContent = response.result_count || results.length;
    resTime.textContent = response.processing_time_ms || 0;
    resultsHeader.style.display = "flex";

    // Clear previous cards
    resultsGrid.innerHTML = "";

    if (results.length === 0) {
      resultsGrid.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          <div class="empty-state-icon" aria-hidden="true">🍃</div>
          <h3>No Similar Images Found</h3>
          <p>The vector search returned zero matches for your query image.</p>
        </div>
      `;
      return;
    }

    // Check top similarity score for low confidence warning (threshold < 0.55)
    const topResult = results[0];
    if (topResult && typeof topResult.similarity === "number" && topResult.similarity < 0.55) {
      showWarningBanner(
        "No close match was found in the current dataset.",
        "Không tìm thấy kết quả đủ tương đồng trong dữ liệu hiện tại."
      );
    }

    // Render cards
    results.forEach((item, index) => {
      const rank = index + 1;
      const canonicalClass = item.canonical_class || "unknown";
      const originalClass = item.original_class || "";
      const filename = item.filename || "unknown";
      const originalSplit = item.original_split || "unknown";
      const relativePath = item.relative_path || "";
      const similarityObj = Utils.formatSimilarity(item.similarity);

      // Card Element
      const card = document.createElement("article");
      card.className = "result-card";

      // Media Section: image_url or placeholder
      let mediaHtml = "";
      if (item.image_url) {
        mediaHtml = `
          <div class="card-media">
            <span class="rank-badge">#${rank}</span>
            <img src="${Utils.escapeHtml(item.image_url)}"
                 alt="Similar match for ${Utils.escapeHtml(canonicalClass)}"
                 loading="lazy"
                 onerror="this.onerror=null; this.parentNode.innerHTML='<span class=\\'rank-badge\\'>#${rank}</span><div class=\\'card-placeholder\\'><span class=\\'fruit-icon\\'>🍎</span><span class=\\'placeholder-class\\'>${Utils.escapeHtml(canonicalClass)}</span><span class=\\'placeholder-note\\'>Image load error</span></div>';">
          </div>
        `;
      } else {
        // Fallback placeholder when image_url is null
        mediaHtml = `
          <div class="card-media">
            <span class="rank-badge">#${rank}</span>
            <div class="card-placeholder">
              <span class="fruit-icon" aria-hidden="true">🍇</span>
              <span class="placeholder-class">${Utils.escapeHtml(canonicalClass)}</span>
              <span class="placeholder-note">Preview unavailable</span>
            </div>
          </div>
        `;
      }

      // Card Content
      card.innerHTML = `
        ${mediaHtml}
        <div class="card-body">
          <div>
            <h3 class="card-class-title">${Utils.escapeHtml(canonicalClass)}</h3>
            ${originalClass ? `<p class="card-class-original">Raw class: ${Utils.escapeHtml(originalClass)}</p>` : ""}
          </div>

          <div class="similarity-box ${similarityObj.levelClass}">
            <div class="similarity-header">
              <span class="similarity-label">Similarity</span>
              <span class="similarity-value">${similarityObj.percentageText}</span>
            </div>
            <div class="similarity-track" role="progressbar" aria-valuenow="${(item.similarity * 100).toFixed(1)}" aria-valuemin="-100" aria-valuemax="100">
              <div class="similarity-fill" style="width: ${similarityObj.visualWidth};"></div>
            </div>
          </div>

          <div class="card-details">
            <div><strong>File:</strong> ${Utils.escapeHtml(filename)}</div>
            <div><strong>Split:</strong> ${Utils.escapeHtml(originalSplit)}</div>
            ${relativePath ? `<div style="font-size:0.625rem; opacity:0.8;">${Utils.escapeHtml(relativePath)}</div>` : ""}
          </div>
        </div>
      `;

      resultsGrid.appendChild(card);
    });
  }
});
