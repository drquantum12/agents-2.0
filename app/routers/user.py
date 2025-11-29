from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timezone
from app.utility.security import get_current_user
from app.db_utility.mongo_db import mongo_db

router = APIRouter(prefix="/user", tags=["User Profile"])

class UserProfileResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    photo_url: Optional[str] = None
    account_type: Optional[str] = "email"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None

@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["_id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "photo_url": current_user.get("photo_url"),
        "account_type": current_user.get("account_type", "email"),
        "created_at": current_user.get("created_at"),
        "updated_at": current_user.get("updated_at")
    }

@router.patch("/me", response_model=UserProfileResponse)
async def update_me(update_data: UserUpdate, current_user: dict = Depends(get_current_user)):
    users_collection = mongo_db["users"]
    
    update_fields = {k: v for k, v in update_data.model_dump(exclude_unset=True).items()}
    
    if not update_fields:
        return {
            "id": current_user["_id"],
            "name": current_user["name"],
            "email": current_user["email"],
            "photo_url": current_user.get("photo_url"),
            "account_type": current_user.get("account_type", "email"),
            "created_at": current_user.get("created_at"),
            "updated_at": current_user.get("updated_at")
        }
        
    update_fields["updated_at"] = datetime.now(timezone.utc)
    
    users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields}
    )
    
    # Fetch updated user
    updated_user = users_collection.find_one({"_id": current_user["_id"]})
    
    return {
        "id": updated_user["_id"],
        "name": updated_user["name"],
        "email": updated_user["email"],
        "photo_url": updated_user.get("photo_url"),
        "account_type": updated_user.get("account_type", "email"),
        "created_at": updated_user.get("created_at"),
        "updated_at": updated_user.get("updated_at")
    }
