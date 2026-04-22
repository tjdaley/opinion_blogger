"""
notifier_webhook.py - FastAPI webhook that receives inbound SMS from Twilio.

Runs as a long-lived service on the same host as the pipeline. HAProxy routes
https://sms.jdbot.us/webhooks/twilio/sms to this app on 127.0.0.1:8080.

Commands (v1):
  status              - counts of opinion_tracking rows by status
  retry <case_number> - reset a case to pending-analysis and run one classify pass
  help                - show available commands
"""
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import Response
from twilio.request_validator import RequestValidator

import twilio_notifier
from db.connection import opinion_tracking_repo
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

app = FastAPI(title="Opinion Blogger SMS Webhook")

# Must match the exact URL Twilio is configured to hit, or signature validation will fail.
WEBHOOK_URL = "https://sms.jdbot.us/webhooks/twilio/sms"

HELP_TEXT = (
    "Commands:\n"
    "  status\n"
    "  retry <case_number>\n"
    "  help"
)


def _twiml(body: str) -> Response:
    # Escape XML-special chars in the reply body.
    safe = (
        body.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'
    return Response(content=xml, media_type="application/xml")


async def _run_retry(case_number: str):
    """Background task: reset a case to pending-analysis and re-run the classifier."""
    try:
        row = opinion_tracking_repo.select_one(condition={"case_number": case_number})
        if not row:
            twilio_notifier.send(f"retry {case_number}: case not found")
            return

        row.status = "pending-analysis"
        opinion_tracking_repo.update(row.id, row.model_dump(mode="json"))

        from classify_opinions import classify_pending
        await classify_pending()

        updated = opinion_tracking_repo.select_one(condition={"case_number": case_number})
        new_status = updated.status if updated else "missing"
        twilio_notifier.send(f"retry {case_number} -> {new_status}")
    except Exception as e:
        logger.exception("retry failed for %s", case_number)
        twilio_notifier.send(f"retry {case_number} error: {e}")


@app.post("/webhooks/twilio/sms")
async def inbound_sms(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(settings.twilio_auth_token)
    post_vars = {k: v for k, v in form.items()}  # type: ignore
    if not validator.validate(WEBHOOK_URL, post_vars, signature):
        logger.warning("Twilio signature validation failed")
        raise HTTPException(status_code=403, detail="Invalid signature")

    sender = form.get("From", "") or ""
    body = ((form.get("Body", "") or "")).strip()  # type: ignore

    if sender != settings.operator_phone_number:
        logger.warning("Rejecting SMS from unauthorized sender %s", sender)
        return _twiml("Unauthorized.")

    logger.info("Inbound SMS from %s: %s", sender, body)

    parts = body.split(maxsplit=1)
    if not parts:
        return _twiml(HELP_TEXT)

    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "status":
        return _twiml(twilio_notifier.status_summary())

    if cmd == "retry":
        if not arg:
            return _twiml("Usage: retry <case_number>")
        background_tasks.add_task(_run_retry, arg)
        return _twiml(f"Queued retry for {arg}. Will SMS when done.")

    if cmd == "help":
        return _twiml(HELP_TEXT)

    return _twiml(f"Unknown command '{cmd}'.\n{HELP_TEXT}")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
