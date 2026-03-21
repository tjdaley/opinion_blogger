"""
db/repositories/opinion_tracking.py - Repository for OpinionTracking model using Supabase
"""
from db.models.opinion_tracking import OpinionTrackingInDB
from db.repositories.base_repo import BaseRepository
from db.supabasemanager import DatabaseManager

class OpinionTrackingRepository(BaseRepository[OpinionTrackingInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "opinion_tracking", OpinionTrackingInDB)

    def delete_by_case_key(self, case_key: str) -> None:
        tracking = self.manager.select_one(self.table_name, self.model_class, {"case_key": case_key})
        if not tracking:
            raise ValueError(f"No opinion tracking found with case_key: {case_key}")
        self.manager.delete(self.table_name, tracking.id)
