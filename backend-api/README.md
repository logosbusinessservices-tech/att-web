# backend-api

FastAPI service for att-web: auth, attendance, edge event ingestion, and face 1:1
verification (ArcFace `buffalo_s`) + geofencing for field attendance.

## Layout

```
app/
  main.py            FastAPI entrypoint (/health, /docs, CORS, routers)
  config.py          all settings from .env
  db/
    database.py      engine/session — SQLite (dev) or Postgres (prod) via DATABASE_URL
    models.py        tables: persons, face_embeddings, attendance_events (+ web cols),
                     departments, stations, attendance_overrides, disputes, leave_requests
    init_db.py       create tables
  face/
    model.py         buffalo_s wrapper — embeddings identical to the pipeline
    verify.py        1:1 cosine verify (FIELD_MATCH_THRESHOLD)
  geo/geofence.py    Haversine center+radius geofence per station
  auth/
    security.py      bcrypt + JWT
    deps.py          current-user / supervisor guards
  routers/           auth, attendance, employees, supervisor, events
scripts/seed_password.py   set a login password for a person
edge/push_events.py        edge -> cloud push with offline retry queue
```

## Dev setup (this laptop, SQLite)

The venv and dependencies are already installed. Then:

```powershell
cd backend-api
Copy-Item .env.example .env          # then edit JWT_SECRET / EDGE_API_KEY
.\.venv\Scripts\python.exe -m app.db.init_db          # create tables
# create a login (creates the person if missing):
.\.venv\Scripts\python.exe -m scripts.seed_password EMP001 "pass123" --role employee --name "Test Employee"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs to try the API. Log in via `POST /auth/login`
(username = external_id, e.g. `EMP001`).

## Switching to Postgres (production, other laptop)

1. Create a Neon/Supabase Postgres (pgvector available).
2. Set `DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/DB` in `.env`.
3. Uncomment the psycopg/pgvector lines in `requirements.txt` and install them.
No app code changes.

## Deploy (Render/Railway)

Uses the `Dockerfile`. Set env vars (`DATABASE_URL`, `JWT_SECRET`, `EDGE_API_KEY`,
`CORS_ORIGINS`) in the host dashboard. Not needed for local dev.
