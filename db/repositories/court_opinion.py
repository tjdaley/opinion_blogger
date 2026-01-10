"""
db/repositories/court_opinion.py - Repository for CourtOpinion model using Supabase
"""
from db.models.court_opinion import CourtOpinionInDB
from db.repositories.base_repo import BaseRepository
from db.supabasemanager import DatabaseManager

class OpinionRepository(BaseRepository[CourtOpinionInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "court_opinions", CourtOpinionInDB)

    def get_by_slug(self, slug: str) -> CourtOpinionInDB:
        return self.manager.select_one(self.table_name, self.model_class, {"slug": slug})