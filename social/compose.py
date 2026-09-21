"""
compose.py - Decide the audience for a (post, channel) pair and write the post.

Audience rules, in order:
  1. A WordPress override tag (audience_attorneys / audience_public) wins.
  2. Facebook always speaks to the public; case-law posts are translated.
  3. Threads mirrors the source: case-law posts go to attorneys; commentary is
     classified by a fast model (most commentary is for the public, but not all).
"""
from dataclasses import asdict, dataclass
from typing import Optional

from agents.social_post_agent import (
    AUDIENCE_RULES, KIND_RULES, Audience, FacebookDraft, ThreadsDraft,
    get_audience_agent, get_social_agent, user_prompt,
)
from social.card import CardContent
from social.source import SourcePost
from util.loggerfactory import LoggerFactory

logger = LoggerFactory.create_logger(__name__)

THREADS_LIMIT = 500


@dataclass
class Composed:
    channel: str
    audience: Audience
    audience_reason: str
    text: str   # final post text, exactly as it will be sent
    link: str   # attached as a clickable link card
    card: Optional[CardContent] = None       # Facebook: the image to render and post
    image_url: Optional[str] = None          # set once that image is hosted

    def to_json(self) -> dict:
        return asdict(self)


async def decide_audience(channel: str, src: SourcePost,
                          attorneys_tag: Optional[int], public_tag: Optional[int]) -> tuple[Audience, str]:
    if attorneys_tag and attorneys_tag in src.tag_ids:
        return "attorneys", "override tag"
    if public_tag and public_tag in src.tag_ids:
        return "public", "override tag"
    if channel == "facebook":
        return "public", "Facebook always speaks to the public"
    if src.kind == "opinion":
        return "attorneys", "case-law post"
    decision = (await get_audience_agent().run(
        user_prompt=f"TITLE: {src.title}\n\n{src.text[:6000]}")).output
    return decision.audience, f"classifier: {decision.reason}"


async def compose(channel: str, src: SourcePost,
                  attorneys_tag: Optional[int] = None, public_tag: Optional[int] = None,
                  news_category: Optional[int] = None) -> Composed:
    audience, why = await decide_audience(channel, src, attorneys_tag, public_tag)
    logger.info("%s / %s -> audience %s (%s)", channel, src.title, audience, why)

    prompt = user_prompt.format(
        channel=channel.title(),
        audience_label=audience.upper(),
        audience_rules=AUDIENCE_RULES[audience],
        kind_rules=KIND_RULES[(src.kind, audience)],
        title=src.title,
        text=src.text,
    )
    draft = (await get_social_agent(channel).run(user_prompt=prompt)).output

    card = None
    if isinstance(draft, ThreadsDraft):
        text = draft.text.strip()[:THREADS_LIMIT]
    elif isinstance(draft, FacebookDraft):
        text = draft.message.strip()
        if draft.hashtags:
            text += "\n\n" + " ".join(dict.fromkeys(draft.hashtags))
        # News posts carry artwork Thomas made himself; leave those as link
        # posts so Facebook keeps showing it. Everything else gets a card.
        if news_category and news_category in src.category_ids:
            logger.info("%s is in the news category; keeping its own artwork", src.title)
        else:
            card = CardContent(eyebrow=draft.card_eyebrow, headline=draft.card_headline, points=draft.card_points)
    else:
        raise TypeError(f"unexpected draft type {type(draft).__name__}")

    return Composed(channel=channel, audience=audience, audience_reason=why, text=text, link=src.link, card=card)
