"""Additive schema/data updates applied at startup (idempotent; safe on every boot).

create_all() only creates missing tables; it can't add columns to tables that
already exist in production. These steps fill that gap without anyone having to
open the database firewall and run a script by hand.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app import storage
from app.config import settings

log = logging.getLogger(__name__)


def run_migrations(engine: Engine) -> None:
    columns = {c["name"] for c in inspect(engine).get_columns("attendance_events")}
    with engine.begin() as conn:
        if "event_uuid" not in columns:
            conn.execute(text("ALTER TABLE attendance_events ADD COLUMN event_uuid VARCHAR"))
            log.info("Added attendance_events.event_uuid")
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_events_event_uuid "
            "ON attendance_events (event_uuid)"
        ))

        if storage.using_blob():
            # Photos saved on the old container disk were wiped by restarts; drop
            # their links so the site shows "no photo" instead of a broken image.
            like = f"{storage.BLOB_PREFIX}%"
            avatars = conn.execute(
                text("UPDATE persons SET avatar_path = NULL "
                     "WHERE avatar_path IS NOT NULL AND avatar_path NOT LIKE :p"),
                {"p": like},
            ).rowcount
            selfies = conn.execute(
                text("UPDATE attendance_events SET selfie_path = NULL "
                     "WHERE selfie_path IS NOT NULL AND selfie_path NOT LIKE :p"),
                {"p": like},
            ).rowcount
            if avatars or selfies:
                log.info("Cleared %s stale avatar and %s stale selfie link(s)", avatars, selfies)
