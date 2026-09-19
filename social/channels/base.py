"""
base.py - What every social channel adapter provides, and the error the
publisher treats as permanent.

Errors, as in instagram/graph.py:
  * PlatformAPIError - the platform answered and refused. Retrying won't help;
    the post gets the <channel>_failed tag for a human.
  * requests exceptions (DNS, timeout, connection) - transient; retried next run.
"""
from typing import Optional, Protocol, Tuple

import requests

from social.compose import Composed


class PlatformAPIError(Exception):
    pass


def check(r: requests.Response, what: str) -> dict:
    """Return the JSON body, or raise PlatformAPIError with the platform's message."""
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code >= 400 or (isinstance(body, dict) and "error" in body):
        err = body.get("error", {}) if isinstance(body, dict) else {}
        msg = err.get("message") if isinstance(err, dict) else None
        raise PlatformAPIError(f"{what} -> {r.status_code}: {msg or r.text[:300]}")
    return body


class Channel(Protocol):
    name: str

    def missing_config(self) -> Optional[str]:
        """A message naming missing settings, or None when ready to post."""

    def refresh_if_due(self) -> Optional[str]:
        """Keep credentials alive. Returns an error message, or None."""

    def publish(self, post: Composed) -> Tuple[str, Optional[str]]:
        """Publish and return (remote_id, permalink)."""
