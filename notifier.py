"""
notifier.py - Vendor dispatcher for outbound SMS.

Re-exports `send` and `status_summary` from whichever vendor module is selected
via `settings.notification_vendor` ('twilio' or 'clicksend'). Pipeline code
imports from here only and never sees the gateway-specific modules directly.
"""
from util.settings import settings

if settings.notification_vendor == "clicksend":
    from notifiers.clicksend.clicksend_notifier import send, status_summary, reply
elif settings.notification_vendor == "telegram":
    from notifiers.telegram.telegram_notifier import send, status_summary, reply
else:
    raise ValueError(f"Unsupported notification vendor: {settings.notification_vendor}")

__all__ = ["send", "status_summary", "reply"]
