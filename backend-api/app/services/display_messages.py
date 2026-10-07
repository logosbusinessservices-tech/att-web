"""Gate-monitor announcements: one shared, ordered list managed by EAs.

Every gate monitor shows the same list, so all rules live here: text cleanup,
the length and count limits, soft removal (kept for audit), reordering, and the
version string the monitors use to download only when something changed.
"""

import hashlib
import json
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import DisplayMessage, Person


class DisplayMessageError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(raw: str) -> str:
    """Single-line, trimmed, no control characters; enforce the length limits.

    Only Cc control characters are dropped — format characters such as the
    zero-width joiners Hindi text relies on are kept.
    """
    without_controls = "".join(
        ch if unicodedata.category(ch) != "Cc" else " " for ch in raw or ""
    )
    text = " ".join(without_controls.split())
    if not text:
        raise DisplayMessageError("Enter a message.", status_code=422)
    if len(text) > settings.display_message_max_chars:
        raise DisplayMessageError(
            f"Keep messages to {settings.display_message_max_chars} characters "
            f"(this one has {len(text)}).",
            status_code=422,
        )
    return text


def active_messages(db: Session) -> list[DisplayMessage]:
    return list(db.execute(
        select(DisplayMessage)
        .where(DisplayMessage.removed_at.is_(None))
        .order_by(DisplayMessage.position, DisplayMessage.id)
    ).scalars().all())


def _get_active(db: Session, message_id: int) -> DisplayMessage:
    msg = db.get(DisplayMessage, message_id)
    if msg is None or msg.removed_at is not None:
        raise DisplayMessageError("Message not found.", status_code=404)
    return msg


def add_message(db: Session, author: Person, raw_text: str) -> DisplayMessage:
    """Append a message to the bottom of the board."""
    text = clean_text(raw_text)
    current = active_messages(db)
    if len(current) >= settings.display_message_max_count:
        raise DisplayMessageError(
            f"The board already has {settings.display_message_max_count} messages. "
            "Remove one before adding another.",
            status_code=409,
        )
    next_position = (max(m.position for m in current) + 1) if current else 0
    msg = DisplayMessage(text=text, position=next_position, created_by=author.id)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def edit_message(db: Session, editor: Person, message_id: int, raw_text: str) -> DisplayMessage:
    msg = _get_active(db, message_id)
    text = clean_text(raw_text)
    if text != msg.text:
        msg.text = text
        msg.updated_by = editor.id
        msg.updated_at = _now()
        db.commit()
        db.refresh(msg)
    return msg


def remove_message(db: Session, remover: Person, message_id: int) -> None:
    """Soft delete: the row stays for audit but leaves the board."""
    msg = _get_active(db, message_id)
    msg.removed_at = _now()
    msg.removed_by = remover.id
    db.commit()


def reorder_messages(db: Session, editor: Person, ids: list[int]) -> list[DisplayMessage]:
    """Apply a new order. `ids` must be exactly the current active messages, so
    a page that's out of date (someone else changed the list) can't silently
    drop or resurrect a message."""
    current = active_messages(db)
    if len(ids) != len(set(ids)) or set(ids) != {m.id for m in current}:
        raise DisplayMessageError(
            "The message list has changed. Refresh and try again.", status_code=409
        )
    by_id = {m.id: m for m in current}
    for position, message_id in enumerate(ids):
        msg = by_id[message_id]
        if msg.position != position:
            msg.position = position
    db.commit()
    return active_messages(db)


def board_version(messages: list[DisplayMessage]) -> str:
    """Short fingerprint of exactly what a monitor would display."""
    payload = json.dumps([[m.id, m.text] for m in messages], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
