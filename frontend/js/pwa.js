/**
 * Fruvia AI — PWA & Offline Support Module
 */
const PwaManager = {
  init() {
    this.registerServiceWorker();
    this.initOfflineBanner();
  },

  registerServiceWorker() {
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker
          .register("/service-worker.js")
          .then((registration) => {
            console.log("Fruvia: ServiceWorker registered successfully:", registration.scope);
          })
          .catch((error) => {
            console.warn("Fruvia: ServiceWorker registration failed:", error);
          });
      });
    }
  },

  initOfflineBanner() {
    const updateOnlineStatus = () => {
      let banner = document.getElementById("offline-network-banner");
      if (!navigator.onLine) {
        if (!banner) {
          banner = document.createElement("div");
          banner.id = "offline-network-banner";
          banner.className = "offline-network-banner";
          banner.innerHTML = `
            <div class="container offline-banner-content">
              <span>Bạn đang ở chế độ ngoại tuyến (Offline). Một số tính năng tìm kiếm AI cần có kết nối mạng.</span>
            </div>
          `;
          document.body.prepend(banner);
        }
        banner.style.display = "block";
      } else if (banner) {
        banner.style.display = "none";
      }
    };

    window.addEventListener("online", updateOnlineStatus);
    window.addEventListener("offline", updateOnlineStatus);
    updateOnlineStatus();
  }
};

document.addEventListener("DOMContentLoaded", () => PwaManager.init());
