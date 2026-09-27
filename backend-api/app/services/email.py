"""Email sender used for 2FA password-change codes.

Providers:
  • "console" (dev): logs the message so you can test without a mail server.
  • "smtp" (prod): send via a configured SMTP server (left as a stub — wire your
    own SMTP creds when deploying).
"""

import logging

from app.config import settings

log = logging.getLogger("email")


def send_email(to: str, subject: str, body: str) -> None:
    provider = settings.email_provider
    if provider == "console":
        log.info("EMAIL to %s | %s | %s", to, subject, body)
        print(f"[email:console] to={to} | {subject} | {body}")
        return
    if provider == "smtp":  # pragma: no cover - deployment-specific
        raise RuntimeError("SMTP email provider is not configured. Set up smtplib here.")
    raise RuntimeError(f"Unknown email provider: {provider!r}")
