{% load static %}
/* Minimal service worker: makes the app installable and serves the cached
   shell + static assets when the network is unavailable. HTML pages are always
   fetched fresh (network-first) so clinical data is never stale. */
const CACHE = "bedtracker-v1";
const SHELL = [
  "{% static 'board.css' %}?v=16",
  "{% static 'htmx.min.js' %}",
  "{% static 'icon.svg' %}",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  } else {
    e.respondWith(fetch(req).catch(() => caches.match(req)));
  }
});
