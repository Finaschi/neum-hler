// Minimal app-shell service worker: network-first, cache fallback.
// Keeps the app usable with a weak/absent signal out on the water once it
// has been opened at least once. Bump CACHE on any deploy that must
// invalidate old clients.
const CACHE = 'nms-shell-v5';
const SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  // Never cache Supabase Edge Function calls (markers API) — must always be
  // live. Match the domain generically, not a specific function slug: the
  // deployed slug ('dynamic-task') doesn't match its dashboard display name
  // ('markers-api'), and slugs can change again if the function is redeployed.
  if (req.url.indexOf('.supabase.co/functions/') !== -1) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req))
  );
});
