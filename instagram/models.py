"""
models.py - The structured content one Instagram carousel is rendered from.

Slide text is deliberately short. Instagram is read at thumb-scroll speed on a
phone, so every field has a hard length budget; the renderer also shrinks type
to fit, but that is a safety net, not a license to write paragraphs.
"""
from pydantic import BaseModel, Field


class CarouselContent(BaseModel):
    # Slide 1 - cover
    court_label: str = Field(description="e.g. 'Texas Court of Appeals' or 'Supreme Court of Texas'")
    topic_label: str = Field(description="Two to four words naming the legal topic, e.g. 'Emergency TROs'")
    hook: str = Field(max_length=90, description="Cover headline: the rule or surprise in plain English")
    case_name: str = Field(description="Short case name, e.g. 'In re McDowell'")
    citation_line: str = Field(description="e.g. 'No. 08-26-00326-CV · Sept. 15, 2026'")

    # Slides 2-4
    issue: str = Field(max_length=260, description="The question the court had to answer")
    holding: str = Field(max_length=260, description="What the court decided")
    takeaways: list[str] = Field(min_length=2, max_length=3, description="Practical points, each under ~120 characters")

    # Post text (not rendered onto slides)
    caption: str = Field(max_length=2200)
    alt_texts: list[str] = Field(default_factory=list, description="One per slide; derived if empty")
