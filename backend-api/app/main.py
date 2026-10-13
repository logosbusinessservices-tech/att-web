"""FastAPI entrypoint.

Run (dev): backend-api/.venv/Scripts/python.exe -m uvicorn app.main:app --reload
Docs:      http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import assert_production_secrets, settings
from app.db.database import engine
from app.db.init_db import init_db
from app.db.migrate import run_migrations
from app.routers import (
    analytics,
    assistant,
    attendance,
    auth,
    display_messages,
    disputes,
    edge,
    employees,
    events,
    field,
    notifications,
    signage_media,
    supervisor,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_production_secrets(settings)
    init_db()
    run_migrations(engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(field.router)
app.include_router(employees.router)
app.include_router(supervisor.router)
app.include_router(assistant.router)
app.include_router(display_messages.router)
app.include_router(analytics.router)
app.include_router(disputes.router)
app.include_router(events.router)
app.include_router(edge.router)
app.include_router(signage_media.router)
app.include_router(notifications.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "env": settings.environment}
