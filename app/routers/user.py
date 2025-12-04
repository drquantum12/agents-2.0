from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

from app.utility.security import get_current_user
from app.controllers.user_controller import UserController
from app.models.user import UserUpdate

router = APIRouter(prefix="/user", tags=["User Profile"])

# Initialize controller
user_controller = UserController()

# Response Models
class UserProfileResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    photo_url: Optional[str] = None
    grade: Optional[str] = None
    board: Optional[str] = None
    personalized_response: bool = False
    account_type: Optional[str] = "email"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# Endpoints

@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile"""
    return await user_controller.get_user_profile(current_user["_id"])

@router.patch("/me", response_model=UserProfileResponse)
async def update_me(update_data: UserUpdate, current_user: dict = Depends(get_current_user)):
    """Update current user profile"""
    return await user_controller.update_user_profile(current_user["_id"], update_data)

@router.delete("/me")
async def delete_me(current_user: dict = Depends(get_current_user)):
    """Delete current user account"""
    return await user_controller.delete_user(current_user["_id"])
