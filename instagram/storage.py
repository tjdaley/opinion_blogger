"""
storage.py - Temporary public hosting for carousel JPEGs (Supabase Storage).

Instagram fetches each image from a public URL when its media container is
created and serves the post from its own CDN afterwards, so these files are
only needed until publishing succeeds. Each carousel lives under one folder,
"<YYYYMMDD-HHMMSS>_<case_key>/", which is deleted after a successful publish;
sweep() removes anything left behind by a crash.
"""
import datetime
from pathlib import Path
from typing import List

from supabase import Client, create_client

from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

STAMP_FORMAT = "%Y%m%d-%H%M%S"

_client: Client | None = None


def _storage():
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client.storage


def ensure_bucket() -> None:
    """Create the public, JPEG-only bucket on first use. No-op once it exists."""
    try:
        _storage().get_bucket(settings.instagram_bucket)
    except Exception:
        logger.info("Creating Supabase Storage bucket %s", settings.instagram_bucket)
        _storage().create_bucket(settings.instagram_bucket, options={
            "public": True,
            "allowed_mime_types": ["image/jpeg"],
            "file_size_limit": 8 * 1024 * 1024,
        })


def new_prefix(case_key: str) -> str:
    return f"{datetime.datetime.now(datetime.timezone.utc):{STAMP_FORMAT}}_{case_key}"


def upload_slides(prefix: str, paths: List[Path]) -> List[str]:
    """Upload slides in order and return their public URLs."""
    bucket = _storage().from_(settings.instagram_bucket)
    urls: List[str] = []
    for p in paths:
        key = f"{prefix}/{p.name}"
        bucket.upload(key, p.read_bytes(), {"content-type": "image/jpeg", "upsert": "true"})
        urls.append(bucket.get_public_url(key).rstrip("?"))
    logger.info("Uploaded %d slides to %s/%s", len(urls), settings.instagram_bucket, prefix)
    return urls


def delete_prefix(prefix: str) -> None:
    bucket = _storage().from_(settings.instagram_bucket)
    files = bucket.list(prefix)
    if files:
        bucket.remove([f"{prefix}/{f['name']}" for f in files])
    logger.info("Deleted %d hosted slides under %s", len(files), prefix)


def sweep(max_age: datetime.timedelta = datetime.timedelta(days=2)) -> int:
    """Delete carousel folders older than max_age. Returns folders removed."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - max_age
    removed = 0
    for entry in _storage().from_(settings.instagram_bucket).list("", {"limit": 1000}):
        stamp = entry["name"].split("_", 1)[0]
        try:
            created = datetime.datetime.strptime(stamp, STAMP_FORMAT).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue  # not one of ours
        if created < cutoff:
            delete_prefix(entry["name"])
            removed += 1
    return removed
