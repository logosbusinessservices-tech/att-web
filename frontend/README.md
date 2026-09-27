# frontend

React + Vite + Tailwind PWA (mobile-first). Employee & supervisor modes.

## Dev

```powershell
cd frontend
npm install
npm run dev            # http://localhost:5173
```

The dev server proxies `/api` to the backend at `http://127.0.0.1:8000`, so start
the backend first (see ../backend-api/README.md).

Test logins (after seeding on the backend):
- Employee: `EMP001` / `pass123`
- Supervisor: `SUP001` / `pass123`

## Build / deploy (Vercel)

```powershell
npm run build          # outputs dist/
```

On Vercel, set `VITE_API_BASE` to the deployed backend URL. Vercel provides HTTPS
and a `*.vercel.app` subdomain automatically (required for camera + GPS in Phase 3).

## Notes
- PWA (installable, offline shell) configured via `vite-plugin-pwa`.
- Add real `icon-192.png` / `icon-512.png` in `public/` before shipping the PWA.
- All timestamps are stored UTC and rendered in IST (`Asia/Kolkata`).
