/**
 * Fruvia AI — Image Retrieval UI Controller
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

  const modeSelect = document.getElementById("mode-select");
  const categorySelect = document.getElementById("category-select");
  const topKDisplay = document.getElementById("top-k-display");
  const topKValueInput = document.getElementById("top-k-value");
  const segmentedBtns = document.querySelectorAll(".segmented-btn");

  const btnSearch = document.getElementById("btn-search");
  const searchText = document.getElementById("search-text");
  const searchSpinner = document.getElementById("search-spinner");

  const comparisonContainer = document.getElementById("comparison-container");
  const queryComparisonImg = document.getElementById("query-comparison-img");
  const topMatchMedia = document.getElementById("top-match-media");

  const errorBannerContainer = document.getElementById("error-banner-container");
  const warningBannerContainer = document.getElementById("warning-banner-container");
  const resultsHeader = document.getElementById("results-header");
  const resCount = document.getElementById("res-count");
  const resTime = document.getElementById("res-time");
  const resultsGrid = document.getElementById("results-grid");
  const initialEmptyState = document.getElementById("initial-empty-state");

  // Modal Elements
  const imageModal = document.getElementById("image-modal");
  const modalClose = document.getElementById("modal-close");
  const modalMediaWrapper = document.getElementById("modal-media-wrapper");
  const modalTitle = document.getElementById("modal-title");
  const modalCanonicalClass = document.getElementById("modal-canonical-class");
  const modalOriginalClass = document.getElementById("modal-original-class");
  const modalDataset = document.getElementById("modal-dataset");
  const modalFilename = document.getElementById("modal-filename");
  const modalSimilarityBox = document.getElementById("modal-similarity-box");
  const modalKnowledgeContainer = document.getElementById("modal-knowledge-container");

  // State Variables
  let selectedFile = null;
  let queryDataUrl = null;
  let isSearching = false;
  let lastFocusedElement = null;

  // ---------- Top-K Segmented Selection ----------
  segmentedBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      segmentedBtns.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-checked", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-checked", "true");
      const val = btn.getAttribute("data-value");
      topKValueInput.value = val;
      topKDisplay.textContent = val;
    });
  });

  // ---------- File Selection & Drag/Drop ----------
  function handleFileSelected(file) {
    if (!file) return;

    if (file.size > CONFIG.MAX_UPLOAD_BYTES) {
      showErrorBanner(
        "Tệp quá lớn",
        `Hình ảnh đã chọn (${(file.size / (1024 * 1024)).toFixed(1)} MB) vượt quá giới hạn 10 MB.`
      );
      return;
    }

    let ext = "";
    if (file.name && file.name.includes(".")) {
      ext = "." + file.name.split(".").pop().toLowerCase();
    } else if (file.type) {
      const mimeExt = file.type.split("/")[1]?.toLowerCase();
      if (mimeExt) ext = mimeExt === "jpeg" ? ".jpg" : "." + mimeExt;
    }

    if (!CONFIG.ALLOWED_EXTENSIONS.includes(ext)) {
      showErrorBanner(
        "Định dạng không được hỗ trợ",
        `Định dạng tệp "${ext || "không xác định"}" không được hỗ trợ. Vui lòng chọn JPG, PNG hoặc WEBP.`
      );
      return;
    }

    clearBanners();
    selectedFile = file;

    const reader = new FileReader();
    reader.onload = (e) => {
      queryDataUrl = e.target.result;
      previewImg.src = queryDataUrl;
      dropzonePrompt.style.display = "none";
      previewContainer.style.display = "flex";
      btnSearch.disabled = false;
    };
    reader.readAsDataURL(file);
  }

  function clearSelectedFile() {
    selectedFile = null;
    queryDataUrl = null;
    fileInput.value = "";
    previewImg.src = "";
    previewContainer.style.display = "none";
    dropzonePrompt.style.display = "block";
    btnSearch.disabled = true;
    comparisonContainer.style.display = "none";
    clearBanners();
  }

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

  // ---------- Paste Event (Ctrl+V) ----------
  window.addEventListener("paste", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;

    const clipboardData = e.clipboardData || (e.originalEvent && e.originalEvent.clipboardData);
    if (!clipboardData) return;

    if (clipboardData.files && clipboardData.files.length > 0) {
      for (let i = 0; i < clipboardData.files.length; i++) {
        const file = clipboardData.files[i];
        if (file.type && file.type.startsWith("image/")) {
          e.preventDefault();
          handleFileSelected(file);
          return;
        }
      }
    }

    const items = clipboardData.items || [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type && item.type.startsWith("image/")) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (!blob) continue;

        let ext = "png";
        if (blob.type === "image/jpeg" || blob.type === "image/jpg") ext = "jpg";
        else if (blob.type === "image/webp") ext = "webp";

        const fileName = `pasted-image-${Date.now()}.${ext}`;
        const pastedFile = new File([blob], fileName, { type: blob.type || `image/${ext}` });
        handleFileSelected(pastedFile);
        return;
      }
    }
  });

  // ---------- Error & Warning Banners ----------
  function showErrorBanner(title, message) {
    errorBannerContainer.innerHTML = "";
    const banner = document.createElement("div");
    banner.className = "alert-banner alert-banner-error";
    banner.setAttribute("role", "alert");

    const iconImg = document.createElement("img");
    iconImg.src = "assets/svg/error-state.svg";
    iconImg.className = "alert-icon";
    iconImg.alt = "";

    const content = document.createElement("div");
    content.className = "alert-content";

    const h4 = document.createElement("h4");
    h4.textContent = title;
    const p = document.createElement("p");
    p.textContent = message;

    content.appendChild(h4);
    content.appendChild(p);
    banner.appendChild(iconImg);
    banner.appendChild(content);
    errorBannerContainer.appendChild(banner);
    errorBannerContainer.style.display = "block";
  }

  function showWarningBanner(title, message) {
    warningBannerContainer.innerHTML = "";
    const banner = document.createElement("div");
    banner.className = "alert-banner alert-banner-warning";
    banner.setAttribute("role", "alert");

    const iconImg = document.createElement("img");
    iconImg.src = "assets/svg/no-results.svg";
    iconImg.className = "alert-icon";
    iconImg.alt = "";

    const content = document.createElement("div");
    content.className = "alert-content";

    const h4 = document.createElement("h4");
    h4.textContent = title;
    const p = document.createElement("p");
    p.textContent = message;

    content.appendChild(h4);
    content.appendChild(p);
    banner.appendChild(iconImg);
    banner.appendChild(content);
    warningBannerContainer.appendChild(banner);
    warningBannerContainer.style.display = "block";
  }

  function clearBanners() {
    errorBannerContainer.innerHTML = "";
    errorBannerContainer.style.display = "none";
    warningBannerContainer.innerHTML = "";
    warningBannerContainer.style.display = "none";
  }

  // ---------- Search Execution ----------
  btnSearch.addEventListener("click", async () => {
    if (!selectedFile || isSearching) return;

    isSearching = true;
    btnSearch.disabled = true;
    searchSpinner.style.display = "inline-block";
    searchText.textContent = "Đang phân tích hình ảnh...";
    clearBanners();

    const topK = parseInt(topKValueInput.value, 10) || 5;
    const mode = modeSelect ? modeSelect.value : "image";
    const category = categorySelect ? categorySelect.value : "all";

    try {
      const response = await ApiClient.retrieveImage(selectedFile, topK, mode, category);
      renderResults(response);
    } catch (err) {
      const friendly = Utils.getFriendlyErrorMessage(err);
      showErrorBanner(friendly.title, friendly.message);
    } finally {
      isSearching = false;
      btnSearch.disabled = !selectedFile;
      searchSpinner.style.display = "none";
      searchText.textContent = "Tìm hình ảnh tương đồng";
    }
  });

  // ---------- Render Search Results ----------
  function renderResults(response) {
    if (initialEmptyState) {
      initialEmptyState.style.display = "none";
    }

    const results = response.results || [];
    resCount.textContent = String(response.result_count || results.length);
    resTime.textContent = String(response.processing_time_ms || 0);
    resultsHeader.style.display = "flex";

    if (queryDataUrl) {
      queryComparisonImg.src = queryDataUrl;
      comparisonContainer.style.display = "flex";
    }

    resultsGrid.innerHTML = "";
    topMatchMedia.innerHTML = "";

    if (results.length === 0) {
      const emptyDiv = document.createElement("div");
      emptyDiv.className = "empty-state";

      const iconImg = document.createElement("img");
      iconImg.src = "assets/svg/empty-search.svg";
      iconImg.className = "empty-state-icon";
      iconImg.alt = "";

      const h3 = document.createElement("h3");
      h3.textContent = "Không tìm thấy kết quả tương đồng";
      const p = document.createElement("p");
      p.textContent = "Không có mẫu trái cây nào phù hợp với bộ lọc và ảnh truy vấn của bạn.";

      emptyDiv.appendChild(iconImg);
      emptyDiv.appendChild(h3);
      emptyDiv.appendChild(p);
      resultsGrid.appendChild(emptyDiv);
      return;
    }

    const topResult = results[0];
    const topSim = topResult && typeof topResult.similarity === "number" ? topResult.similarity : 0;

    if (topSim < CONFIG.LOW_SIMILARITY_THRESHOLD) {
      showWarningBanner(
        "Kết quả có độ tương đồng thấp",
        "Ảnh truy vấn có thể nằm ngoài phạm vi dữ liệu hiện tại."
      );
    }

    if (topResult) {
      const displayNameVi = topResult.display_name_vi;
      const displayNameEn = topResult.display_name || topResult.canonical_class;
      const displayName = displayNameVi ? `${displayNameVi} (${displayNameEn})` : displayNameEn;

      if (Utils.isSafeImageUrl(topResult.image_url)) {
        const topImg = document.createElement("img");
        topImg.src = topResult.image_url;
        topImg.alt = `Top match: ${displayName}`;
        topMatchMedia.appendChild(topImg);
      }
    }

    // Render Cards
    results.forEach((item, index) => {
      const rank = index + 1;
      const canonicalClass = item.canonical_class || "unknown";
      const originalClass = item.original_class || "unknown";
      const displayNameVi = item.display_name_vi;
      const displayNameEn = item.display_name || canonicalClass;
      const displayName = displayNameVi ? `${displayNameVi} (${displayNameEn})` : displayNameEn;
      const datasetName = item.dataset_name || "Fruits-360";
      const similarityObj = Utils.formatSimilarity(item.similarity);

      const card = document.createElement("article");
      card.className = "result-card";

      // Card Header & Image
      const headerDiv = document.createElement("div");
      headerDiv.className = "card-header";

      const rankBadge = document.createElement("span");
      rankBadge.className = "rank-badge";
      rankBadge.textContent = `#${rank}`;
      headerDiv.appendChild(rankBadge);

      const mediaDiv = document.createElement("div");
      mediaDiv.className = "card-media";

      if (Utils.isSafeImageUrl(item.image_url)) {
        const img = document.createElement("img");
        img.setAttribute("loading", "lazy");
        img.setAttribute("decoding", "async");
        img.alt = `Mẫu tương đồng: ${displayName}`;
        img.src = item.image_url;
        mediaDiv.appendChild(img);
      }
      headerDiv.appendChild(mediaDiv);

      // Card Body
      const bodyDiv = document.createElement("div");
      bodyDiv.className = "card-body";

      const titleEl = document.createElement("h3");
      titleEl.className = "card-title";
      titleEl.textContent = displayName;

      const subtitleEl = document.createElement("p");
      subtitleEl.className = "card-subtitle";
      subtitleEl.textContent = `Nhãn gốc: ${originalClass} · ${datasetName}`;

      bodyDiv.appendChild(titleEl);
      bodyDiv.appendChild(subtitleEl);

      // Similarity Bar
      const simBox = document.createElement("div");
      simBox.className = `similarity-box ${similarityObj.levelClass}`;
      simBox.innerHTML = `
        <div class="similarity-header">
          <span class="similarity-label">Độ tương đồng</span>
          <span class="similarity-value">${similarityObj.percentageText}</span>
        </div>
        <div class="similarity-track" role="progressbar" aria-valuenow="${(item.similarity * 100).toFixed(1)}" aria-valuemin="0" aria-valuemax="100">
          <div class="similarity-fill" style="width: ${similarityObj.visualWidth};"></div>
        </div>
      `;
      bodyDiv.appendChild(simBox);

      // Detail Button CTA
      const actionsDiv = document.createElement("div");
      actionsDiv.className = "card-actions";
      const btnDetail = document.createElement("button");
      btnDetail.type = "button";
      btnDetail.className = "btn btn-secondary btn-sm";
      btnDetail.textContent = "Xem chi tiết";
      btnDetail.addEventListener("click", () => openModal(item, btnDetail));

      actionsDiv.appendChild(btnDetail);
      bodyDiv.appendChild(actionsDiv);

      card.appendChild(headerDiv);
      card.appendChild(bodyDiv);
      resultsGrid.appendChild(card);
    });
  }

  // ---------- Detail Modal Logic ----------
  function openModal(item, triggerBtn) {
    lastFocusedElement = triggerBtn || document.activeElement;

    const canonicalClass = item.canonical_class || "unknown";
    const originalClass = item.original_class || "unknown";
    const displayNameVi = item.display_name_vi;
    const displayNameEn = item.display_name || canonicalClass;
    const displayName = displayNameVi ? `${displayNameVi} (${displayNameEn})` : displayNameEn;
    const datasetName = item.dataset_name || "Fruits-360";
    const filename = item.filename || "unknown";
    const similarityObj = Utils.formatSimilarity(item.similarity);

    modalTitle.textContent = displayName;
    modalCanonicalClass.textContent = canonicalClass;
    modalOriginalClass.textContent = originalClass;
    modalDataset.textContent = datasetName;
    modalFilename.textContent = filename;

    modalMediaWrapper.innerHTML = "";
    if (Utils.isSafeImageUrl(item.image_url)) {
      const modalImg = document.createElement("img");
      modalImg.src = item.image_url;
      modalImg.alt = displayName;
      modalMediaWrapper.appendChild(modalImg);
    }

    modalSimilarityBox.className = `similarity-box ${similarityObj.levelClass}`;
    modalSimilarityBox.innerHTML = `
      <div class="similarity-header">
        <span class="similarity-label">Độ tương đồng</span>
        <span class="similarity-value">${similarityObj.percentageText}</span>
      </div>
      <div class="similarity-track">
        <div class="similarity-fill" style="width: ${similarityObj.visualWidth};"></div>
      </div>
    `;

    // Trustworthy Knowledge Base section (no fake data)
    modalKnowledgeContainer.innerHTML = "";
    const emptyKnowledge = document.createElement("div");
    emptyKnowledge.className = "knowledge-empty";
    emptyKnowledge.textContent = "Chưa có dữ liệu tri thức thực vật đáng tin cậy cho loài này trong cơ sở dữ liệu.";
    modalKnowledgeContainer.appendChild(emptyKnowledge);

    imageModal.style.display = "flex";
    document.body.style.overflow = "hidden";
    modalClose.focus();
  }

  function closeModal() {
    imageModal.style.display = "none";
    document.body.style.overflow = "";
    if (lastFocusedElement) {
      lastFocusedElement.focus();
    }
  }

  modalClose.addEventListener("click", closeModal);
  imageModal.addEventListener("click", (e) => {
    if (e.target === imageModal) {
      closeModal();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && imageModal.style.display === "flex") {
      closeModal();
    }
  });
});
