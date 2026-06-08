// O2M Mood — service worker minimal.
// But : rendre la page installable en PWA (plein écran) sur Android/iOS.
// NB : un service worker ne s'enregistre QUE dans un contexte sécurisé (HTTPS
// ou localhost). En HTTP simple, l'enregistrement est refusé par le navigateur
// et l'app reste un simple raccourci (pas de plein écran). Ce fichier est donc
// prêt mais inactif tant que le site n'est pas servi en HTTPS.

const CACHE = 'o2m-mood-v1';
const SHELL = [
  '/mood',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {}))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Stratégie : réseau d'abord, repli cache. On NE met jamais en cache les appels
// API ni les flux Mopidy (toujours frais).
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/mopidy')) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.status === 200 && url.origin === self.location.origin) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match('/mood')))
  );
});
