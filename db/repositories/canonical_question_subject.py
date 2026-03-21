"""
db/repositories/canonical_question_subject.py - Repository for CanonicalQuestionSubject model
"""
import re
from typing import Optional

from db.models.canonical_question import CanonicalQuestionSubjectInDB
from db.repositories.base_repo import BaseRepository
from db.databasemanager import DatabaseManager


class CanonicalQuestionSubjectRepository(BaseRepository[CanonicalQuestionSubjectInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "canonical_question_subjects", CanonicalQuestionSubjectInDB)

    def get_or_create_by_name(self, name: str) -> CanonicalQuestionSubjectInDB:
        """Look up a subject by name, creating it if it doesn't exist."""
        existing = self.select_one({"name": name})
        if existing:
            return existing

        slug = re.sub(r'[^a-z0-9\s-]', '', name.lower().strip())
        slug = re.sub(r'[\s-]+', '-', slug)[:120]
        return self.insert({"name": name, "slug": slug})
