/**
 * Fruvia AI — PWA & Offline Support Module
 */
const PwaManager = {
  cachePrefix: "fruvia-v2-static-",

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
      this.disableLocalServiceWorker();
      return;
    }

    window.addEventListener("load", () => {
      navigator.serviceWorker
        .register("/service-worker.js", { updateViaCache: "none" })
        .then((registration) => {
          console.log("Fruvia: ServiceWorker registered successfully:", registration.scope);
          return registration.update();
        })
        .catch((error) => {
          console.warn("Fruvia: ServiceWorker registration failed:", error);
        });
    });
  },

  async disableLocalServiceWorker() {
    try {
      const wasControlled = Boolean(navigator.serviceWorker.controller);
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.unregister()));

      if (typeof caches !== "undefined") {
        const cacheNames = await caches.keys();
        await Promise.all(
          cacheNames
            .filter((name) => name.startsWith(this.cachePrefix))
            .map((name) => caches.delete(name))
        );
      }

      console.log("Fruvia Dev: Cleared stale ServiceWorker and app-shell caches on localhost");

      // unregister() does not release a tab that is already controlled. Reload
      // exactly once so localhost receives current JS and response headers.
      const reloadKey = "fruvia-dev-sw-cleanup-reloaded";
      if (wasControlled && sessionStorage.getItem(reloadKey) !== "1") {
        sessionStorage.setItem(reloadKey, "1");
        window.location.reload();
      } else if (!wasControlled) {
        sessionStorage.removeItem(reloadKey);
      }
    } catch (error) {
      console.warn("Fruvia Dev: Could not clear stale ServiceWorker state", error);
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
