/**
 * Fruvia AI — Progressive Web App Service Worker
 * Caches static frontend assets safely.
 * NEVER caches POST /api/retrieve, /api/*, or dynamic backend search requests.
 */

const CACHE_PREFIX = "fruvia-v2-static-";
const CACHE_NAME = `${CACHE_PREFIX}v9`;
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

function shouldUseNetworkFirst(request, pathname) {
  return (
    request.mode === "navigate" ||
    pathname.startsWith("/js/") ||
    pathname.startsWith("/css/") ||
    pathname.startsWith("/data/")
  );
}

function isCacheableResponse(response) {
  return Boolean(response && response.status === 200 && response.type === "basic");
}

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const networkResponse = await fetch(request);
    if (isCacheableResponse(networkResponse)) {
      await cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cachedResponse = await cache.match(request);
    if (cachedResponse) return cachedResponse;

    if (request.mode === "navigate") {
      const offlineResponse = await cache.match("/offline.html");
      if (offlineResponse) return offlineResponse;
    }

    return new Response("Offline", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" }
    });
  }
}

function cacheFirstWithRefresh(event, request) {
  const cachePromise = caches.open(CACHE_NAME);
  const refreshPromise = cachePromise.then(async (cache) => {
    const networkResponse = await fetch(request);
    if (isCacheableResponse(networkResponse)) {
      await cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  });

  // Keep the worker alive until the background update is actually persisted.
  event.waitUntil(refreshPromise.then(() => undefined).catch(() => undefined));

  return cachePromise
    .then((cache) => cache.match(request))
    .then((cachedResponse) => cachedResponse || refreshPromise)
    .catch(() => new Response("Offline", { status: 503 }));
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
          if (name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME) {
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

  if (shouldUseNetworkFirst(request, url.pathname)) {
    // Online visits must receive current HTML (including CSP), JS and taxonomy.
    event.respondWith(networkFirst(request));
    return;
  }

  event.respondWith(cacheFirstWithRefresh(event, request));
});
