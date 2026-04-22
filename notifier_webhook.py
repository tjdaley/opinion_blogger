"""
notifier_webhook.py - Vendor dispatcher for the inbound SMS webhook.

Re-exports the FastAPI `app` from whichever vendor webhook module is selected
via `settings.notification_vendor` ('twilio' or 'clicksend'). systemd's
ExecStart references `notifier_webhook:app` and stays stable across vendors.
"""
from util.settings import settings

if settings.notification_vendor == "clicksend":
    from clicksend_notifier_webhook import app
elif settings.notification_vendor == "telegram":
    from telegram_notifier_webhook import app
else:
    from twilio_notifier_webhook import app

__all__ = ["app"]
