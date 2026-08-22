/**
 * Regression tests for stale Fruvia app-shell caches.
 * Executes the real service-worker.js in a small mocked worker environment.
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const handlers = {};
const puts = [];
let fetchCount = 0;
const oldResponse = new Response("old cached Explore shell", {
  status: 200,
  headers: { "Content-Security-Policy": "img-src 'self' data:;" }
});
const newResponse = new Response("current network Explore shell", {
  status: 200,
  headers: { "Content-Security-Policy": "img-src 'self' https://images.example;" }
});

function cloneAsBasic(response) {
  const clone = response.clone();
  Object.defineProperty(clone, "type", { value: "basic" });
  return clone;
}

const currentCache = {
  addAll: async () => {},
  match: async () => cloneAsBasic(oldResponse),
  put: async (request, response) => {
    puts.push({ request, body: await response.text() });
  }
};

const context = {
  URL,
  Response,
  console,
  fetch: async () => {
    fetchCount += 1;
    return cloneAsBasic(newResponse);
  },
  caches: {
    open: async () => currentCache,
    keys: async () => ["fruvia-v2-static-v8", "unrelated-cache"],
    delete: async () => true
  },
  self: {
    location: { origin: "http://127.0.0.1:8000" },
    clients: { claim: async () => {} },
    skipWaiting: async () => {},
    addEventListener: (type, handler) => {
      handlers[type] = handler;
    }
  }
};

const workerPath = path.join(__dirname, "..", "service-worker.js");
vm.runInNewContext(fs.readFileSync(workerPath, "utf8"), context, { filename: workerPath });

function createFetchEvent(url, mode = "cors") {
  return {
    request: {
      method: "GET",
      mode,
      url,
      headers: { get: () => "text/html" }
    },
    responsePromise: null,
    lifetimePromises: [],
    respondWith(promise) {
      this.responsePromise = Promise.resolve(promise);
    },
    waitUntil(promise) {
      this.lifetimePromises.push(Promise.resolve(promise));
    }
  };
}

(async () => {
  // Navigation must prefer the network even when an old cached HTML/CSP exists.
  const navigationEvent = createFetchEvent("http://127.0.0.1:8000/explore", "navigate");
  handlers.fetch(navigationEvent);
  const navigationResponse = await navigationEvent.responsePromise;
  assert.strictEqual(await navigationResponse.text(), "current network Explore shell");
  assert.strictEqual(fetchCount, 1);
  assert.ok(puts.some((put) => put.body === "current network Explore shell"));

  // Cache-first immutable assets must keep the worker alive while refresh is persisted.
  const assetEvent = createFetchEvent(
    "http://127.0.0.1:8000/assets/svg/brand-mark.svg",
    "cors"
  );
  handlers.fetch(assetEvent);
  const assetResponse = await assetEvent.responsePromise;
  assert.strictEqual(await assetResponse.text(), "old cached Explore shell");
  assert.strictEqual(assetEvent.lifetimePromises.length, 1);
  await Promise.all(assetEvent.lifetimePromises);
  assert.strictEqual(fetchCount, 2);

  console.log("Service Worker cache refresh regression tests passed.");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
