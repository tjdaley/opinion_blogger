"""
db/repositories/court_opinion.py - Repository for CourtOpinion model using Supabase
"""
import datetime
from typing import Union

from db.models.court_opinion import CourtOpinionInDB
from db_handler import DatabaseManager, BaseRepository, NOT_NULL

class OpinionRepository(BaseRepository[CourtOpinionInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "court_opinions", CourtOpinionInDB)

    def get_opinions_with_qa(self, page_size: int = 500) -> list[CourtOpinionInDB]:
        """Fetch all opinions that have non-null q_and_a, handling pagination internally."""
        all_results: list[CourtOpinionInDB] = []
        offset = 0
        while True:
            batch, _ = self.select_many(
                condition={"q_and_a": NOT_NULL},
                start=offset,
                end=offset + page_size - 1,
            )
            all_results.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return all_results

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

    def delete_by_case_key(self, case_key: str) -> None:
        case = self.manager.select_one(self.table_name, self.model_class, {"case_key": case_key})
        if not case:
            raise ValueError(f"No opinion found with case_key: {case_key}")
        self.manager.delete(self.table_name, case.id)
