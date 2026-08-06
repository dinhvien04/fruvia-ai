const API_BASE_URL = window.FruviaConfig?.apiBaseUrl || "http://localhost:8000";
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

const elements = {
  imageInput: document.querySelector("#imageInput"),
  dropZone: document.querySelector("#dropZone"),
  dropPlaceholder: document.querySelector("#dropPlaceholder"),
  imagePreview: document.querySelector("#imagePreview"),
  clearButton: document.querySelector("#clearButton"),
  searchButton: document.querySelector("#searchButton"),
  buttonLabel: document.querySelector(".button-label"),
  buttonLoader: document.querySelector(".button-loader"),
  topKSelect: document.querySelector("#topKSelect"),
  formMessage: document.querySelector("#formMessage"),
  serviceStatus: document.querySelector("#serviceStatus"),
  serviceStatusText: document.querySelector("#serviceStatusText"),
  emptyState: document.querySelector("#emptyState"),
  resultsSection: document.querySelector("#resultsSection"),
  resultsGrid: document.querySelector("#resultsGrid"),
  resultCount: document.querySelector("#resultCount"),
  processingTime: document.querySelector("#processingTime"),
  resultSummary: document.querySelector("#resultSummary"),
  resultCardTemplate: document.querySelector("#resultCardTemplate"),
};

let selectedFile = null;
let previewUrl = null;

function setMessage(message = "", isError = false) {
  elements.formMessage.textContent = message;
  elements.formMessage.classList.toggle("is-error", isError);
}

function setLoading(isLoading) {
  elements.searchButton.disabled = isLoading || !selectedFile;
  elements.imageInput.disabled = isLoading;
  elements.topKSelect.disabled = isLoading;
  elements.clearButton.disabled = isLoading || !selectedFile;
  elements.buttonLabel.hidden = isLoading;
  elements.buttonLoader.hidden = !isLoading;
}

function resetPreview() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  selectedFile = null;
  elements.imageInput.value = "";
  elements.imagePreview.removeAttribute("src");
  elements.imagePreview.hidden = true;
  elements.dropPlaceholder.hidden = false;
  elements.clearButton.disabled = true;
  elements.searchButton.disabled = true;
  setMessage();
}

function validateFile(file) {
  if (!file) return "Không tìm thấy tệp ảnh.";
  if (!ALLOWED_TYPES.has(file.type)) return "Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.";
  if (file.size > MAX_FILE_BYTES) return "Ảnh vượt quá giới hạn 10 MB.";
  return null;
}

function useFile(file) {
  const error = validateFile(file);
  if (error) {
    setMessage(error, true);
    return;
  }

  resetPreview();
  selectedFile = file;
  previewUrl = URL.createObjectURL(file);
  elements.imagePreview.src = previewUrl;
  elements.imagePreview.alt = `Ảnh truy vấn: ${file.name}`;
  elements.imagePreview.hidden = false;
  elements.dropPlaceholder.hidden = true;
  elements.clearButton.disabled = false;
  elements.searchButton.disabled = false;
  setMessage(`${file.name} · ${(file.size / 1024).toFixed(0)} KB`);
}

function humanizeClassName(value) {
  if (!value) return "Không xác định";
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function similarityPercent(score) {
  return Math.max(0, Math.min(100, score * 100));
}

function renderSummary(results) {
  if (!results.length) {
    elements.resultSummary.innerHTML = "Không tìm thấy kết quả phù hợp trong collection hiện tại.";
    return;
  }

  const first = results[0];
  const label = humanizeClassName(first.canonical_class || first.original_class);
  const score = similarityPercent(first.similarity).toFixed(1);
  const lowSimilarityNotice = first.similarity < 0.55
    ? " Điểm tương đồng còn thấp; ảnh này có thể không thuộc nhóm dữ liệu hiện có."
    : "";

  elements.resultSummary.innerHTML = `Kết quả gần nhất nghiêng về <strong>${escapeHtml(label)}</strong> với cosine similarity <strong>${score}%</strong>.${escapeHtml(lowSimilarityNotice)}`;
}

function renderResults(payload) {
  const results = Array.isArray(payload.results) ? payload.results : [];
  elements.resultsGrid.replaceChildren();

  results.forEach((result, index) => {
    const fragment = elements.resultCardTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".result-card");
    const image = fragment.querySelector(".result-image");
    const placeholder = fragment.querySelector(".result-placeholder");
    const scorePercent = similarityPercent(result.similarity);

    fragment.querySelector(".result-rank").textContent = `#${index + 1}`;
    fragment.querySelector(".canonical-class").textContent = humanizeClassName(result.canonical_class);
    fragment.querySelector(".original-class").textContent = result.original_class || "Unknown";
    fragment.querySelector(".similarity-value").textContent = `${scorePercent.toFixed(1)}%`;
    fragment.querySelector(".similarity-track span").style.width = `${scorePercent}%`;
    fragment.querySelector(".result-filename").textContent = result.filename || "—";
    fragment.querySelector(".result-split").textContent = result.original_split || "—";

    if (result.image_url) {
      image.src = result.image_url;
      image.alt = result.original_class || "Ảnh kết quả";
      image.hidden = false;
      placeholder.hidden = true;
      image.addEventListener("error", () => {
        image.hidden = true;
        placeholder.hidden = false;
      }, { once: true });
    }

    if (result.relative_path) card.title = result.relative_path;
    elements.resultsGrid.appendChild(fragment);
  });

  elements.resultCount.textContent = `${payload.result_count ?? results.length} kết quả`;
  elements.processingTime.textContent = `${Math.round(payload.processing_time_ms || 0)} ms`;
  renderSummary(results);
  elements.emptyState.hidden = true;
  elements.resultsSection.hidden = false;
  elements.resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(value) {
  const span = document.createElement("span");
  span.textContent = String(value);
  return span.innerHTML;
}

async function parseError(response) {
  try {
    const body = await response.json();
    return body.message || body.detail || `HTTP ${response.status}`;
  } catch {
    return `Backend trả về HTTP ${response.status}.`;
  }
}

async function searchSimilarImages() {
  if (!selectedFile) return;

  setLoading(true);
  setMessage("Đang tạo embedding và truy vấn Qdrant…");

  const formData = new FormData();
  formData.append("file", selectedFile, selectedFile.name);
  formData.append("top_k", elements.topKSelect.value);

  try {
    const response = await fetch(`${API_BASE_URL}/api/retrieve`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) throw new Error(await parseError(response));
    const payload = await response.json();
    renderResults(payload);
    setMessage("Tìm kiếm hoàn tất.");
  } catch (error) {
    const networkHint = error instanceof TypeError
      ? " Không kết nối được backend; hãy chạy FastAPI tại cổng 8000 và kiểm tra CORS."
      : "";
    setMessage(`${error.message || "Tìm kiếm thất bại."}${networkHint}`, true);
  } finally {
    setLoading(false);
  }
}

async function checkBackendHealth() {
  elements.serviceStatus.dataset.state = "checking";
  elements.serviceStatusText.textContent = "Đang kiểm tra backend…";

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 7000);
    const response = await fetch(`${API_BASE_URL}/api/health`, { signal: controller.signal });
    clearTimeout(timer);

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const health = await response.json();
    const fullyReady = health.status === "ok";
    elements.serviceStatus.dataset.state = fullyReady ? "online" : "checking";
    elements.serviceStatusText.textContent = fullyReady ? "Backend sẵn sàng" : "Backend đang degraded";
  } catch {
    elements.serviceStatus.dataset.state = "offline";
    elements.serviceStatusText.textContent = "Backend chưa kết nối";
  }
}

elements.imageInput.addEventListener("change", (event) => useFile(event.target.files?.[0]));
elements.clearButton.addEventListener("click", resetPreview);
elements.searchButton.addEventListener("click", searchSimilarImages);

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("is-dragging");
  });
});

elements.dropZone.addEventListener("drop", (event) => useFile(event.dataTransfer.files?.[0]));

checkBackendHealth();
