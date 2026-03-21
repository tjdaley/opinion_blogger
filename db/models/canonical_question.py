"""
db/models/canonical_question.py - Models for canonical question clustering pipeline.

Database models for canonical_question_subjects, canonical_questions,
and opinion_question_mapping tables, plus pipeline-specific models
for the clustering workflow.
"""
import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# ── Database models ──────────────────────────────────────────────────────────

class CanonicalQuestionSubject(BaseModel):
    name: str
    slug: str
    display_order: int = 0
    description: Optional[str] = None
    proven_strategy_slugs: Optional[list[str]] = None
    hub_slugs: Optional[list[str]] = None


class CanonicalQuestionSubjectInDB(CanonicalQuestionSubject):
    id: int
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    model_config = ConfigDict(from_attributes=True)


class CanonicalQuestionRecord(BaseModel):
    question: str
    slug: str
    subject_id: Optional[int] = None
    needs_review: bool = True


class CanonicalQuestionRecordInDB(CanonicalQuestionRecord):
    id: int
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    model_config = ConfigDict(from_attributes=True)


class OpinionQuestionMapping(BaseModel):
    canonical_question_id: int
    court_opinion_id: int
    source_question_index: int
    source_question_text: str
    relevance_score: Optional[float] = None


class OpinionQuestionMappingInDB(OpinionQuestionMapping):
    id: int
    created_at: Optional[datetime.datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ── Pipeline models (used for type clarity in clustering workflow) ────────────

class ExtractedQuestion(BaseModel):
    """A single Q&A entry flattened from a court opinion's q_and_a array."""
    court_opinion_id: int
    question_index: int
    question_text: str
    answer_text: str
    case_name: str
    slug: str


class ClusterMember(BaseModel):
    """A court opinion Q&A entry within a cluster review entry."""
    court_opinion_id: int
    question_index: int
    question_text: str
    case_name: str
    slug: str


class ClusterReviewEntry(BaseModel):
    """A cluster of similar questions with its generated canonical question."""
    cluster_id: int
    canonical_question: str
    subject: str
    member_count: int
    needs_review: bool = True
    members: list[ClusterMember]
