"""Shared-secret guard for the edge (NUC) endpoints."""

import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


def require_edge_key(x_edge_key: str | None = Header(default=None)):
    """Accept the request only if X-Edge-Key matches EDGE_API_KEY.

    compare_digest takes the same time however many characters match, so the
    key can't be guessed one character at a time from response timings.
    """
    if not x_edge_key or not secrets.compare_digest(
        x_edge_key.encode("utf-8"), settings.edge_api_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid edge API key"
        )
