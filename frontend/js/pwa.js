/**
 * Fruvia AI — PWA & Offline Support Module
 */
const PwaManager = {
  init() {
    this.registerServiceWorker();
    this.initOfflineBanner();
  },

  registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;

    // Check if running on local development host
    const isLocalhost = Boolean(
      window.location.hostname === "localhost" ||
      window.location.hostname === "[::1]" ||
      window.location.hostname.match(/^127(?:\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)){3}$/)
    );

    if (isLocalhost) {
      // Unregister any active service worker during local development to avoid stale caching
      navigator.serviceWorker.getRegistrations().then((registrations) => {
        for (const registration of registrations) {
          registration.unregister().then(() => {
            console.log("Fruvia Dev: Unregistered ServiceWorker on localhost");
          });
        }
      });
      return;
    }

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
