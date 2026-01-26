"""
db/repositories/opinion_tracking.py - Repository for OpinionTracking model using Supabase
"""
from db.models.opinion_tracking import OpinionTrackingInDB
from db.repositories.base_repo import BaseRepository
from db.supabasemanager import DatabaseManager

class OpinionTrackingRepository(BaseRepository[OpinionTrackingInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "opinion_tracking", OpinionTrackingInDB)
