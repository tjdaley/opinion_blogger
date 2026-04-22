"""
telegram_notifier_webhook.py - FastAPI webhook for inbound Telegram updates.

Plug-compatible with the twilio/clicksend webhooks: exposes `app`, /healthz,
and an inbound endpoint. Authentication uses Telegram's own scheme: when you
register the webhook via setWebhook, you supply a `secret_token` and Telegram
includes it in the X-Telegram-Bot-Api-Secret-Token header on every update.

Telegram has no TwiML-style inline reply, so responses go out as a fresh
sendMessage call via telegram_notifier.send().
"""
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

import telegram_notifier
from db.connection import opinion_tracking_repo
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

app = FastAPI(title="Opinion Blogger Webhook (Telegram)")

HELP_TEXT = (
    "Commands:\n"
    "  status\n"
    "  retry <case_number>\n"
    "  help"
)


async def _run_retry(case_number: str):
    """Background task: reset a case to pending-analysis and re-run the classifier."""
    try:
        row = opinion_tracking_repo.select_one(condition={"case_number": case_number})
        if not row:
            telegram_notifier.send(f"retry {case_number}: case not found")
            return

        row.status = "pending-analysis"
        opinion_tracking_repo.update(row.id, row.model_dump(mode="json"))

        from classify_opinions import classify_pending
        await classify_pending()

        updated = opinion_tracking_repo.select_one(condition={"case_number": case_number})
        new_status = updated.status if updated else "missing"
        telegram_notifier.send(f"retry {case_number} -> {new_status}")
    except Exception as e:
        logger.exception("retry failed for %s", case_number)
        telegram_notifier.send(f"retry {case_number} error: {e}")


def _reply(text: str):
    """Telegram has no inline reply on the webhook — send as an outbound message."""
    telegram_notifier.send(text)


async def _dispatch(body: str, background_tasks: BackgroundTasks):
    parts = body.split(maxsplit=1)
    if not parts:
        _reply(HELP_TEXT)
        return

    cmd = parts[0].lstrip("/").lower()  # allow either "status" or "/status"
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "status":
        _reply(telegram_notifier.status_summary())
        return

    if cmd == "retry":
        if not arg:
            _reply("Usage: retry <case_number>")
            return
        _reply(f"Queued retry for {arg}. Will message when done.")
        background_tasks.add_task(_run_retry, arg)
        return

    if cmd in ("help", "start"):
        _reply(HELP_TEXT)
        return

    _reply(f"Unknown command '{cmd}'.\n{HELP_TEXT}")


@app.post("/webhooks/telegram/updates")
async def inbound_update(request: Request, background_tasks: BackgroundTasks):
    # 1. Secret-token check (Telegram puts it in this header on every call).
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not settings.telegram_webhook_secret or received != settings.telegram_webhook_secret:
        logger.warning("Telegram webhook secret invalid or missing")
        raise HTTPException(status_code=403, detail="Invalid secret")

    update = await request.json()
    logger.info("Inbound Telegram update: %s", update)

    message = update.get("message") or update.get("edited_message")
    if not message:
        # Not a text update (e.g., callback_query, channel_post) — ignore for v1.
        return {"status": "ignored"}

    chat_id = str((message.get("chat") or {}).get("id", ""))
    text = (message.get("text") or "").strip()

    # 2. Authorization: only the operator's chat can issue commands.
    if chat_id != str(settings.telegram_chat_id):
        logger.warning("Rejecting Telegram message from unauthorized chat %s", chat_id)
        return {"status": "ignored"}

    logger.info("Inbound Telegram from chat %s: %s", chat_id, text)

    # 3. Dispatch; reply is a separate outbound sendMessage call.
    background_tasks.add_task(_dispatch, text, background_tasks)
    return {"status": "accepted"}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
