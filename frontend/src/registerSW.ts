// Registers the service worker that makes the tracker installable and offline-tolerant.
// Only in a production build: a cached shell during `vite dev` hides your own edits.
export function registerServiceWorker() {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // An unregistered worker only costs offline support, so failing is survivable.
    })
  })
}
