from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime


class NotificationInDB(BaseModel):
    """Notification model as stored in database"""
    id: str = Field(alias="_id")
    user_id: str
    message: str
    type: Literal["info", "warn", "err"]
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
