"""
instagram_agent.py - Condense an approved blog post into the editorial text of
a five-slide Instagram carousel plus its caption.

Only the judgment calls live here (hook, plain-English issue/holding, takeaways,
caption body, hashtags). Everything factual that can be computed - court label,
case number, date, alt text, the caption's link-in-bio line and disclaimer - is
filled in deterministically by instagram/content.py.
"""
from typing import Annotated, List
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from agents.util import configure_model, get_prompt
from util.settings import settings


class InstagramDraft(BaseModel):
    topic_label: str = Field(max_length=24, description="2-3 word legal topic for the cover eyebrow, e.g. 'Emergency TROs'")
    hook: str = Field(max_length=90, description="Cover headline: the holding or rule as a plain-English statement")
    short_case_name: str = Field(max_length=40, description="Short case name, e.g. 'In re McDowell' or 'Tan v. Moore'")
    issue: str = Field(max_length=240, description="The question the court answered, in plain English")
    holding: str = Field(max_length=240, description="What the court decided, in plain English")
    takeaways: List[Annotated[str, Field(max_length=120)]] = Field(min_length=2, max_length=3)
    caption_body: str = Field(max_length=1200, description="Caption text WITHOUT link-in-bio, disclaimer, or hashtags")
    hashtags: List[Annotated[str, Field(pattern=r"^#[A-Za-z0-9]{2,30}$")]] = Field(min_length=3, max_length=5)


_instagram_agent: Agent[None, InstagramDraft] | None = None


def get_instagram_agent() -> Agent[None, InstagramDraft]:
    """Lazy singleton so the agent is built inside the running event loop."""
    global _instagram_agent
    if _instagram_agent is None:
        _instagram_agent = Agent(
            model=configure_model(
                mode="chat",
                no_safety=True,
                override_vendor=settings.instagram_agent_vendor or None,
                override_model=settings.instagram_agent_model or None,
            ),
            output_type=InstagramDraft,
            system_prompt=get_prompt("instagram_agent_system_prompt"),
            name="InstagramAgent",
            retries=2,
        )
    return _instagram_agent


user_prompt = get_prompt("instagram_agent_user_prompt_template", raise_error=True)
