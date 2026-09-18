"""
publisher.py - Post approved blog posts to Instagram as carousels.

Selection is by WordPress tag, mirroring post_migrator.process_workflow:
  * published posts tagged instagram_ok_tag are candidates;
  * posts also tagged instagram_done_tag or instagram_failed_tag are skipped.

Per post: generate slide text -> render JPEGs -> host them -> create carousel
containers -> publish -> record the media id -> swap WP tags -> delete hosted
images. The media id is saved to court_opinions BEFORE the tags are swapped, so
a post whose re-tag fails is recognized next run and only re-tagged, never
published twice.
"""
import datetime
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import httpx
import requests
from markdownify import markdownify as md

from db.connection import court_opinion_repo
from db.models.court_opinion import CourtOpinionInDB
from instagram import graph, storage
from instagram.content import build_carousel
from instagram.renderer import render_slides
from post_migrator import find_case_key, get_posts_to_process, get_tag_id
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

TRANSIENT = (requests.ConnectionError, requests.Timeout, httpx.TransportError)


class PublishedButUnrecorded(Exception):
    """The carousel is live but the DB doesn't know. Never retry."""


@dataclass
class RunReport:
    published: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    deferred: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def eventful(self) -> bool:
        return bool(self.published or self.failed or self.notes)

    def summary(self) -> str:
        lines = [f"Instagram: {len(self.published)} published, {len(self.failed)} failed, "
                 f"{len(self.deferred)} deferred."]
        lines += [f"  posted: {p}" for p in self.published]
        lines += [f"  FAILED: {f}" for f in self.failed]
        lines += [f"  later: {d}" for d in self.deferred]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def _update_post(post: dict, **fields: List[int]) -> None:
    r = requests.post(f"{settings.wp_base_url}/posts/{post['id']}", json=fields,
                      auth=(settings.wp_username, settings.wp_app_password), timeout=30)
    r.raise_for_status()


def _set_tags(post: dict, tags: List[int]) -> None:
    _update_post(post, tags=tags)


def _category_id(slug: str) -> Optional[int]:
    r = requests.get(f"{settings.wp_base_url}/categories", params={"slug": slug},
                     auth=(settings.wp_username, settings.wp_app_password), timeout=30)
    found = r.json()
    return found[0]["id"] if found else None


def _mark_published(post: dict, ok_id: int, done_id: Optional[int], category_id: Optional[int]) -> None:
    """Swap ok -> done tag and add the Instagram category, which feeds the
    thomasjdaley.com/instagram-posts page the bio links to."""
    tags = [t for t in post["tags"] if t != ok_id] + ([done_id] if done_id and done_id not in post["tags"] else [])
    fields = {"tags": tags}
    if category_id and category_id not in post["categories"]:
        fields["categories"] = post["categories"] + [category_id]
    _update_post(post, **fields)


def _backfill_category(done_id: Optional[int], category_id: Optional[int]) -> int:
    """Give every already-posted post the Instagram category if it lacks it.
    Self-heals posts published before the category existed or tagged by hand."""
    if not (done_id and category_id):
        return 0
    fixed = 0
    for post in get_posts_to_process(settings.instagram_done_tag):
        if category_id not in post["categories"]:
            _update_post(post, categories=post["categories"] + [category_id])
            fixed += 1
    return fixed


def _case_key(post: dict) -> str:
    return find_case_key(md(post["content"]["raw"], strip=["script", "style"]))


def _title(post: dict) -> str:
    return post["title"]["rendered"]


def candidates(ok_id: int, done_id: Optional[int], failed_id: Optional[int]) -> List[dict]:
    posts = get_posts_to_process(settings.instagram_ok_tag)
    return [p for p in posts if not ({done_id, failed_id} & set(p["tags"]))]


async def _publish_one(post: dict, opinion: CourtOpinionInDB) -> str:
    """Publish one carousel; returns the permalink (or media id). Raises on failure."""
    content = await build_carousel(opinion)
    prefix = storage.new_prefix(opinion.case_key or str(opinion.id))
    with tempfile.TemporaryDirectory() as tmp:
        slides = await render_slides(content, Path(tmp))
        urls = storage.upload_slides(prefix, slides)

    children = [graph.create_carousel_item(u, alt) for u, alt in zip(urls, content.alt_texts)]
    for c in children:
        graph.wait_until_ready(c)
    carousel = graph.create_carousel(children, content.caption)
    graph.wait_until_ready(carousel)
    media_id = graph.publish(carousel)
    logger.info("Published %s to Instagram as media %s", opinion.case_name, media_id)

    # Record first: from here on, a failure must never lead to a second publish.
    try:
        court_opinion_repo.update(opinion.id, {
            "instagram_media_id": media_id,
            "instagram_content": content.model_dump(mode="json"),
            "instagram_published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
    except Exception as e:
        # Deliberately NOT transient: the caller must tag this post failed so
        # the next run can't publish it again.
        raise PublishedButUnrecorded(f"LIVE as media {media_id}, but saving that to the DB failed: {e}") from e
    link = graph.permalink(media_id)
    if link:
        court_opinion_repo.update(opinion.id, {"instagram_permalink": link})

    try:
        storage.delete_prefix(prefix)
    except Exception as e:
        logger.warning("Could not delete hosted slides %s (sweep will): %s", prefix, e)
    return link or f"media {media_id}"


async def publish_pending(dry_run: bool = False, limit: Optional[int] = None) -> RunReport:
    report = RunReport()
    limit = settings.instagram_max_posts_per_run if limit is None else limit

    ok_id = get_tag_id(settings.instagram_ok_tag)
    done_id = get_tag_id(settings.instagram_done_tag)
    failed_id = get_tag_id(settings.instagram_failed_tag)
    category_id = _category_id(settings.instagram_ok_category)
    if not category_id:
        report.notes.append(f"WordPress category '{settings.instagram_ok_category}' not found; "
                            "posts won't appear on the link-in-bio page.")
    if not ok_id:
        report.notes.append(f"WordPress tag '{settings.instagram_ok_tag}' not found.")
        return report

    posts = candidates(ok_id, done_id, failed_id)
    logger.info("%d WordPress posts approved for Instagram", len(posts))

    if dry_run:
        for p in posts:
            key = _case_key(p)
            op = court_opinion_repo.select_one(condition={"case_key": key}) if key else None
            state = ("no case key" if not key else "not migrated yet" if not op
                     else "already posted (will re-tag)" if op.instagram_media_id else "ready")
            report.deferred.append(f"{_title(p)} [{state}]")
        if len(posts) > limit:
            report.notes.append(f"Only {limit} will post per run.")
        return report

    err = graph.refresh_token_if_due()
    if err:
        report.notes.append(err)

    if posts:
        storage.ensure_bucket()
        used, total = graph.publishing_quota()
        limit = min(limit, max(0, total - used - 1))

    attempted = 0
    for post in posts:
        title = _title(post)
        key = _case_key(post)
        opinion = court_opinion_repo.select_one(condition={"case_key": key}) if key else None
        if not opinion:
            report.deferred.append(f"{title} (not migrated to court_opinions yet)")
            continue

        if opinion.instagram_media_id:
            # Published on an earlier run whose re-tag didn't stick.
            _mark_published(post, ok_id, done_id, category_id)
            report.notes.append(f"re-tagged already-posted {title}")
            continue

        if attempted >= limit:
            report.deferred.append(title)
            continue
        attempted += 1

        try:
            link = await _publish_one(post, opinion)
            _mark_published(post, ok_id, done_id, category_id)
            report.published.append(f"{title}\n    {link}")
        except TRANSIENT as e:
            logger.warning("Transient error on %s; will retry next run: %s", title, e)
            report.deferred.append(f"{title} (network: {e.__class__.__name__})")
        except Exception as e:
            logger.exception("Instagram publish failed for %s", title)
            report.failed.append(f"{title}: {e}")
            if failed_id:
                try:
                    _set_tags(post, post["tags"] + [failed_id])
                except Exception as tag_e:
                    logger.error("Could not add failed tag to %s: %s", title, tag_e)

    try:
        n = _backfill_category(done_id, category_id)
        if n:
            report.notes.append(f"added '{settings.instagram_ok_category}' category to {n} earlier post(s)")
    except Exception as e:
        logger.warning("Category backfill failed: %s", e)

    try:
        n = storage.sweep()
        if n:
            logger.info("Swept %d stale carousel folders from storage", n)
    except Exception as e:
        logger.warning("Storage sweep failed: %s", e)

    return report
