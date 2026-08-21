/**
 * Fruvia AI — Search Page Orchestrator Controller
 * Coordinates UploadManager, ApiClient, ResultsRenderer, ResultModal, and SearchHistory.
 */
document.addEventListener("DOMContentLoaded", () => {
  // Initialize Modules
  UploadManager.init({
    dropzoneId: "dropzone",
    fileInputId: "file-input",
    cameraInputId: "camera-input",
    previewContainerId: "preview-container",
    previewImgId: "preview-img"
  });

  ResultModal.init();

  // Controls DOM elements
  const btnSearch = document.getElementById("btn-search");
  const searchText = document.getElementById("search-text");
  const searchSpinner = document.getElementById("search-spinner");

  const modeSelect = document.getElementById("mode-select");
  const categorySelect = document.getElementById("category-select");
  const topKDisplay = document.getElementById("top-k-display");
  const topKValueInput = document.getElementById("top-k-value");
  const segmentedBtns = document.querySelectorAll(".segmented-btn");
  const advancedToggleBtn = document.getElementById("btn-toggle-options");
  const advancedOptionsContent = document.getElementById("advanced-options-content");

  let isSearching = false;

  // 1. Collapsible Advanced Search Options
  if (advancedToggleBtn && advancedOptionsContent) {
    advancedToggleBtn.addEventListener("click", () => {
      const isExpanded = advancedToggleBtn.getAttribute("aria-expanded") === "true";
      advancedToggleBtn.setAttribute("aria-expanded", !isExpanded);
      advancedOptionsContent.classList.toggle("is-expanded", !isExpanded);

      const icon = advancedToggleBtn.querySelector(".toggle-icon");
      if (icon) {
        icon.style.transform = isExpanded ? "rotate(0deg)" : "rotate(180deg)";
      }
    });
  }

  // Quick Camera & Gallery Buttons
  const btnQuickCamera = document.getElementById("btn-quick-camera");
  const btnQuickGallery = document.getElementById("btn-quick-gallery");
  const cameraInput = document.getElementById("camera-input");
  const fileInput = document.getElementById("file-input");

  if (btnQuickCamera && cameraInput) {
    btnQuickCamera.addEventListener("click", () => cameraInput.click());
  }
  if (btnQuickGallery && fileInput) {
    btnQuickGallery.addEventListener("click", () => fileInput.click());
  }

  // 2. Top-K Segmented Buttons
  segmentedBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      segmentedBtns.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-checked", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-checked", "true");
      const val = btn.getAttribute("data-value");
      if (topKValueInput) topKValueInput.value = val;
      if (topKDisplay) topKDisplay.textContent = val;
    });
  });

  // 3. Upload State Callbacks
  UploadManager.onSelected(() => {
    if (btnSearch) {
      btnSearch.disabled = false;
    }
  });

  UploadManager.onCleared(() => {
    if (btnSearch) {
      btnSearch.disabled = true;
    }
    const resultsHeader = document.getElementById("results-header");
    const compContainer = document.getElementById("comparison-container");
    const resultsGrid = document.getElementById("results-grid");

    if (resultsHeader) resultsHeader.style.display = "none";
    if (compContainer) compContainer.style.display = "none";
    if (resultsGrid) {
      resultsGrid.innerHTML = `
        <div id="initial-empty-state" class="empty-state">
          <img src="assets/svg/empty-search.svg" alt="" class="empty-state-icon" aria-hidden="true">
          <h3>Chưa có kết quả</h3>
          <p>Tải ảnh lên ở cột bên trái và bấm "Tìm hình ảnh tương đồng" để bắt đầu tra cứu.</p>
        </div>
      `;
    }
  });

  // 4. Perform Search Event
  if (btnSearch) {
    btnSearch.addEventListener("click", async () => {
      if (!UploadManager.selectedFile || isSearching) return;

      isSearching = true;
      btnSearch.disabled = true;
      if (searchSpinner) searchSpinner.style.display = "inline-block";
      if (searchText) searchText.textContent = "Đang tìm mẫu gần nhất...";

      const topK = parseInt(topKValueInput ? topKValueInput.value : "5", 10) || 5;
      const mode = modeSelect ? modeSelect.value : "image";
      const category = categorySelect ? categorySelect.value : "all";

      try {
        const response = await ApiClient.retrieveImage(
          UploadManager.selectedFile,
          topK,
          mode,
          category
        );

        // Render Results
        ResultsRenderer.render(response, UploadManager.previewDataUrl, { mode, category });

        // Save to History (if results exist) — stores public top-result gallery image URL, never private user query dataUrl
        if (response.results && response.results.length > 0) {
          const top = response.results[0];
          SearchHistory.addEntry({
            thumbnailUrl: top.image_url || top.thumbnail_url || null,
            filename: UploadManager.selectedFile.name,
            topResultNameVi: top.display_name_vi || top.display_name,
            topResultNameEn: top.display_name,
            similarity: top.similarity,
            mode,
            category,
            timestamp: Date.now()
          });
        }
      } catch (err) {
        UploadManager.notifyError(err);
      } finally {
        isSearching = false;
        btnSearch.disabled = !UploadManager.selectedFile;
        if (searchSpinner) searchSpinner.style.display = "none";
        if (searchText) searchText.textContent = "Tìm hình ảnh tương đồng";
      }
    });
  }
});
