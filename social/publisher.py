"""
publisher.py - Post tagged WordPress posts to Threads or Facebook.

Same shape and guarantees as instagram/publisher.py, for any post (case-law or
commentary), with the record kept in social_posts:
  * candidates: published posts tagged ok_for_<channel>, minus those tagged
    published_to_<channel> or <channel>_failed;
  * the social_posts row is written BEFORE the WP tags are swapped, so a post
    that published but failed to re-tag is only re-tagged next run;
  * platform refusals get <channel>_failed; network errors are retried.
"""
import datetime
from typing import Optional

import httpx
import requests

from db.connection import social_post_repo
from instagram.publisher import RunReport
from post_migrator import get_posts_to_process, get_tag_id
from social.channels.base import Channel
from social.channels.facebook import FacebookChannel
from social.channels.threads import ThreadsChannel
from social.compose import compose
from social.source import from_wp
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

CHANNELS: dict[str, Channel] = {"threads": ThreadsChannel(), "facebook": FacebookChannel()}
TRANSIENT = (requests.ConnectionError, requests.Timeout, httpx.TransportError)


class PublishedButUnrecorded(Exception):
    """Live on the platform, but the DB doesn't know. Never retry."""


def tag_names(channel: str) -> tuple[str, str, str]:
    return f"ok_for_{channel}", f"published_to_{channel}", f"{channel}_failed"


def _update_post(wp_id: int, **fields) -> None:
    r = requests.post(f"{settings.wp_base_url}/posts/{wp_id}", json=fields,
                      auth=(settings.wp_username, settings.wp_app_password), timeout=30)
    r.raise_for_status()


def _swap_tags(post: dict, ok_id: int, done_id: Optional[int]) -> None:
    tags = [t for t in post["tags"] if t != ok_id]
    if done_id and done_id not in tags:
        tags.append(done_id)
    _update_post(post["id"], tags=tags)


async def publish_pending(channel_name: str, dry_run: bool = False, limit: Optional[int] = None) -> RunReport:
    channel = CHANNELS[channel_name]
    report = RunReport(label=channel_name.title())
    limit = settings.social_max_posts_per_run if limit is None else limit

    ok_name, done_name, failed_name = tag_names(channel_name)
    ok_id, done_id, failed_id = get_tag_id(ok_name), get_tag_id(done_name), get_tag_id(failed_name)
    missing_tags = [n for n, i in ((ok_name, ok_id), (done_name, done_id), (failed_name, failed_id)) if not i]
    if missing_tags:
        report.notes.append(f"Create these WordPress tags: {', '.join(missing_tags)}")
        if not ok_id:
            return report
    attorneys_tag = get_tag_id(settings.social_audience_attorneys_tag)
    public_tag = get_tag_id(settings.social_audience_public_tag)

    posts = [p for p in get_posts_to_process(ok_name) if not ({done_id, failed_id} & set(p["tags"]))]
    logger.info("%d WordPress posts approved for %s", len(posts), channel_name)

    if dry_run:
        for p in posts:
            src = from_wp(p)
            already = social_post_repo.select_one(condition={"wp_post_id": src.wp_id, "channel": channel_name})
            report.deferred.append(f"{src.title} [{src.kind}{', already posted (will re-tag)' if already else ''}]")
        if (msg := channel.missing_config()):
            report.notes.append(msg)
        return report

    if (msg := channel.missing_config()):
        report.notes.append(msg)
        return report
    if (err := channel.refresh_if_due()):
        report.notes.append(err)

    attempted = 0
    for post in posts:
        src = from_wp(post)
        if social_post_repo.select_one(condition={"wp_post_id": src.wp_id, "channel": channel_name}):
            _swap_tags(post, ok_id, done_id)  # published earlier; re-tag didn't stick
            report.notes.append(f"re-tagged already-posted {src.title}")
            continue
        if attempted >= limit:
            report.deferred.append(src.title)
            continue
        attempted += 1

        try:
            composed = await compose(channel_name, src, attorneys_tag, public_tag)
            remote_id, permalink = channel.publish(composed)
            logger.info("Published %s to %s as %s", src.title, channel_name, remote_id)
            try:
                social_post_repo.insert({
                    "wp_post_id": src.wp_id, "channel": channel_name, "audience": composed.audience,
                    "remote_id": remote_id, "permalink": permalink, "content": composed.to_json(),
                    "case_key": src.case_key,
                    "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
            except Exception as e:
                raise PublishedButUnrecorded(f"LIVE as {remote_id}, but saving that to the DB failed: {e}") from e
            _swap_tags(post, ok_id, done_id)
            report.published.append(f"{src.title} ({composed.audience})\n    {permalink or remote_id}")
        except TRANSIENT as e:
            logger.warning("Transient error on %s; will retry next run: %s", src.title, e)
            report.deferred.append(f"{src.title} (network: {e.__class__.__name__})")
        except Exception as e:
            logger.exception("%s publish failed for %s", channel_name, src.title)
            report.failed.append(f"{src.title}: {e}")
            if failed_id:
                try:
                    _update_post(post["id"], tags=post["tags"] + [failed_id])
                except Exception as tag_e:
                    logger.error("Could not add failed tag to %s: %s", src.title, tag_e)

    return report
