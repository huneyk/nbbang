/* eslint-disable no-restricted-globals */
// Npang PWA Service Worker
// 최소한의 설치 가능 요건을 충족하고, 정적 자산에 한해 간단한 캐시를 제공합니다.

const CACHE_NAME = 'npang-static-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/favicon.png',
  '/Nbang_icon.png',
  '/Nbang_icon_180.png',
  '/Nbang_icon_192.png',
  '/Nbang_icon_512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS).catch(() => undefined))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // API 요청이나 동적 요청은 항상 네트워크 우선으로 처리합니다(캐시 사용 안 함).
  const url = new URL(request.url);
  const isSameOrigin = url.origin === self.location.origin;
  const isApi = url.pathname.startsWith('/api/');

  if (request.method !== 'GET' || !isSameOrigin || isApi) return;

  // 네비게이션 요청: 네트워크 우선, 실패 시 캐시된 index.html 로 폴백.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/index.html'))
    );
    return;
  }

  // 정적 자산: 캐시 우선, 없으면 네트워크에서 받고 캐시에 저장.
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type !== 'basic') return response;
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => cached);
    })
  );
});
