"""
notifier.py - Outbound SMS notification to the operator via Twilio.

Thin wrapper so the rest of the pipeline never imports Twilio directly.
Failures in SMS delivery never raise — they log and return False, so a
transient Twilio outage can't take down the pipeline.
"""
from typing import Optional

from twilio.rest import Client

from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

_client: Optional[Client] = None


def _get_client() -> Optional[Client]:
    global _client
    if _client is not None:
        return _client
    if not (settings.twilio_account_sid and settings.twilio_auth_token):
        logger.warning("Twilio credentials not configured; SMS disabled.")
        return None
    _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def send(message: str) -> bool:
    """Send an SMS to the operator. Never raises."""
    if not (settings.twilio_phone_number and settings.operator_phone_number):
        logger.warning("Twilio/operator phone numbers not configured; skipping SMS: %s", message)
        return False
    client = _get_client()
    if client is None:
        return False
    try:
        # Cap at ~10 segments (1600 chars) so a runaway log line can't burn a fortune.
        body = message[:1500]
        msg = client.messages.create(
            body=body,
            from_=settings.twilio_phone_number,
            to=settings.operator_phone_number,
        )
        logger.info("Sent SMS (sid=%s)", msg.sid)
        return True
    except Exception as e:
        logger.error("Failed to send SMS: %s", e)
        return False


def status_summary() -> str:
    """Return a short string with current opinion_tracking counts by status."""
    from db.connection import opinion_tracking_repo
    statuses = [
        "pending-analysis",
        "pending-family-review",
        "pending-blog",
        "rejected",
    ]
    parts = []
    for s in statuses:
        try:
            _, count = opinion_tracking_repo.select_many(condition={"status": s})  # type: ignore
            parts.append(f"{s}={count or 0}")
        except Exception as e:
            logger.error("status_summary: failed counting %s: %s", s, e)
            parts.append(f"{s}=?")
    return " ".join(parts)
