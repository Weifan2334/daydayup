/* 明管家 v0.3.2 service worker — 桌面端禁用离线缓存，每次启动强制刷新 */
// 原因：Electron 桌面端后端始终本地可用，service worker 缓存会导致前端更新后仍显示旧界面。
// 本 service worker 安装后主动注销自身并清空所有缓存，让后续请求直接走网络。

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
      .then(() => self.registration.unregister())
      .catch(() => {})
  );
});

self.addEventListener('fetch', (event) => {
  // 不再拦截任何请求，让浏览器直接请求后端
});
