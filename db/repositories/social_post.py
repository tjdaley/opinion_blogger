"""
db/repositories/social_post.py - Repository for SocialPost model using Supabase
"""
from db.models.social_post import SocialPostInDB
from db_handler import DatabaseManager, BaseRepository

class SocialPostRepository(BaseRepository[SocialPostInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "social_posts", SocialPostInDB)
