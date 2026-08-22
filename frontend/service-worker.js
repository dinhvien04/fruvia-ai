/**
 * Fruvia AI — Progressive Web App Service Worker
 * Caches static frontend assets safely.
 * NEVER caches POST /api/retrieve, /api/*, or dynamic backend search requests.
 */

const CACHE_NAME = "fruvia-v2-static-v5";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/search",
  "/retrieval.html",
  "/explore",
  "/explore.html",
  "/species",
  "/species.html",
  "/offline.html",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/css/variables.css",
  "/css/base.css",
  "/css/components.css",
  "/css/home.css",
  "/css/retrieval.css",
  "/css/explore.css",
  "/js/config.js",
  "/js/api.js",
  "/js/utils.js",
  "/js/knowledge-utils.js",
  "/js/history.js",
  "/js/history-ui.js",
  "/js/home.js",
  "/js/species.js",
  "/js/offline.js",
  "/js/modal.js",
  "/js/upload.js",
  "/js/results.js",
  "/js/retrieval.js",
  "/js/explore.js",
  "/js/navigation.js",
  "/js/pwa.js",
  "/data/species.json",
  "/assets/svg/brand-lockup.svg",
  "/assets/svg/brand-mark.svg",
  "/assets/svg/upload-illustration.svg",
  "/assets/svg/empty-search.svg",
  "/assets/svg/no-results.svg",
  "/assets/svg/error-state.svg",
  "/assets/svg/nav-home.svg",
  "/assets/svg/nav-search.svg",
  "/assets/svg/nav-explore.svg",
  "/assets/svg/camera.svg",
  "/assets/svg/gallery.svg",
  "/assets/svg/history.svg"
];

// Allowed public static route prefixes and exact paths for runtime cache updates
const ALLOWED_CACHE_PATHS = new Set([
  "/",
  "/index.html",
  "/search",
  "/retrieval.html",
  "/explore",
  "/explore.html",
  "/species",
  "/species.html",
  "/offline.html",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/robots.txt",
  "/sitemap.xml"
]);

function isCacheableStaticPath(pathname) {
  if (ALLOWED_CACHE_PATHS.has(pathname)) {
    return true;
  }
  return (
    pathname.startsWith("/css/") ||
    pathname.startsWith("/js/") ||
    pathname.startsWith("/assets/") ||
    pathname.startsWith("/data/")
  );
}

// Install Event
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log("Fruvia SW: Caching static app shell");
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// Activate Event
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            console.log("Fruvia SW: Clearing old cache:", name);
            return caches.delete(name);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Event
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Security & Safety: ONLY handle same-origin static GET requests.
  // NEVER cache API requests (/api/*), health checks, non-GET requests, or unapproved paths.
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/") ||
    !isCacheableStaticPath(url.pathname)
  ) {
    return;
  }

  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        // Return cached version & fetch update in background for static assets
        fetch(request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200 && networkResponse.type === "basic") {
              caches.open(CACHE_NAME).then((cache) => cache.put(request, networkResponse));
            }
          })
          .catch(() => {});
        return cachedResponse;
      }

      // Network Fallback
      return fetch(request).catch(() => {
        if (request.headers.get("accept")?.includes("text/html")) {
          return caches.match("/offline.html");
        }
      });
    })
  );
});
