"""
telegram_notifier.py - Outbound messaging via the Telegram Bot API.

Plug-compatible with twilio_notifier and clicksend_notifier: exposes
`send(message) -> bool` and `status_summary() -> str`. Uses the raw HTTP
Bot API (no extra dependency beyond requests).

Failures never raise — they log and return False.
"""
import requests

from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

API_BASE = "https://api.telegram.org"


def send(message: str) -> bool:
    """Send a Telegram message to the operator's chat. Never raises."""
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        logger.warning("Telegram bot token / chat id not configured; skipping: %s", message)
        return False
    url = f"{API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    try:
        # Telegram messages max out at 4096 chars — cap under that to be safe.
        payload = {
            "chat_id": settings.telegram_chat_id,
            "text": message[:4000],
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            logger.error("Telegram send returned not-ok: %s", data)
            return False
        logger.info("Sent Telegram message (message_id=%s)", data.get("result", {}).get("message_id"))
        return True
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
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
