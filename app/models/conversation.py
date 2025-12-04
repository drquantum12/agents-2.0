from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ConversationBase(BaseModel):
    """Base Conversation model with common attributes"""
    user_id: str = Field(..., description="Reference to User ID")
    topic: str = Field(..., min_length=1, max_length=200)


class ConversationCreate(BaseModel):
    """Model for creating a new conversation"""
    topic: str = Field(..., min_length=1, max_length=200)


class ConversationUpdate(BaseModel):
    """Model for updating conversation information"""
    topic: Optional[str] = Field(None, min_length=1, max_length=200)


class Conversation(ConversationBase):
    """Conversation model for API responses"""
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ConversationInDB(ConversationBase):
    """Conversation model as stored in database"""
    id: str = Field(alias="_id")
    created_at: datetime
    
    class Config:
        from_attributes = True
        populate_by_name = True
