"""
threads.py - Publish a text post with a link card to Threads (graph.threads.net).

Flow: create a TEXT container with link_attachment -> wait until FINISHED ->
threads_publish -> fetch permalink. Long-lived Threads tokens last 60 days and
are refreshed weekly here, persisted to settings.threads_token_file (same
scheme as instagram/graph.py).
"""
import datetime
import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Tuple

import requests

from social.channels.base import PlatformAPIError, check
from social.compose import Composed
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

REFRESH_EVERY = datetime.timedelta(days=7)


class ThreadsChannel:
    name = "threads"

    # ------------------------------------------------------------ token ----
    def _fingerprint(self) -> str:
        return hashlib.sha256(settings.threads_access_token.encode()).hexdigest()[:16]

    def _state(self) -> Optional[dict]:
        p = Path(settings.threads_token_file)
        if not p.exists():
            return None
        state = json.loads(p.read_text(encoding="utf-8"))
        return state if state.get("env_fingerprint") == self._fingerprint() else None

    def _save(self, token: str, when: datetime.datetime, expires_in: Optional[int]) -> None:
        Path(settings.threads_token_file).write_text(json.dumps({
            "access_token": token,
            "env_fingerprint": self._fingerprint(),
            "refreshed_at": when.isoformat(),
            "expires_at": (when + datetime.timedelta(seconds=expires_in)).isoformat() if expires_in else None,
        }, indent=2), encoding="utf-8")

    def _token(self) -> str:
        state = self._state()
        return state["access_token"] if state else settings.threads_access_token

    def missing_config(self) -> Optional[str]:
        missing = [n for n in ("threads_access_token", "threads_user_id") if not getattr(settings, n)]
        return f"Threads not configured (missing {', '.join(missing).upper()})" if missing else None

    def refresh_if_due(self) -> Optional[str]:
        now = datetime.datetime.now(datetime.timezone.utc)
        state = self._state()
        if state is None:
            self._save(settings.threads_access_token, now, None)  # too new to refresh; start the clock
            return None
        if now - datetime.datetime.fromisoformat(state["refreshed_at"]) < REFRESH_EVERY:
            return None
        try:
            r = requests.get(f"{settings.threads_graph_url.rsplit('/', 1)[0]}/refresh_access_token",
                             params={"grant_type": "th_refresh_token", "access_token": state["access_token"]},
                             timeout=30)
            body = check(r, "Threads token refresh")
            self._save(body["access_token"], now, body.get("expires_in"))
            return None
        except Exception as e:
            return f"Threads token refresh failed: {e}"

    # -------------------------------------------------------------- API ----
    def _call(self, method: str, path: str, **params) -> dict:
        r = requests.request(method, f"{settings.threads_graph_url}/{path}",
                             params={**params, "access_token": self._token()}, timeout=60)
        return check(r, f"Threads {method} {path}")

    def publish(self, post: Composed) -> Tuple[str, Optional[str]]:
        uid = settings.threads_user_id
        container = self._call("POST", f"{uid}/threads",
                               media_type="TEXT", text=post.text, link_attachment=post.link)["id"]
        deadline = time.monotonic() + 300
        while True:
            status = self._call("GET", container, fields="status,error_message")
            if status.get("status") in ("FINISHED", "PUBLISHED"):
                break
            if status.get("status") in ("ERROR", "EXPIRED"):
                raise PlatformAPIError(f"Threads container {container}: {status}")
            if time.monotonic() > deadline:
                raise PlatformAPIError(f"Threads container {container} not ready after 300s")
            time.sleep(5)
        media_id = self._call("POST", f"{uid}/threads_publish", creation_id=container)["id"]
        try:
            link = self._call("GET", media_id, fields="permalink").get("permalink")
        except Exception as e:
            logger.warning("No Threads permalink for %s: %s", media_id, e)
            link = None
        return media_id, link
