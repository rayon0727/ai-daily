// AI 晨报总览 · Service Worker
// 策略：HTML 页面网络优先（确保每天新晨报立即可见），静态资源缓存优先
const CACHE = 'ai-daily-v1';
const PRECACHE = ['./manifest.webmanifest', './icon-192.png', './icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // HTML 页面：网络优先，失败回退缓存
  if (req.mode === 'navigate' || req.headers.get('accept')?.includes('text/html')) {
    e.respondWith(
      fetch(req).then(r => {
        const copy = r.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
        return r;
      }).catch(() => caches.match(req).then(m => m || caches.match('./index.html')))
    );
    return;
  }

  // 静态资源：缓存优先
  e.respondWith(
    caches.match(req).then(m => m || fetch(req).then(r => {
      const copy = r.clone();
      caches.open(CACHE).then(c => c.put(req, copy));
      return r;
    }))
  );
});

// ---- Push 通知 ----
self.addEventListener('push', e => {
  let data = { title: 'AI 晨报', body: '今日晨报已更新', url: './index.html' };
  try { data = Object.assign(data, e.data ? e.data.json() : {}); } catch (_) {}
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: './icon-192.png',
      badge: './icon-192.png',
      data: { url: data.url },
      vibrate: [100, 60, 100]
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const c of list) { if ('focus' in c) return c.focus(); }
      return clients.openWindow(e.notification.data.url || './index.html');
    })
  );
});
