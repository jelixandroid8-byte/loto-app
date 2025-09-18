// Minimal service worker using cache-first for app shell
const CACHE_NAME = 'lotoweb-v1';
// Keep APP_SHELL minimal and avoid caching the site root to prevent serving a bad cached
// response for '/' which can cause navigation failures in some environments.
const APP_SHELL = [
  '/static/style.css',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

// Fallback page for navigation requests when network is unavailable
const NAV_FALLBACK = '/lh-test';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL.concat([NAV_FALLBACK]).filter(Boolean)))
      .then(() => {
        // Activate this service worker immediately without waiting for old workers to be released.
        // This helps CI audits (like Lighthouse) detect a controlling service worker on the next navigation.
        try { self.skipWaiting(); } catch (e) { /* skipWaiting not available in some environments */ }
      })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // For navigation requests (page loads), try network first then fall back to cached NAV_FALLBACK.
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).then((response) => {
        return response;
      }).catch(() => caches.match(NAV_FALLBACK))
    );
    return;
  }

  // For other requests, use cache-first for performance
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
