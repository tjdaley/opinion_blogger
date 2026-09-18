"""
graph.py - Minimal client for Instagram content publishing (Instagram Login,
graph.instagram.com).

Errors come in two kinds, and the publisher treats them differently:
  * InstagramAPIError - Instagram answered and said no. Retrying the same post
    won't help, so it gets the failed tag for a human to look at.
  * requests exceptions (DNS, timeout, connection) - transient. The post is
    left alone and retried on the next run.
"""
import datetime
import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional, Tuple

import requests

from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
REFRESH_EVERY = datetime.timedelta(days=7)  # long-lived tokens last 60 days


class InstagramAPIError(Exception):
    pass


# ---------------------------------------------------------------- token ----

def _env_fingerprint() -> str:
    return hashlib.sha256(settings.instagram_access_token.encode()).hexdigest()[:16]


def _read_state() -> Optional[dict]:
    """The persisted token, unless .env has been given a different token since."""
    p = Path(settings.instagram_token_file)
    if not p.exists():
        return None
    state = json.loads(p.read_text(encoding="utf-8"))
    if state.get("env_fingerprint") != _env_fingerprint():
        return None  # operator pasted a new token into .env; it wins
    return state


def _write_state(token: str, refreshed_at: datetime.datetime, expires_in: Optional[int]) -> None:
    state = {
        "access_token": token,
        "env_fingerprint": _env_fingerprint(),
        "refreshed_at": refreshed_at.isoformat(),
        "expires_at": (refreshed_at + datetime.timedelta(seconds=expires_in)).isoformat() if expires_in else None,
    }
    Path(settings.instagram_token_file).write_text(json.dumps(state, indent=2), encoding="utf-8")


def token() -> str:
    state = _read_state()
    return state["access_token"] if state else settings.instagram_access_token


def refresh_token_if_due() -> Optional[str]:
    """Refresh the long-lived token weekly. Returns an error message, or None.

    The first time a token is seen, just record it: Instagram refuses to
    refresh a token less than 24 hours old, and a week-old refresh is well
    inside the 60-day life.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    state = _read_state()
    if state is None:
        _write_state(settings.instagram_access_token, now, None)
        return None
    if now - datetime.datetime.fromisoformat(state["refreshed_at"]) < REFRESH_EVERY:
        return None
    try:
        r = requests.get(REFRESH_URL, params={"grant_type": "ig_refresh_token",
                                              "access_token": state["access_token"]}, timeout=30)
        body = r.json()
        if r.status_code >= 400 or "access_token" not in body:
            return f"Instagram token refresh failed: {body.get('error', {}).get('message', r.text[:200])}"
        _write_state(body["access_token"], now, body.get("expires_in"))
        logger.info("Refreshed Instagram token; expires in %s days", (body.get("expires_in") or 0) // 86400)
        return None
    except Exception as e:
        return f"Instagram token refresh failed: {e}"


# ------------------------------------------------------------------ API ----

def _call(method: str, path: str, **data) -> dict:
    r = requests.request(
        method, f"{settings.instagram_graph_url}/{path}",
        headers={"Authorization": f"Bearer {token()}"},
        params=data if method == "GET" else None,
        data=data if method != "GET" else None,
        timeout=60,
    )
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code >= 400 or "error" in body:
        err = body.get("error", {})
        raise InstagramAPIError(f"{method} {path} -> {r.status_code}: {err.get('message') or r.text[:300]}")
    return body


def publishing_quota() -> Tuple[int, int]:
    """(posts used, posts allowed) in the rolling 24-hour window."""
    data = _call("GET", f"{settings.instagram_user_id}/content_publishing_limit",
                 fields="quota_usage,config")["data"][0]
    return data["quota_usage"], data["config"]["quota_total"]


def create_carousel_item(image_url: str, alt_text: str) -> str:
    return _call("POST", f"{settings.instagram_user_id}/media",
                 image_url=image_url, is_carousel_item="true", alt_text=alt_text)["id"]


def create_carousel(children: List[str], caption: str) -> str:
    return _call("POST", f"{settings.instagram_user_id}/media",
                 media_type="CAROUSEL", children=",".join(children), caption=caption)["id"]


def wait_until_ready(container_id: str, timeout_s: int = 300, every_s: int = 5) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        status = _call("GET", container_id, fields="status_code").get("status_code")
        if status in ("FINISHED", "PUBLISHED"):
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramAPIError(f"container {container_id} status {status}")
        if time.monotonic() > deadline:
            raise InstagramAPIError(f"container {container_id} still {status} after {timeout_s}s")
        time.sleep(every_s)


def publish(container_id: str) -> str:
    return _call("POST", f"{settings.instagram_user_id}/media_publish", creation_id=container_id)["id"]


def permalink(media_id: str) -> Optional[str]:
    try:
        return _call("GET", media_id, fields="permalink").get("permalink")
    except Exception as e:
        logger.warning("Could not fetch permalink for %s: %s", media_id, e)
        return None
