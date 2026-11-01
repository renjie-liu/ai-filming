// Runtime env. Docker/Nginx deployments overwrite this file via the entrypoint script.
// Default: when the UI is served from the Vite dev server on localhost, talk to the
// local backend on :8000; on any other host (e.g. Vercel) use same-origin `/api/v1/...`.
window.__ENV = window.__ENV || {}
if (window.__ENV.BACKEND_URL === undefined) {
  var __h = window.location.hostname
  var __isLocal = __h === 'localhost' || __h === '127.0.0.1'
  window.__ENV.BACKEND_URL = __isLocal && window.location.port !== '8000' ? 'http://localhost:8000' : ''
}
