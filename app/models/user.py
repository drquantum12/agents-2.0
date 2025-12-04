from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """Base User model with common attributes"""
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    grade: Optional[str] = Field(None, max_length=20)
    board: Optional[str] = Field(None, max_length=50)
    personalized_response: Optional[bool] = Field(default=False)


class UserCreate(UserBase):
    """Model for creating a new user"""
    password: Optional[str] = Field(None, min_length=6)


class UserUpdate(BaseModel):
    """Model for updating user information"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    grade: Optional[str] = Field(None, max_length=20)
    board: Optional[str] = Field(None, max_length=50)
    personalized_response: Optional[bool] = None
    photo_url: Optional[str] = None


class User(UserBase):
    """User model for API responses"""
    id: str
    photo_url: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserInDB(UserBase):
    """User model as stored in database"""
    id: str = Field(alias="_id")
    password: Optional[str] = None
    photo_url: Optional[str] = None
    account_type: str = Field(default="email")  # "email" or "google"
    firebase_uid: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        populate_by_name = True
