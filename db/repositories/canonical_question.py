"""
db/repositories/canonical_question.py - Repository for CanonicalQuestion model
"""
from typing import Any

from db.models.canonical_question import CanonicalQuestionRecordInDB
from db.repositories.base_repo import BaseRepository
from db.databasemanager import DatabaseManager


class CanonicalQuestionRepository(BaseRepository[CanonicalQuestionRecordInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "canonical_questions", CanonicalQuestionRecordInDB)

    def upsert_by_slug(self, data: dict[str, Any]) -> CanonicalQuestionRecordInDB:
        """Insert or update a canonical question, matching on slug."""
        return self.upsert(data, on_conflict="slug")
