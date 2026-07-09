"""
clicksend_notifier_webhook.py - FastAPI webhook for inbound SMS from ClickSend.

Plug-compatible with twilio_notifier_webhook.py: exposes `app` (FastAPI),
/healthz, and a POST endpoint that accepts the gateway's inbound-SMS callback.

Differences from the Twilio version:
  * ClickSend has no HMAC signature scheme. We require a shared-secret token
    in the URL query string (?token=...) and validate against
    `settings.clicksend_webhook_token`.
  * ClickSend doesn't support inline replies (no TwiML equivalent). The handler
    returns HTTP 200 immediately, and the reply is sent as a separate outbound
    SMS via clicksend_notifier.send() in a background task.
  * Field names on the inbound POST are read defensively (form or JSON, with
    aliases) because ClickSend's docs are inconsistent. The full payload is
    logged on first receipt so you can verify the exact shape.
"""
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

import notifiers.clicksend.clicksend_notifier as clicksend_notifier
from db.connection import opinion_tracking_repo
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

app = FastAPI(title="Opinion Blogger SMS Webhook (ClickSend)")

HELP_TEXT = (
    "Commands:\n"
    "  status\n"
    "  retry <case_number>\n"
    "  help"
)


def _field(payload: Dict[str, Any], *names: str) -> str:
    """Return the first non-empty value for any of the given keys (case-insensitive)."""
    lowered = {k.lower(): v for k, v in payload.items()}
    for n in names:
        v = lowered.get(n.lower())
        if v:
            return str(v).strip()
    return ""


async def _run_retry(case_number: str):
    """Background task: reset a case to pending-analysis and re-run the classifier."""
    try:
        row = opinion_tracking_repo.select_one(condition={"case_number": case_number})
        if not row:
            clicksend_notifier.send(f"retry {case_number}: case not found")
            return

        row.status = "pending-analysis"
        opinion_tracking_repo.update(row.id, row.model_dump(mode="json"))

        from classify_opinions import classify_pending
        await classify_pending()

        updated = opinion_tracking_repo.select_one(condition={"case_number": case_number})
        new_status = updated.status if updated else "missing"
        clicksend_notifier.send(f"retry {case_number} -> {new_status}")
    except Exception as e:
        logger.exception("retry failed for %s", case_number)
        clicksend_notifier.send(f"retry {case_number} error: {e}")

def reply(text: str):
    _reply(text)

def _reply(text: str):
    """ClickSend has no inline reply — send the response as an outbound SMS."""
    clicksend_notifier.send(text)


async def _dispatch(body: str, background_tasks: BackgroundTasks):
    parts = body.split(maxsplit=1)
    if not parts:
        _reply(HELP_TEXT)
        return

    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "status":
        _reply(clicksend_notifier.status_summary())
        return

    if cmd == "retry":
        if not arg:
            _reply("Usage: retry <case_number>")
            return
        _reply(f"Queued retry for {arg}. Will SMS when done.")
        background_tasks.add_task(_run_retry, arg)
        return

    if cmd == "help":
        _reply(HELP_TEXT)
        return

    _reply(f"Unknown command '{cmd}'.\n{HELP_TEXT}")


@app.post("/webhooks/clicksend/sms")
async def inbound_sms(request: Request, background_tasks: BackgroundTasks):
    # 1. Shared-secret token check (ClickSend has no HMAC)
    token = str(request.query_params.get("token", ""))  # type: ignore
    if not settings.clicksend_webhook_token or token != settings.clicksend_webhook_token:
        logger.warning("ClickSend webhook token (%s) invalid or missing", token or "<none>")
        raise HTTPException(status_code=403, detail="Invalid token")

    # 2. Parse payload defensively — form-encoded or JSON, unknown exact fields
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = {k: v for k, v in form.items()}  # type: ignore

    logger.info("Inbound ClickSend payload: %s", payload)

    # Documented ClickSend inbound fields: from, body, to, message_id,
    # timestamp_send, custom_string, original_body, original_message_id, _keyword.
    sender = _field(payload, "from")
    body = _field(payload, "body")

    # 3. Sender authorization — only the operator can issue commands
    if sender != settings.operator_phone_number:
        logger.warning("Rejecting SMS from unauthorized sender %r", sender)
        return {"status": "ignored"}

    logger.info("Inbound SMS from %s: %s", sender, body)

    # 4. Dispatch, but respond to ClickSend immediately — the reply is a separate SMS
    background_tasks.add_task(_dispatch, body, background_tasks)
    return {"status": "accepted"}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
