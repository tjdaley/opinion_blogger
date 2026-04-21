"""
db/repositories/legal_subject.py - Repository for LegalSubject model using Supabase
"""
from db.models.legal_subject import LegalSubjectInDB
from db_handler import DatabaseManager, BaseRepository

class LegalSubjectRepository(BaseRepository[LegalSubjectInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "legal_subjects", LegalSubjectInDB)
