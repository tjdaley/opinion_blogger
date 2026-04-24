import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from db.models.opinion_tracking import QandA

class CourtOpinion(BaseModel):
    case_name: str
    citation: str
    opinion_link: str
    court: str
    lower_court_name: Optional[str] = None
    date: datetime.date
    summary: str
    litigation_takeaway: str
    slug: str
    category: str
    needs_review: bool = False
    blog_post: Optional[str] = None
    case_key: Optional[str] = None
    google_index_requested_at: Optional[datetime.datetime] = None
    case_name_corrected: bool = False
    q_and_a: Optional[list[QandA]] = None
    tags_top_k: Optional[list[str]] = None
    tags_discarded: Optional[list[str]] = None
    tag_rationale: Optional[str] = None
    has_substance: Optional[bool] = None


class CourtOpinionInDB(CourtOpinion):
    id: int
    created_at: Optional[datetime.datetime]
    updated_at: Optional[datetime.datetime]
    model_config = ConfigDict(from_attributes=True)