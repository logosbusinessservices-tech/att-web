# att-web

Railway office attendance management website — mobile-first PWA + API, built on top of an existing
facial-recognition camera pipeline (separate repo).

- **backend-api/** — FastAPI service: auth, attendance, face 1:1 verify (ArcFace `buffalo_s`), geofence, event ingestion.
- **frontend/** — React + Vite + Tailwind PWA (employee & supervisor modes).
- **_pipeline_reference/** — read-only copies of the pipeline's face/DB code so embeddings match exactly. Not shipped.

## Quick start (dev, this laptop — SQLite)

```powershell
# Backend
cd backend-api
.\.venv\Scripts\Activate.ps1        # venv already created
uvicorn app.main:app --reload       # http://127.0.0.1:8000/docs

# Frontend (later)
cd ../frontend
npm install
npm run dev
```

Dev uses SQLite (zero setup). Production switches to Postgres + pgvector by changing only `DATABASE_URL`.

See [backend-api/README.md](backend-api/README.md) for details.
