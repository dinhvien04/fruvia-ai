/**
 * Fruvia AI — Species Detail Page Script
 */

document.addEventListener('DOMContentLoaded', async () => {
  // Load public runtime configuration
  if (typeof RuntimeConfig !== 'undefined' && typeof RuntimeConfig.load === 'function') {
    RuntimeConfig.load();
  }

  const container = document.getElementById('species-detail-container');
  if (!container) return;

  const params = new URLSearchParams(window.location.search);
  const speciesId = params.get('id');

  if (!speciesId) {
    container.innerHTML = `
      <div class="empty-state">
        <h3>Không tìm thấy loài</h3>
        <p>Vui lòng chọn một loài từ trang khám phá.</p>
        <a href="/explore" class="btn btn-primary btn-sm" style="margin-top: 16px;">Về trang khám phá</a>
      </div>
    `;
    return;
  }

  try {
    const response = await fetch('data/species.json');
    const list = await response.json();
    const item = list.find(s => s.id === speciesId);

    if (!item) {
      container.innerHTML = `
        <div class="empty-state">
          <h3>Không tìm thấy thông tin loài "${typeof Utils !== 'undefined' ? Utils.escapeHtml(speciesId) : speciesId}"</h3>
          <a href="/explore" class="btn btn-primary btn-sm" style="margin-top: 16px;">Về trang khám phá</a>
        </div>
      `;
      return;
    }

    document.title = `${item.name_vi} (${item.name_en}) | Fruvia AI`;

    const catMap = { fruit: 'Trái cây', vegetable: 'Rau củ', nut: 'Hạt dinh dưỡng', seed: 'Hạt giống', other: 'Khác' };
    const catLabel = catMap[item.category] || item.category;

    container.innerHTML = `
      <div class="species-detail-content">
        <div class="species-detail-header">
          <div>
            <h1 class="species-detail-title">${typeof Utils !== 'undefined' ? Utils.escapeHtml(item.name_vi) : item.name_vi}</h1>
            <p class="species-detail-subtitle">${typeof Utils !== 'undefined' ? Utils.escapeHtml(item.name_en) : item.name_en}</p>
          </div>
          <span class="badge badge-primary">${typeof Utils !== 'undefined' ? Utils.escapeHtml(catLabel) : catLabel}</span>
        </div>

        <div class="species-detail-grid">
          <div class="card species-info-card">
            <span class="species-info-label">Mã định danh loài (Canonical Key)</span>
            <strong class="species-info-value">${typeof Utils !== 'undefined' ? Utils.escapeHtml(item.id) : item.id}</strong>
          </div>
          <div class="card species-info-card">
            <span class="species-info-label">Phân loại</span>
            <strong class="species-info-value">${item.is_fruit ? 'Trái cây' : 'Nông sản khác'}</strong>
          </div>
        </div>

        ${item.aliases && item.aliases.length > 0 ? `
          <div class="species-aliases-section">
            <h4 class="species-aliases-title">Các biến thể nhãn trong dữ liệu (Dataset Aliases)</h4>
            <div class="species-aliases-list">
              ${item.aliases.map(a => `<span class="badge badge-neutral">${typeof Utils !== 'undefined' ? Utils.escapeHtml(a) : a}</span>`).join('')}
            </div>
          </div>
        ` : ''}

        <div class="species-detail-actions">
          <a href="/explore" class="btn btn-secondary btn-sm">← Xem danh mục loài</a>
          <a href="/search" class="btn btn-primary btn-sm">Tìm kiếm ảnh loài này →</a>
        </div>
      </div>
    `;
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><h3>Lỗi tải thông tin loài</h3></div>`;
  }
});
