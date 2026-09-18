"""
content.py - Build a CarouselContent for one court_opinion row.

The LLM (agents/instagram_agent.py) writes only the editorial text. Court
labels, the case-number/date line, alt text, and the fixed parts of the caption
are computed here so they are always correct and consistent.
"""
import datetime
import re
from typing import Optional

from agents.instagram_agent import InstagramDraft, get_instagram_agent, user_prompt
from db.connection import opinion_tracking_repo
from db.models.court_opinion import CourtOpinionInDB
from instagram.models import CarouselContent
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

# Seat of each intermediate court of appeals, as practitioners refer to them.
COA_CITIES = {
    1: "Houston (1st)", 2: "Fort Worth", 3: "Austin", 4: "San Antonio", 5: "Dallas",
    6: "Texarkana", 7: "Amarillo", 8: "El Paso", 9: "Beaumont", 10: "Waco",
    11: "Eastland", 12: "Tyler", 13: "Corpus Christi–Edinburg", 14: "Houston (14th)",
    15: "Fifteenth Court",
}

# AP-style month abbreviations.
MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June",
          "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]

CAPTION_LINK_LINE = "Full case analysis: link in bio."
CAPTION_DISCLAIMER = "General information only, not legal advice."
SLIDE_DISCLAIMER = ("General information only, not legal advice. Reading this post does not "
                    "create an attorney–client relationship. Every case turns on its own facts.")
REQUIRED_HASHTAG = "#TexasFamilyLaw"


def court_label(court: str) -> str:
    return "Supreme Court of Texas" if court.upper() == "SCOTX" else "Texas Court of Appeals"


def court_long_name(court: str) -> str:
    """Name for the prompt, e.g. 'Dallas Court of Appeals'."""
    city = _coa_city(court)
    return f"{city} Court of Appeals" if city else court_label(court)


def _coa_city(court: str) -> Optional[str]:
    m = re.fullmatch(r"COA0?(\d{1,2})", court.upper())
    return COA_CITIES.get(int(m.group(1))) if m else None


def ap_date(d: datetime.date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def _case_number(opinion: CourtOpinionInDB) -> Optional[str]:
    """Prefer the tracked case number; fall back to parsing the citation."""
    if opinion.case_key:
        try:
            tracked = opinion_tracking_repo.select_one(condition={"case_key": opinion.case_key})
            if tracked and tracked.case_number:
                return tracked.case_number
        except Exception as e:
            logger.warning("Case-number lookup failed for %s: %s", opinion.case_key, e)
    m = re.search(r"Nos?\.\s*([0-9A-Z][0-9A-Z\-]+)", opinion.citation or "")
    return m.group(1) if m else None


def citation_line(opinion: CourtOpinionInDB) -> str:
    parts = []
    number = _case_number(opinion)
    if number:
        parts.append(f"No. {number}")
    city = _coa_city(opinion.court)
    if city:
        parts.append(city)
    parts.append(ap_date(opinion.date))
    return " · ".join(parts)


def assemble_caption(draft: InstagramDraft) -> str:
    tags = list(dict.fromkeys([REQUIRED_HASHTAG] + draft.hashtags))  # dedupe, keep order
    caption = "\n\n".join([draft.caption_body.strip(), CAPTION_LINK_LINE, CAPTION_DISCLAIMER, " ".join(tags)])
    return caption[:2200]


def alt_texts(c: CarouselContent) -> list[str]:
    """One per slide, taken from the slide's own text so it can never drift."""
    points = " ".join(f"{i}. {t}" for i, t in enumerate(c.takeaways, 1))
    return [
        f"Cover slide. {c.court_label}, {c.topic_label}. {c.hook} {c.case_name}, {c.citation_line}. "
        f"Thomas J. Daley, {settings.instagram_firm_name}.",
        f"Slide 2 of 5. The question: {c.issue}",
        f"Slide 3 of 5. What the court held: {c.holding}",
        f"Slide 4 of 5. Why it matters. Practice pointers: {points}",
        f"Slide 5 of 5. Read the full case analysis, link in bio, thomasjdaley.com. {SLIDE_DISCLAIMER}",
    ]


async def build_carousel(opinion: CourtOpinionInDB) -> CarouselContent:
    """Run the agent on one opinion and return render-ready content."""
    if not opinion.blog_post:
        raise ValueError(f"court_opinion {opinion.id} has no blog_post to draw from")

    prompt = user_prompt.format(
        case_name=opinion.case_name,
        court_name=court_long_name(opinion.court),
        opinion_date=ap_date(opinion.date),
        category=opinion.category,
        litigation_takeaway=opinion.litigation_takeaway,
        blog_post=opinion.blog_post,
    )
    logger.info("Generating Instagram draft for %s", opinion.case_name)
    draft: InstagramDraft = (await get_instagram_agent().run(user_prompt=prompt)).output

    content = CarouselContent(
        court_label=court_label(opinion.court),
        topic_label=draft.topic_label,
        hook=draft.hook if draft.hook.rstrip()[-1:] in ".!?" else draft.hook.rstrip() + ".",
        case_name=draft.short_case_name,
        citation_line=citation_line(opinion),
        issue=draft.issue,
        holding=draft.holding,
        takeaways=draft.takeaways,
        caption=assemble_caption(draft),
    )
    content.alt_texts = alt_texts(content)
    return content
