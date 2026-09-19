"""
source.py - Normalize a WordPress post into what the social agents need.

Works for any post. Case-law posts (those carrying a ~~case_key~~ token) are
marked kind="opinion" and pick up their court_opinions row when one exists;
everything else is kind="commentary".
"""
import html
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

from markdownify import markdownify as md

from db.connection import court_opinion_repo
from db.models.court_opinion import CourtOpinionInDB
from post_migrator import find_case_key

Kind = Literal["opinion", "commentary"]

_GATE_BLOCK = re.compile(r"<!-- GATE-REVIEW-NOTES START -->.*?<!-- GATE-REVIEW-NOTES END -->", re.S)
_CASE_KEY_TOKEN = re.compile(r"~~[0-9a-fA-F-]{36}~~")


@dataclass
class SourcePost:
    wp_id: int
    title: str
    link: str
    text: str            # markdown body, cleaned of pipeline tokens
    kind: Kind
    tag_ids: list[int]
    category_ids: list[int]
    case_key: Optional[str] = None
    opinion: Optional[CourtOpinionInDB] = None


def from_wp(post: dict[str, Any]) -> SourcePost:
    raw = post["content"]["raw"]
    body = md(_GATE_BLOCK.sub("", raw), strip=["script", "style"], heading_style="ATX")
    case_key = find_case_key(body) or None
    body = _CASE_KEY_TOKEN.sub("", body).strip()

    opinion = None
    if case_key:
        try:
            opinion = court_opinion_repo.select_one(condition={"case_key": case_key})
        except Exception:
            opinion = None

    return SourcePost(
        wp_id=post["id"],
        title=html.unescape(post["title"]["rendered"]),
        link=post["link"],
        text=body,
        kind="opinion" if case_key else "commentary",
        tag_ids=list(post["tags"]),
        category_ids=list(post["categories"]),
        case_key=case_key,
        opinion=opinion,
    )
