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
  const modeSelect = document.getElementById("mode-select");
  const categorySelect = document.getElementById("category-select");

  const btnSearch = document.getElementById("btn-search");
  const searchText = document.getElementById("search-text");
  const searchSpinner = document.getElementById("search-spinner");

  const backendStatusBadge = document.getElementById("backend-status");
  const statusText = document.getElementById("status-text");

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
  const modalOriginalClass = document.getElementById("modal-original-class");
  const modalSimilarityBox = document.getElementById("modal-similarity-box");
  const modalFilename = document.getElementById("modal-filename");
  const modalSplit = document.getElementById("modal-split");
  const modalPath = document.getElementById("modal-path");

  // State Variables
  let selectedFile = null;
  let queryDataUrl = null;
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

    if (file.size > CONFIG.MAX_UPLOAD_BYTES) {
      showErrorBanner(
        "File Too Large",
        `Selected image (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds the 10 MB limit.`
      );
      return;
    }

    // Determine file extension (fallback to MIME type if missing filename)
    let ext = "";
    if (file.name && file.name.includes(".")) {
      ext = "." + file.name.split(".").pop().toLowerCase();
    } else if (file.type) {
      const mimeExt = file.type.split("/")[1]?.toLowerCase();
      if (mimeExt) {
        ext = mimeExt === "jpeg" ? ".jpg" : "." + mimeExt;
      }
    }

    if (!CONFIG.ALLOWED_EXTENSIONS.includes(ext)) {
      showErrorBanner(
        "Unsupported File Extension",
        `File extension "${ext || "unknown"}" is not supported. Please select JPG, PNG, or WEBP.`
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

  // ---------- Clipboard Paste Event (Ctrl+V / Cmd+V) ----------
  window.addEventListener("paste", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

    const clipboardData = e.clipboardData || (e.originalEvent && e.originalEvent.clipboardData);
    if (!clipboardData) return;

    // 1. Check for files array first (Windows Explorer copy/paste file)
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

    // 2. Check for clipboard items (Snipping Tool, Paint, Copy Image from Browser)
    const items = clipboardData.items || [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type && item.type.startsWith("image/")) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (!blob) continue;

        let ext = "png";
        if (blob.type === "image/jpeg" || blob.type === "image/jpg") {
          ext = "jpg";
        } else if (blob.type === "image/webp") {
          ext = "webp";
        } else if (blob.type.includes("/")) {
          ext = blob.type.split("/")[1];
        }

        const rawName = blob.name && blob.name !== "image.png" && blob.name !== "blob" ? blob.name : "";
        const fileName = rawName || `pasted-image-${Date.now()}.${ext}`;
        const pastedFile = new File([blob], fileName, { type: blob.type || `image/${ext}` });

        handleFileSelected(pastedFile);
        return;
      }
    }
  });

  topKSlider.addEventListener("input", (e) => {
    topKDisplay.textContent = e.target.value;
  });

  // ---------- Banner Renderers ----------
  function showErrorBanner(title, message) {
    errorBannerContainer.innerHTML = "";
    const banner = document.createElement("div");
    banner.className = "alert-banner alert-banner-error";
    banner.setAttribute("role", "alert");

    const icon = document.createElement("span");
    icon.className = "alert-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "⚠️";

    const content = document.createElement("div");
    content.className = "alert-content";

    const h4 = document.createElement("h4");
    h4.textContent = title;

    const p = document.createElement("p");
    p.textContent = message;

    content.appendChild(h4);
    content.appendChild(p);
    banner.appendChild(icon);
    banner.appendChild(content);
    errorBannerContainer.appendChild(banner);
    errorBannerContainer.style.display = "block";
  }

  function showWarningBanner(title, message) {
    warningBannerContainer.innerHTML = "";
    const banner = document.createElement("div");
    banner.className = "alert-banner alert-banner-warning";
    banner.setAttribute("role", "alert");

    const icon = document.createElement("span");
    icon.className = "alert-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "⚠️";

    const content = document.createElement("div");
    content.className = "alert-content";

    const h4 = document.createElement("h4");
    h4.textContent = title;

    const p = document.createElement("p");
    p.textContent = message;

    content.appendChild(h4);
    content.appendChild(p);
    banner.appendChild(icon);
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

  // ---------- Search Submission ----------
  btnSearch.addEventListener("click", async () => {
    if (!selectedFile || isSearching) return;

    isSearching = true;
    btnSearch.disabled = true;
    searchSpinner.style.display = "inline-block";
    searchText.textContent = "Processing Vector Search...";
    clearBanners();

    const topK = parseInt(topKSlider.value, 10);
    const mode = modeSelect ? modeSelect.value : "image";
    const category = categorySelect ? categorySelect.value : "fruit";

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
      searchText.textContent = "Find Similar Images";
    }
  });

  // ---------- Render Results Cards (DOM API) ----------
  function renderResults(response) {
    if (initialEmptyState) {
      initialEmptyState.style.display = "none";
    }

    const results = response.results || [];
    resCount.textContent = String(response.result_count || results.length);
    resTime.textContent = String(response.processing_time_ms || 0);
    resultsHeader.style.display = "flex";

    // Setup Query Image vs Top Match comparison section
    if (queryDataUrl) {
      queryComparisonImg.src = queryDataUrl;
      comparisonContainer.style.display = "flex";
    }

    // Clear previous results
    resultsGrid.innerHTML = "";
    topMatchMedia.innerHTML = "";

    if (results.length === 0) {
      const emptyDiv = document.createElement("div");
      emptyDiv.className = "empty-state";
      emptyDiv.style.gridColumn = "1 / -1";

      const icon = document.createElement("div");
      icon.className = "empty-state-icon";
      icon.textContent = "🍃";

      const h3 = document.createElement("h3");
      h3.textContent = "No Similar Images Found";

      const p = document.createElement("p");
      p.textContent = "The vector search returned zero matches for your query image.";

      emptyDiv.appendChild(icon);
      emptyDiv.appendChild(h3);
      emptyDiv.appendChild(p);
      resultsGrid.appendChild(emptyDiv);
      return;
    }

    // Check similarity thresholds for reliability warning
    const topResult = results[0];
    const topSim = topResult && typeof topResult.similarity === "number" ? topResult.similarity : 0;

    if (topSim < CONFIG.LOW_SIMILARITY_THRESHOLD) {
      showWarningBanner(
        "No close match was found in the current dataset.",
        "Không tìm thấy loại trái cây đủ tương đồng trong dữ liệu hiện tại."
      );
    }

    // Populate Top Match in Comparison Container
    if (topResult) {
      const displayName = topResult.display_name || topResult.canonical_class || "Unknown";
      if (Utils.isSafeImageUrl(topResult.image_url)) {
        const topImg = document.createElement("img");
        topImg.src = topResult.image_url;
        topImg.alt = `Top match: ${displayName}`;
        topMatchMedia.appendChild(topImg);
      } else {
        const topPlaceholder = document.createElement("div");
        topPlaceholder.className = "card-placeholder";
        const pIcon = document.createElement("span");
        pIcon.className = "fruit-icon";
        pIcon.textContent = "🍎";
        const pText = document.createElement("span");
        pText.className = "placeholder-class";
        pText.textContent = displayName;
        topPlaceholder.appendChild(pIcon);
        topPlaceholder.appendChild(pText);
        topMatchMedia.appendChild(topPlaceholder);
      }
    }

    // Render individual result cards using DOM Methods (No unsafe innerHTML)
    results.forEach((item, index) => {
      const rank = index + 1;
      const originalClass = item.original_class || "unknown";
      const canonicalClass = item.canonical_class || "unknown";
      const displayNameEn = item.display_name || canonicalClass;
      const displayNameVi = item.display_name_vi || null;
      const displayName = displayNameVi ? `${displayNameVi} (${displayNameEn})` : displayNameEn;
      const datasetName = item.dataset_name || "Fruits-360";
      const hitCount = item.hit_count ? ` (${item.hit_count} hits)` : "";
      const filename = item.filename || "unknown";
      const originalSplit = item.original_split || "unknown";
      const relativePath = item.relative_path || "";
      const similarityObj = Utils.formatSimilarity(item.similarity);

      const card = document.createElement("article");
      card.className = "result-card";

      // --- Media Container ---
      const mediaDiv = document.createElement("div");
      mediaDiv.className = "card-media";

      const rankBadge = document.createElement("span");
      rankBadge.className = "rank-badge";
      rankBadge.textContent = `#${rank}`;
      mediaDiv.appendChild(rankBadge);

      const hasSafeUrl = Utils.isSafeImageUrl(item.image_url);

      if (hasSafeUrl) {
        // Skeleton shimmer overlay
        const skeleton = document.createElement("div");
        skeleton.className = "card-skeleton";
        mediaDiv.appendChild(skeleton);

        const img = document.createElement("img");
        img.setAttribute("loading", "lazy");
        img.setAttribute("decoding", "async");
        img.alt = `Similar fruit match: ${displayName}`;

        img.addEventListener("load", () => {
          skeleton.remove();
          img.classList.add("loaded");
        });

        img.addEventListener("error", () => {
          skeleton.remove();
          img.remove();
          mediaDiv.appendChild(createPlaceholderElement(displayName, "Image load error"));
        });

        img.src = item.image_url;
        mediaDiv.appendChild(img);
      } else {
        mediaDiv.appendChild(createPlaceholderElement(displayName, "Preview unavailable"));
      }

      // Click media to open Modal Lightbox
      mediaDiv.addEventListener("click", () => {
        openModal(item, queryDataUrl);
      });

      // --- Body Container ---
      const bodyDiv = document.createElement("div");
      bodyDiv.className = "card-body";

      const titleHeader = document.createElement("div");
      const titleH3 = document.createElement("h3");
      titleH3.className = "card-class-title";
      titleH3.textContent = displayName;

      const rawLabelP = document.createElement("p");
      rawLabelP.className = "card-class-original";
      rawLabelP.textContent = `Label: ${originalClass} • ${datasetName}${hitCount}`;

      titleHeader.appendChild(titleH3);
      titleHeader.appendChild(rawLabelP);
      bodyDiv.appendChild(titleHeader);

      // --- Similarity Bar ---
      const simBox = document.createElement("div");
      simBox.className = `similarity-box ${similarityObj.levelClass}`;

      const simHeader = document.createElement("div");
      simHeader.className = "similarity-header";

      const simLabel = document.createElement("span");
      simLabel.className = "similarity-label";
      simLabel.textContent = "Similarity";

      const simValue = document.createElement("span");
      simValue.className = "similarity-value";
      simValue.textContent = similarityObj.percentageText;

      simHeader.appendChild(simLabel);
      simHeader.appendChild(simValue);

      const simTrack = document.createElement("div");
      simTrack.className = "similarity-track";
      simTrack.setAttribute("role", "progressbar");
      simTrack.setAttribute("aria-valuenow", (item.similarity * 100).toFixed(1));
      simTrack.setAttribute("aria-valuemin", "-100");
      simTrack.setAttribute("aria-valuemax", "100");

      const simFill = document.createElement("div");
      simFill.className = "similarity-fill";
      simFill.style.width = similarityObj.visualWidth;

      simTrack.appendChild(simFill);
      simBox.appendChild(simHeader);
      simBox.appendChild(simTrack);
      bodyDiv.appendChild(simBox);

      // --- Compact Metadata Summary ---
      const summaryDiv = document.createElement("div");
      summaryDiv.className = "card-details";

      const fileLine = document.createElement("div");
      const fileStrong = document.createElement("strong");
      fileStrong.textContent = "File: ";
      fileLine.appendChild(fileStrong);
      fileLine.appendChild(document.createTextNode(filename));

      const splitLine = document.createElement("div");
      const splitStrong = document.createElement("strong");
      splitStrong.textContent = "Split: ";
      splitLine.appendChild(splitStrong);
      splitLine.appendChild(document.createTextNode(originalSplit));

      summaryDiv.appendChild(fileLine);
      summaryDiv.appendChild(splitLine);

      // --- Collapsible Technical Details ---
      const detailsToggleBtn = document.createElement("button");
      detailsToggleBtn.type = "button";
      detailsToggleBtn.className = "card-details-toggle";
      detailsToggleBtn.textContent = "▶ Technical Details";

      const hiddenDetailsDiv = document.createElement("div");
      hiddenDetailsDiv.style.display = "none";
      hiddenDetailsDiv.className = "card-details";
      hiddenDetailsDiv.style.marginTop = "0.25rem";

      const pathLine = document.createElement("div");
      const pathStrong = document.createElement("strong");
      pathStrong.textContent = "Path: ";
      pathLine.appendChild(pathStrong);
      pathLine.appendChild(document.createTextNode(relativePath));

      const rawSimLine = document.createElement("div");
      const rawSimStrong = document.createElement("strong");
      rawSimStrong.textContent = "Raw Similarity: ";
      rawSimLine.appendChild(rawSimStrong);
      rawSimLine.appendChild(document.createTextNode(String(item.similarity)));

      hiddenDetailsDiv.appendChild(pathLine);
      hiddenDetailsDiv.appendChild(rawSimLine);

      detailsToggleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isHidden = hiddenDetailsDiv.style.display === "none";
        hiddenDetailsDiv.style.display = isHidden ? "block" : "none";
        detailsToggleBtn.textContent = isHidden ? "▼ Technical Details" : "▶ Technical Details";
      });

      bodyDiv.appendChild(summaryDiv);
      bodyDiv.appendChild(detailsToggleBtn);
      bodyDiv.appendChild(hiddenDetailsDiv);

      card.appendChild(mediaDiv);
      card.appendChild(bodyDiv);
      resultsGrid.appendChild(card);
    });
  }

  function createPlaceholderElement(displayName, noteText) {
    const placeholder = document.createElement("div");
    placeholder.className = "card-placeholder";

    const fruitIcon = document.createElement("span");
    fruitIcon.className = "fruit-icon";
    fruitIcon.setAttribute("aria-hidden", "true");
    fruitIcon.textContent = "🍇";

    const nameSpan = document.createElement("span");
    nameSpan.className = "placeholder-class";
    nameSpan.textContent = displayName;

    const noteSpan = document.createElement("span");
    noteSpan.className = "placeholder-note";
    noteSpan.textContent = noteText;

    placeholder.appendChild(fruitIcon);
    placeholder.appendChild(nameSpan);
    placeholder.appendChild(noteSpan);
    return placeholder;
  }

  // ---------- Modal / Lightbox Logic ----------
  function openModal(item, queryImgUrl) {
    const displayName = item.display_name || item.canonical_class || "Unknown";
    const originalClass = item.original_class || "unknown";
    const filename = item.filename || "unknown";
    const originalSplit = item.original_split || "unknown";
    const relativePath = item.relative_path || "";
    const similarityObj = Utils.formatSimilarity(item.similarity);

    modalTitle.textContent = displayName;
    modalOriginalClass.textContent = `Dataset label: ${originalClass}`;
    modalFilename.textContent = filename;
    modalSplit.textContent = originalSplit;
    modalPath.textContent = relativePath;

    modalMediaWrapper.innerHTML = "";
    if (Utils.isSafeImageUrl(item.image_url)) {
      const modalImg = document.createElement("img");
      modalImg.src = item.image_url;
      modalImg.alt = displayName;
      modalMediaWrapper.appendChild(modalImg);
    } else {
      modalMediaWrapper.appendChild(createPlaceholderElement(displayName, "Preview unavailable"));
    }

    modalSimilarityBox.className = `similarity-box ${similarityObj.levelClass}`;
    modalSimilarityBox.innerHTML = `
      <div class="similarity-header">
        <span class="similarity-label">Similarity</span>
        <span class="similarity-value">${similarityObj.percentageText}</span>
      </div>
      <div class="similarity-track">
        <div class="similarity-fill" style="width: ${similarityObj.visualWidth};"></div>
      </div>
    `;

    imageModal.style.display = "flex";
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    imageModal.style.display = "none";
    document.body.style.overflow = "";
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
