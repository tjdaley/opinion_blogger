"""
social_post_agent.py - Write Threads and Facebook posts from a blog post, and
classify a commentary post's primary audience.

The system prompt is the shared rules (social_common_rules.txt) plus the
channel's format and voice (<channel>_agent_system_prompt.txt). Audience and
source-type guidance go in the user prompt, since the same channel serves both.
"""
from typing import Annotated, List, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from agents.util import configure_model, get_prompt
from util.settings import settings

Audience = Literal["attorneys", "public"]


class ThreadsDraft(BaseModel):
    text: str = Field(max_length=480, description="The whole Threads post. No URLs, no hashtags.")


class FacebookDraft(BaseModel):
    message: str = Field(min_length=200, max_length=1500, description="The Facebook post body. No URLs.")
    hashtags: List[Annotated[str, Field(pattern=r"^#[A-Za-z0-9]{2,30}$")]] = Field(default_factory=list, max_length=3)
    # The image card rendered alongside the post (social/cards/facebook_card.html.j2)
    card_eyebrow: str = Field(max_length=30, description="2-3 word topic label for the top of the image")
    card_headline: str = Field(max_length=80, description="The image headline: a question a client would ask")
    card_points: List[Annotated[str, Field(max_length=75)]] = Field(min_length=2, max_length=3)


class AudienceDecision(BaseModel):
    audience: Audience
    reason: str


DRAFT_TYPES = {"threads": ThreadsDraft, "facebook": FacebookDraft}

AUDIENCE_RULES = {
    "attorneys": (
        "Texas family-law attorneys. Peer to peer: terms of art (TRO, mandamus, "
        "SAPCR, UCCJEA) are expected and need no definition. Cite rules and "
        "statutes by number when the post does. Lead with the holding and why it "
        "matters in practice."
    ),
    "public": (
        "Members of the public: parents, spouses, people in or near a family case. "
        "Plain English. Explain or avoid legal jargon; never Latin. Lead with people "
        "and consequences, not doctrine."
    ),
}

KIND_RULES = {
    ("opinion", "attorneys"): "An analysis of a Texas appellate opinion, written for lawyers.",
    ("opinion", "public"): (
        "An analysis of a Texas appellate opinion, written for lawyers. Translate it "
        "for the public: what happened to this family, what the court decided, and "
        "what a parent or spouse in a similar spot should understand. Refer to the "
        "parties by role (a mother, a father, the grandparents), NOT by name, even "
        "though the opinion is public record. You may give the short case name once, "
        "near the end, for anyone who wants to look it up."
    ),
    ("commentary", "attorneys"): "Thomas's own commentary, written for lawyers. Keep his point of view.",
    ("commentary", "public"): (
        "Thomas's own commentary or advocacy. Keep his voice, point of view, and "
        "conviction. Refer to people the way the post does."
    ),
}


_agents: dict[str, Agent] = {}


def get_social_agent(channel: str) -> Agent:
    """Lazy per-channel singleton, built inside the running event loop."""
    if channel not in _agents:
        _agents[channel] = Agent(
            model=configure_model(
                mode="chat",
                no_safety=True,
                override_vendor=settings.social_agent_vendor or None,
                override_model=settings.social_agent_model or None,
            ),
            output_type=DRAFT_TYPES[channel],
            system_prompt=get_prompt("social_common_rules") + "\n\n" + get_prompt(f"{channel}_agent_system_prompt"),
            name=f"{channel.title()}Agent",
            retries=2,
        )
    return _agents[channel]


_audience_agent: Agent[None, AudienceDecision] | None = None


def get_audience_agent() -> Agent[None, AudienceDecision]:
    global _audience_agent
    if _audience_agent is None:
        _audience_agent = Agent(
            model=configure_model(mode="chat", no_safety=True),
            output_type=AudienceDecision,
            system_prompt=get_prompt("audience_agent_system_prompt"),
            name="AudienceAgent",
        )
    return _audience_agent


user_prompt = get_prompt("social_post_agent_user_prompt_template", raise_error=True)
