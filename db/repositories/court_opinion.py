"""
db/repositories/court_opinion.py - Repository for CourtOpinion model using Supabase
"""
import datetime
from typing import Union

from db.models.court_opinion import CourtOpinionInDB
from db.repositories.base_repo import BaseRepository
from db.supabasemanager import DatabaseManager

class OpinionRepository(BaseRepository[CourtOpinionInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "court_opinions", CourtOpinionInDB)

    def get_by_slug(self, slug: str) -> Union[CourtOpinionInDB, None]:
        return self.manager.select_one(self.table_name, self.model_class, {"slug": slug})
    
    def update_google_index_requested_at(self, slug: str) -> None:
        if not slug:
            raise ValueError("Slug must be provided to update google_index_requested_at")
        
        opinion = self.get_by_slug(slug)
        if not opinion:
            raise ValueError(f"No opinion found with slug: {slug}")
        
        timestamp = datetime.datetime.now(datetime.timezone.utc)  # Use timezone-aware timestamp
        opinion.google_index_requested_at = timestamp
        self.manager.update(
            self.table_name,
            opinion.id, 
            opinion.model_dump(mode="json"),
            self.model_class
        )
