"""
models/legal_subject.py - Data models for legal subjects
"""
import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class LegalSubject(BaseModel):
    label: str

class LegalSubjectInDB(LegalSubject):
    id: str
    created_at: Optional[datetime.datetime]
    updated_at: Optional[datetime.datetime]
    model_config = ConfigDict(from_attributes=True)
