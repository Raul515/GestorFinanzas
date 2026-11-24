// Service Worker para Gestor Finanzas Quick-Capture PWA (Spec 016)
const CACHE_NAME = "gestor-finanzas-mobile-v1";
const ASSETS_TO_CACHE = [
  "/mobile/",
  "/mobile/index.html",
  "/mobile/manifest.json",
  "/mobile/icon-192.png",
  "/mobile/icon-512.png",
  "/mobile/icon-192.svg",
  "/mobile/icon-512.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
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
  const url = new URL(event.request.url);

  // Peticiones de API: network-first o network-only
  if (url.pathname.startsWith("/api/")) {
    if (url.pathname === "/api/mobile/catalog") {
      // Catálogo: network-first con fallback a caché
      event.respondWith(
        fetch(event.request)
          .then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
            }
            return response;
          })
          .catch(() => caches.match(event.request))
      );
      return;
    }

    // El resto de API (sync, status): directo a red
    return;
  }

  // Recursos estáticos del frontend: cache-first con fallback a red
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      });
    }).catch(() => {
      // Fallback a index.html para navegación SPA
      if (event.request.mode === "navigate") {
        return caches.match("/mobile/index.html");
      }
    })
  );
});
