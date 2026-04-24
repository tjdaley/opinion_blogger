"""
opinion_tracking.py - Scratch table used to track opinions from scraping through blog posting
"""
import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class QandA(BaseModel):
    question: str
    answer: str

class OpinionTracking(BaseModel):
    case_number: str
    status: str
    is_family_law: bool
    headline: str
    legal_issue: str
    holding: str
    opinion_link: str
    processed_at: datetime.datetime
    court: str
    opinion_date: datetime.date
    case_name: Optional[str] = None
    lower_court_name: Optional[str] = None
    seo_title: Optional[str] = None
    seo_focus_kw: Optional[str] = None
    meta_description: Optional[str] = None
    case_key: Optional[str] = None
    body: Optional[str] = None
    q_and_a: Optional[List[QandA]] = None
    opinion_text: Optional[str] = None
    has_substance: Optional[bool] = None

class OpinionTrackingInDB(OpinionTracking):
    id: int
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    model_config = ConfigDict(from_attributes=True)
