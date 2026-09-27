"""SMS delivery abstraction.

Dev/default provider is "console": it just logs the message (and the OTP code is
also returned in the API response when OTP_DEBUG_RETURN_CODE is on), so you can
test the whole flow with no SMS account. Swap SMS_PROVIDER=twilio in production
and fill the TWILIO_* settings.
"""

import logging

from app.config import settings

logger = logging.getLogger("sms")


def send_sms(to_phone: str, body: str) -> None:
    provider = settings.sms_provider.lower()
    if provider == "twilio":
        _send_twilio(to_phone, body)
    else:  # console / dev
        logger.warning("[SMS→%s] %s", to_phone, body)


def _send_twilio(to_phone: str, body: str) -> None:
    # Imported lazily so the dependency is only needed in production.
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError("twilio package not installed; `pip install twilio`") from exc
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    client.messages.create(to=to_phone, from_=settings.twilio_from_number, body=body)
