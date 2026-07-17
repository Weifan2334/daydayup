/* 明管家 v0.1 service worker — 离线缓存静态资源 */
const CACHE_NAME = 'daily-log-v0.1.5';
const CORE_ASSETS = [
  '/',
  '/static/styles.css',
  '/static/app.js',
  '/manifest.json',
  '/static/icons/icon-192.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  // API 永远走网络（不缓存实时数据）
  if (req.url.includes('/api/') || req.url.includes('/health')) return;

  event.respondWith(
    caches.match(req).then((cached) => {
      const fetchPromise = fetch(req).then((res) => {
        // 只缓存同源 GET 200
        if (res && res.status === 200 && res.type === 'basic') {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, clone));
        }
        return res;
      }).catch(() => cached);
      return cached || fetchPromise;
    })
  );
});