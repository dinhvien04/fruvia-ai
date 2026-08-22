/**
 * Fruvia AI — Home Page Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Single Source Stats Populate
  if (typeof CONFIG !== 'undefined' && CONFIG.STATS) {
    const vCount = document.getElementById('stat-vector-count');
    const sCount = document.getElementById('stat-species-count');
    const dCount = document.getElementById('stat-dataset-count');
    const fDim = document.getElementById('stat-feature-dim');

    if (vCount) vCount.textContent = CONFIG.STATS.VECTOR_COUNT_TEXT;
    if (sCount) sCount.textContent = CONFIG.STATS.SPECIES_COUNT_LABEL;
    if (dCount) dCount.textContent = CONFIG.STATS.DATASET_COUNT_LABEL;
    if (fDim) fDim.textContent = CONFIG.STATS.FEATURE_DIM_LABEL;
  }

  // 2. Initialize Upload Manager for Hero Widget
  if (typeof UploadManager !== 'undefined') {
    UploadManager.init({
      dropzoneId: 'dropzone',
      fileInputId: 'file-input',
      cameraInputId: 'camera-input',
      previewContainerId: 'preview-container',
      previewImgId: 'preview-img'
    });

    const btnQuickCamera = document.getElementById('btn-quick-camera');
    const btnQuickGallery = document.getElementById('btn-quick-gallery');
    const cameraInput = document.getElementById('camera-input');
    const fileInput = document.getElementById('file-input');

    if (btnQuickCamera && cameraInput) {
      btnQuickCamera.addEventListener('click', () => cameraInput.click());
    }
    if (btnQuickGallery && fileInput) {
      btnQuickGallery.addEventListener('click', () => fileInput.click());
    }

    const btnHeroSearch = document.getElementById('btn-hero-search');

    UploadManager.onSelected(() => {
      if (btnHeroSearch) btnHeroSearch.disabled = false;
    });

    UploadManager.onCleared(() => {
      if (btnHeroSearch) btnHeroSearch.disabled = true;
    });

    if (btnHeroSearch) {
      btnHeroSearch.addEventListener('click', () => {
        if (UploadManager.transferToSearchPage()) {
          window.location.href = '/search';
        }
      });
    }
  }
});
