/**
 * Fruvia AI — Image Upload Manager Module
 * Handles file picking, camera input, drag/drop, clipboard paste, image validation,
 * preview generation, and cross-page transfer (Homepage hero search -> Search page).
 */
const UploadManager = {
  selectedFile: null,
  previewDataUrl: null,
  onImageSelectedCallbacks: [],
  onImageClearedCallbacks: [],

  init(options = {}) {
    const { dropzoneId, fileInputId, cameraInputId, previewContainerId, previewImgId } = options;

    const dropzone = document.getElementById(dropzoneId || "dropzone");
    const fileInput = document.getElementById(fileInputId || "file-input");
    const cameraInput = document.getElementById(cameraInputId || "camera-input");
    const previewContainer = document.getElementById(previewContainerId || "preview-container");
    const previewImg = document.getElementById(previewImgId || "preview-img");

    if (!dropzone || !fileInput) return;

    // File Input change
    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        this.handleFile(e.target.files[0]);
      }
    });

    // Camera Input change (Mobile dedicated camera input)
    if (cameraInput) {
      cameraInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
          this.handleFile(e.target.files[0]);
        }
      });
    }

    // Dropzone Click -> Trigger file picker if not clicking change/remove button
    dropzone.addEventListener("click", (e) => {
      if (e.target.closest("#btn-change-image") || e.target.closest("#btn-remove-image")) {
        return;
      }
      fileInput.click();
    });

    // Keyboard Access (Enter / Space)
    dropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        fileInput.click();
      }
    });

    // Drag and Drop
    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add("drag-over");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove("drag-over");
      });
    });

    dropzone.addEventListener("drop", (e) => {
      const dt = e.dataTransfer;
      if (dt && dt.files && dt.files[0]) {
        this.handleFile(dt.files[0]);
      }
    });

    // Clipboard Paste (Ctrl+V)
    document.addEventListener("paste", (e) => {
      const items = (e.clipboardData || e.originalEvent.clipboardData)?.items;
      if (!items) return;

      for (const item of items) {
        if (item.type.indexOf("image") === 0) {
          const file = item.getAsFile();
          if (file) {
            this.handleFile(file);
            break;
          }
        }
      }
    });

    // Change Image button
    const btnChange = document.getElementById("btn-change-image");
    if (btnChange) {
      btnChange.addEventListener("click", (e) => {
        e.stopPropagation();
        fileInput.click();
      });
    }

    // Remove Image button
    const btnRemove = document.getElementById("btn-remove-image");
    if (btnRemove) {
      btnRemove.addEventListener("click", (e) => {
        e.stopPropagation();
        this.clear();
      });
    }

    // Check if there is a pending image transferred from Homepage Hero Search
    this.restorePendingTransfer();
  },

  onSelected(callback) {
    if (typeof callback === "function") {
      this.onImageSelectedCallbacks.push(callback);
    }
  },

  onCleared(callback) {
    if (typeof callback === "function") {
      this.onImageClearedCallbacks.push(callback);
    }
  },

  handleFile(file) {
    // 1. Format check
    const validTypes = ["image/jpeg", "image/jpg", "image/png", "image/webp"];
    if (!validTypes.includes(file.type.toLowerCase())) {
      const err = new Error("Chỉ hỗ trợ định dạng tệp ảnh JPG, PNG hoặc WEBP.");
      err.errorCode = "UNSUPPORTED_FORMAT";
      this.notifyError(err);
      return;
    }

    // 2. Size check (10 MB)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      const err = new Error("Kích thước tệp vượt quá giới hạn 10 MB.");
      err.errorCode = "FILE_TOO_LARGE";
      this.notifyError(err);
      return;
    }

    this.selectedFile = file;

    // Generate Preview Data URL
    const reader = new FileReader();
    reader.onload = (e) => {
      this.previewDataUrl = e.target.result;
      this.renderPreview(this.previewDataUrl, file.name);

      // Trigger selection callbacks
      this.onImageSelectedCallbacks.forEach((cb) => cb(this.selectedFile, this.previewDataUrl));
    };
    reader.onerror = () => {
      const err = new Error("Không thể đọc tệp ảnh.");
      err.errorCode = "INVALID_IMAGE";
      this.notifyError(err);
    };
    reader.readAsDataURL(file);
  },

  renderPreview(dataUrl, filename) {
    const prompt = document.getElementById("dropzone-prompt");
    const container = document.getElementById("preview-container");
    const img = document.getElementById("preview-img");

    if (prompt) prompt.style.display = "none";
    if (container) container.style.display = "flex";
    if (img) {
      img.src = dataUrl;
      img.alt = filename ? `Ảnh truy vấn: ${filename}` : "Ảnh truy vấn";
    }
  },

  clear() {
    this.selectedFile = null;
    this.previewDataUrl = null;

    const fileInput = document.getElementById("file-input");
    const cameraInput = document.getElementById("camera-input");
    if (fileInput) fileInput.value = "";
    if (cameraInput) cameraInput.value = "";

    const prompt = document.getElementById("dropzone-prompt");
    const container = document.getElementById("preview-container");
    const img = document.getElementById("preview-img");

    if (prompt) prompt.style.display = "flex";
    if (container) container.style.display = "none";
    if (img) img.src = "";

    // Clear session storage transfer
    try {
      sessionStorage.removeItem("fruvia_pending_image");
    } catch (e) {}

    this.onImageClearedCallbacks.forEach((cb) => cb());
  },

  /**
   * Save current image to sessionStorage so user can jump from Homepage -> Search seamlessly
   */
  transferToSearchPage() {
    if (!this.selectedFile || !this.previewDataUrl) return false;
    try {
      const payload = {
        name: this.selectedFile.name,
        type: this.selectedFile.type,
        dataUrl: this.previewDataUrl
      };
      sessionStorage.setItem("fruvia_pending_image", JSON.stringify(payload));
      return true;
    } catch (e) {
      console.warn("Fruvia: Failed to save image to sessionStorage", e);
      return false;
    }
  },

  /**
   * Restore image on Search page load if coming from Homepage Hero Search with strict validation
   */
  restorePendingTransfer() {
    try {
      const raw = sessionStorage.getItem("fruvia_pending_image");
      if (!raw) return;
      sessionStorage.removeItem("fruvia_pending_image"); // Use once and clear immediately

      const payload = JSON.parse(raw);
      if (!payload || typeof payload !== "object" || !payload.dataUrl || typeof payload.dataUrl !== "string") {
        return;
      }

      // Validate dataUrl format against allowed MIME patterns
      const allowedDataUrlPrefixes = [
        "data:image/jpeg;base64,",
        "data:image/jpg;base64,",
        "data:image/png;base64,",
        "data:image/webp;base64,"
      ];
      const hasValidPrefix = allowedDataUrlPrefixes.some(prefix => payload.dataUrl.startsWith(prefix));
      if (!hasValidPrefix) {
        console.warn("Fruvia: Discarded invalid sessionStorage dataUrl format.");
        return;
      }

      // Convert dataUrl back to File object safely
      const arr = payload.dataUrl.split(",");
      if (arr.length !== 2) return;

      const mimeMatch = arr[0].match(/:(.*?);/);
      if (!mimeMatch) return;
      const mime = mimeMatch[1].toLowerCase();

      const bstr = atob(arr[1]);
      let n = bstr.length;
      if (n > 10 * 1024 * 1024) { // Hard cap 10 MB
        console.warn("Fruvia: Restored session image exceeded maximum 10MB limit.");
        return;
      }

      const u8arr = new Uint8Array(n);
      while (n--) {
        u8arr[n] = bstr.charCodeAt(n);
      }
      const safeName = (payload.name && typeof payload.name === "string")
        ? payload.name.substring(0, 255)
        : "search_image.jpg";

      const file = new File([u8arr], safeName, { type: mime });
      this.handleFile(file);
    } catch (e) {
      console.warn("Fruvia: Failed to restore image from transfer", e);
    }
  },

  notifyError(error) {
    const friendly = Utils.getFriendlyErrorMessage(error);
    const container = document.getElementById("error-banner-container");
    if (container) {
      container.innerHTML = `
        <div class="alert-banner alert-banner-error" role="alert">
          <img src="assets/svg/error-state.svg" alt="" class="alert-icon" aria-hidden="true">
          <div class="alert-content">
            <h4>${Utils.escapeHtml(friendly.title)}</h4>
            <p>${Utils.escapeHtml(friendly.message)}</p>
          </div>
        </div>
      `;
      container.style.display = "block";
    } else {
      alert(`${friendly.title}\n${friendly.message}`);
    }
  }
};
