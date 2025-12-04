from pydantic import BaseModel, Field
from typing import List, Dict, Any
from datetime import datetime


class MessageData(BaseModel):
    """Data content for a message"""
    content: str


class Message(BaseModel):
    """Embedded Message model"""
    type: str = Field(..., description="Message type, e.g., 'text'")
    data: MessageData
    timestamp: datetime


class SessionBase(BaseModel):
    """Base Session model"""
    messages: List[Message] = Field(default_factory=list)


class Session(SessionBase):
    """Session model for API responses"""
    id: str
    
    class Config:
        from_attributes = True


class SessionInDB(SessionBase):
    """Session model as stored in database"""
    id: str = Field(alias="_id")
    
    class Config:
        from_attributes = True
        populate_by_name = True
