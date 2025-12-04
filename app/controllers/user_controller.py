from fastapi import HTTPException, status
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.models.user import UserUpdate
from app.db_utility.mongo_db import mongo_db


class UserController:
    """Controller for handling user profile operations"""
    
    def __init__(self):
        self.users_collection = mongo_db["users"]
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get user profile by user ID
        
        Args:
            user_id: User ID
            
        Returns:
            User profile data
            
        Raises:
            HTTPException: If user not found
        """
        user = self.users_collection.find_one({"_id": user_id})
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "id": user["_id"],
            "name": user["name"],
            "email": user["email"],
            "photo_url": user.get("photo_url"),
            "grade": user.get("grade"),
            "board": user.get("board"),
            "personalized_response": user.get("personalized_response", False),
            "account_type": user.get("account_type", "email"),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at")
        }
    
    async def update_user_profile(
        self, 
        user_id: str, 
        update_data: UserUpdate
    ) -> Dict[str, Any]:
        """
        Update user profile
        
        Args:
            user_id: User ID
            update_data: Fields to update
            
        Returns:
            Updated user profile data
            
        Raises:
            HTTPException: If user not found
        """
        user = self.users_collection.find_one({"_id": user_id})
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Extract only provided fields
        update_fields = {
            k: v for k, v in update_data.model_dump(exclude_unset=True).items()
        }
        
        if not update_fields:
            # No updates, return current user
            return await self.get_user_profile(user_id)
        
        # Add updated timestamp
        update_fields["updated_at"] = datetime.now(timezone.utc)
        
        # Update user in database
        self.users_collection.update_one(
            {"_id": user_id},
            {"$set": update_fields}
        )
        
        # Return updated user profile
        return await self.get_user_profile(user_id)
    
    async def delete_user(self, user_id: str) -> Dict[str, str]:
        """
        Delete user account
        
        Args:
            user_id: User ID
            
        Returns:
            Success message
            
        Raises:
            HTTPException: If user not found
        """
        result = self.users_collection.delete_one({"_id": user_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Also delete user's conversations and messages
        from app.db_utility.mongo_db import mongo_db
        mongo_db["conversations"].delete_many({"user_id": user_id})
        
        # Get conversation IDs to delete associated messages
        conversations = mongo_db["conversations"].find({"user_id": user_id})
        conversation_ids = [conv["_id"] for conv in conversations]
        
        if conversation_ids:
            mongo_db["messages"].delete_many({"conversation_id": {"$in": conversation_ids}})
        
        return {"message": "User account deleted successfully"}
