import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './lib/auth.jsx'
import './index.css'

import { registerSW } from 'virtual:pwa-register'

// Register the service worker and automatically reload the page when a new
// version has taken over. With skipWaiting + clientsClaim in workbox, the
// new SW activates on first visit after a deploy; this line then triggers
// one clean reload so the user sees the new UI immediately instead of the
// stale cached one.
registerSW({
  immediate: true,
  onRegisteredSW(_, registration) {
    // Also poll every 60s while the app is open, so a user who leaves it
    // running catches new deploys without having to close+reopen.
    if (registration) {
      setInterval(() => { registration.update().catch(() => {}) }, 60 * 1000)
    }
  },
  onNeedRefresh() {
    // New SW is waiting — reload once to pick it up.
    window.location.reload()
  },
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)

