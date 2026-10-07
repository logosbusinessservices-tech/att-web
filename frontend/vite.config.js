import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// PWA config makes the site installable to the home screen and work like an app.
// Camera (getUserMedia) + GPS (geolocation) require HTTPS in production, which
// Vercel provides automatically.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      workbox: {
        // The MediaPipe WASM/model are large; don't precache them. Instead cache
        // on first use (CacheFirst) so liveness works offline after one online run.
        globIgnores: ['**/mediapipe/**'],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/mediapipe/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'mediapipe-assets',
              expiration: { maxEntries: 12 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
      manifest: {
        name: 'RVNL Attendance',
        short_name: 'Attendance',
        description: 'Employee & supervisor attendance',
        theme_color: '#25201C',
        background_color: '#f7f7f4',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    // The large MediaPipe model shouldn't be file-watched (locks/EBUSY on Windows).
    watch: { ignored: ['**/public/mediapipe/**'] },
    // Proxy API calls to the backend during dev so the frontend uses same-origin /api.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
