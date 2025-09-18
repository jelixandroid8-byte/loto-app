// Minimal service worker using cache-first for app shell
const CACHE_NAME = 'lotoweb-v1';
const APP_SHELL = [
  '/',
  '/login',
  '/static/style.css',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => {
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
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
