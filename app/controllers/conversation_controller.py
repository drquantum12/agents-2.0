from fastapi import HTTPException, status
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid

from app.models.conversation import ConversationCreate, ConversationUpdate
from app.db_utility.mongo_db import mongo_db


class ConversationController:
    """Controller for handling conversation operations"""
    
    def __init__(self):
        self.conversations_collection = mongo_db["conversations"]
        self.sessions_collection = mongo_db["sessions"]
    
    async def create_conversation(
        self, 
        user_id: str, 
        conversation_data: ConversationCreate
    ) -> Dict[str, Any]:
        """
        Create a new conversation for a user
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        new_conversation = {
            "_id": conversation_id,
            "user_id": user_id,
            "topic": conversation_data.topic,
            "created_at": now
        }
        
        self.conversations_collection.insert_one(new_conversation)
        
        # Create corresponding session
        self.sessions_collection.insert_one({
            "_id": conversation_id,
            "messages": []
        })
        
        return {
            "id": conversation_id,
            "user_id": user_id,
            "topic": new_conversation["topic"],
            "created_at": new_conversation["created_at"]
        }
    
    async def get_conversation(
        self, 
        conversation_id: str, 
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get a specific conversation by ID
        """
        conversation = self.conversations_collection.find_one({
            "_id": conversation_id,
            "user_id": user_id
        })
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        return {
            "id": conversation["_id"],
            "user_id": conversation["user_id"],
            "topic": conversation["topic"],
            "created_at": conversation["created_at"]
        }
    
    async def get_user_conversations(
        self, 
        user_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all conversations for a user
        """
        conversations = self.conversations_collection.find(
            {"user_id": user_id}
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        return [
            {
                "id": conv["_id"],
                "user_id": conv["user_id"],
                "topic": conv["topic"],
                "created_at": conv["created_at"]
            }
            for conv in conversations
        ]
    
    async def update_conversation(
        self,
        conversation_id: str,
        user_id: str,
        update_data: ConversationUpdate
    ) -> Dict[str, Any]:
        """
        Update a conversation
        """
        # Check if conversation exists and belongs to user
        conversation = self.conversations_collection.find_one({
            "_id": conversation_id,
            "user_id": user_id
        })
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Extract only provided fields
        update_fields = {
            k: v for k, v in update_data.model_dump(exclude_unset=True).items()
        }
        
        if not update_fields:
            # No updates, return current conversation
            return await self.get_conversation(conversation_id, user_id)
        
        # Update conversation
        self.conversations_collection.update_one(
            {"_id": conversation_id},
            {"$set": update_fields}
        )
        
        # Return updated conversation
        return await self.get_conversation(conversation_id, user_id)
    
    async def delete_conversation(
        self,
        conversation_id: str,
        user_id: str
    ) -> Dict[str, str]:
        """
        Delete a conversation and its session
        """
        # Check if conversation exists and belongs to user
        result = self.conversations_collection.delete_one({
            "_id": conversation_id,
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Delete corresponding session
        self.sessions_collection.delete_one({"_id": conversation_id})
        
        return {"message": "Conversation deleted successfully"}
