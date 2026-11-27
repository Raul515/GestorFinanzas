// Service Worker para Gestor Finanzas Quick-Capture PWA (Spec 016/017 - App Shell Instantánea)
const NETWORK_TIMEOUT_MS = 2500;
const DEFAULT_ASSETS = [
  "/mobile/",
  "/mobile/index.html",
  "/mobile/manifest.json",
  "/mobile/icon-192.png",
  "/mobile/icon-512.png",
  "/mobile/icon-192.svg",
  "/mobile/icon-512.svg"
];
const CACHE_NAME = "gestor-finanzas-mobile-v1.4.0-6ecef1f15b";
const ASSETS_TO_CACHE = [
  "/mobile/",
  "/mobile/assets/index-VXnBt-eg.css",
  "/mobile/assets/index-uNo5Idpr.js",
  "/mobile/assets/web-BEGz8DnN.js",
  "/mobile/assets/web-Bq85ucHN.js",
  "/mobile/assets/web-DdD-7P6s.js",
  "/mobile/icon-192.png",
  "/mobile/icon-192.svg",
  "/mobile/icon-512.png",
  "/mobile/icon-512.svg",
  "/mobile/index.html",
  "/mobile/manifest.json"
];

function fetchWithTimeout(request, options = {}, timeoutMs = NETWORK_TIMEOUT_MS) {
  if (typeof AbortController === "undefined") {
    return fetch(request, options);
  }
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(request, { ...options, signal: controller.signal }).finally(() => {
    clearTimeout(timerId);
  });
}

async function sanitizeForCache(response) {
  if (!response || !response.redirected) {
    return response;
  }
  const body = await response.clone().arrayBuffer();
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: new Headers(response.headers),
  });
}

async function matchShellFromCache(request) {
  return (
    (await caches.match(request, { ignoreSearch: true })) ||
    (await caches.match("/mobile/index.html")) ||
    (await caches.match("/mobile/"))
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return Promise.all(
        ASSETS_TO_CACHE.map((assetUrl) =>
          fetchWithTimeout(assetUrl, { cache: "no-store" }, 5000)
            .then(async (res) => {
              if (res && res.ok) {
                const cleanRes = await sanitizeForCache(res);
                return cache.put(assetUrl, cleanRes);
              }
              return cache.add(assetUrl);
            })
            .catch(() => cache.add(assetUrl).catch(() => null))
        )
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  const url = new URL(event.request.url);

  // Peticiones de API: directo a red (o catálogo con fallback caché sin colgar UI)
  if (url.pathname.startsWith("/api/")) {
    if (url.pathname === "/api/mobile/catalog") {
      event.respondWith(
        fetchWithTimeout(event.request, {}, 5000)
          .then((response) => {
            if (response && response.ok) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
            }
            return response;
          })
          .catch(() => caches.match(event.request))
      );
      return;
    }
    return;
  }

  // Navegación HTML principal (/mobile/, /mobile/index.html): App Shell Cache-First instantánea
  // Evita esperar timeouts TCP (20-75s) cuando Docker/PC está apagado.
  // Las actualizaciones nuevas se descargan atómicamente vía sw.js (CACHE_NAME con hash de build).
  if (
    event.request.mode === "navigate" ||
    url.pathname === "/mobile" ||
    url.pathname === "/mobile/" ||
    url.pathname === "/mobile/index.html"
  ) {
    event.respondWith(
      (async () => {
        const cached = await matchShellFromCache(event.request);
        if (cached) {
          return cached;
        }
        try {
          const networkResponse = await fetchWithTimeout("/mobile/index.html", { cache: "no-store" }, NETWORK_TIMEOUT_MS);
          if (networkResponse && networkResponse.status === 200) {
            const cleanRes = await sanitizeForCache(networkResponse);
            const cache = await caches.open(CACHE_NAME);
            await cache.put("/mobile/index.html", cleanRes.clone());
            await cache.put("/mobile/", cleanRes.clone());
            return cleanRes;
          }
          return networkResponse;
        } catch {
          return (await matchShellFromCache(event.request)) || Response.error();
        }
      })()
    );
    return;
  }

  // Recursos estáticos (bundles JS/CSS de Vite, iconos, manifest): cache-first con fallback con timeout
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetchWithTimeout(event.request, {}, NETWORK_TIMEOUT_MS).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      });
    }).catch(async () => {
      if (event.request.mode === "navigate") {
        return (await matchShellFromCache(event.request)) || Response.error();
      }
      return Response.error();
    })
  );
});
