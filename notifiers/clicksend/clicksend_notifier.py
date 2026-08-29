"""
clicksend_notifier.py - Outbound SMS via ClickSend. Plug-compatible with
twilio_notifier.py: exposes `send(message) -> bool` and `status_summary() -> str`.

Failures never raise — they log and return False so transient gateway outages
can't take down the pipeline.
"""
from typing import Optional

import clicksend_client
from clicksend_client.rest import ApiException

from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

_api: Optional[clicksend_client.SMSApi] = None


def _get_api() -> Optional[clicksend_client.SMSApi]:
    global _api
    if _api is not None:
        return _api
    if not (settings.clicksend_username and settings.clicksend_api_key):
        logger.warning("ClickSend credentials not configured; SMS disabled.")
        return None
    config = clicksend_client.Configuration()
    config.username = settings.clicksend_username
    config.password = settings.clicksend_api_key
    _api = clicksend_client.SMSApi(clicksend_client.ApiClient(config))
    return _api


def reply(message: str) -> bool:
    """Send an operator-facing SMS. Present so the vendor modules stay
    plug-compatible with telegram_notifier, which prefixes the instance id."""
    return send(message)


def send(message: str) -> bool:
    """Send an SMS to the operator. Never raises."""
    if not (settings.clicksend_phone_number and settings.operator_phone_number):
        logger.warning("ClickSend/operator phone numbers not configured; skipping SMS: %s", message)
        return False
    api = _get_api()
    if api is None:
        return False
    try:
        body = message[:1500]
        sms_message = clicksend_client.SmsMessage(
            source="opinion-blogger",
            body=body,
            to=settings.operator_phone_number,
            from_=settings.clicksend_phone_number,
        )
        collection = clicksend_client.SmsMessageCollection(messages=[sms_message])
        resp = api.sms_send_post(collection)
        logger.info("Sent SMS via ClickSend: %s", resp)
        return True
    except ApiException as e:
        logger.error("ClickSend API error: %s", e)
        return False
    except Exception as e:
        logger.error("Failed to send SMS via ClickSend: %s", e)
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
