"""
facebook.py - Publish a text post with a link card to Thomas's Facebook Page.

Uses a Page access token (pages_manage_posts). A Page token obtained from a
long-lived user token does not expire, so there is nothing to refresh.
"""
from typing import Optional, Tuple

import requests

from social.channels.base import check
from social.compose import Composed
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)


class FacebookChannel:
    name = "facebook"

    def missing_config(self) -> Optional[str]:
        missing = [n for n in ("facebook_page_id", "facebook_page_access_token") if not getattr(settings, n)]
        return f"Facebook not configured (missing {', '.join(missing).upper()})" if missing else None

    def refresh_if_due(self) -> Optional[str]:
        return None

    def publish(self, post: Composed) -> Tuple[str, Optional[str]]:
        base = settings.facebook_graph_url
        token = settings.facebook_page_access_token
        r = requests.post(f"{base}/{settings.facebook_page_id}/feed",
                          data={"message": post.text, "link": post.link, "access_token": token}, timeout=60)
        post_id = check(r, "Facebook POST feed")["id"]
        try:
            r = requests.get(f"{base}/{post_id}", params={"fields": "permalink_url", "access_token": token}, timeout=30)
            link = check(r, "Facebook GET permalink").get("permalink_url")
        except Exception as e:
            logger.warning("No Facebook permalink for %s: %s", post_id, e)
            link = None
        return post_id, link
