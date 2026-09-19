"""
models/social_post.py - One post published to one social channel.
"""
import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class SocialPost(BaseModel):
    wp_post_id: int
    channel: str
    audience: str
    remote_id: str
    permalink: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    case_key: Optional[str] = None
    published_at: Optional[datetime.datetime] = None


class SocialPostInDB(SocialPost):
    id: int
    created_at: Optional[datetime.datetime]
    updated_at: Optional[datetime.datetime]
    model_config = ConfigDict(from_attributes=True)
