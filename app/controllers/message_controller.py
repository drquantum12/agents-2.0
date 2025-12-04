from fastapi import HTTPException, status
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid


from app.db_utility.mongo_db import mongo_db


class MessageController:
    """Controller for handling message operations via sessions"""
    
    def __init__(self):
        self.sessions_collection = mongo_db["sessions"]
        self.conversations_collection = mongo_db["conversations"]
    
    async def create_message(
        self,
        user_id: str,
        message_data: Any # Using Any as input model needs update or loose typing for now
    ) -> Dict[str, Any]:
        """
        Add a new message to a session
        """
        # Verify conversation exists and belongs to user
        conversation = self.conversations_collection.find_one({
            "_id": message_data.conversation_id,
            "user_id": user_id
        })
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Create message object
        now = datetime.now(timezone.utc)
        
        new_message = {
            "type": "text", # Defaulting to text for now
            "data": {"content": message_data.content},
            "timestamp": now
        }
        
        # Push to sessions
        result = self.sessions_collection.update_one(
            {"_id": message_data.conversation_id},
            {"$push": {"messages": new_message}}
        )
        
        if result.matched_count == 0:
             # If session doesn't exist (shouldn't happen if conversation exists, but for safety)
             self.sessions_collection.insert_one({
                 "_id": message_data.conversation_id,
                 "messages": [new_message]
             })

        return {
            "conversation_id": message_data.conversation_id,
            "role": message_data.role, # Keeping role in response for compatibility if needed, though not in DB
            "content": message_data.content,
            "created_at": now
        }
    
    async def get_conversation_messages(
        self,
        conversation_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all messages in a conversation (session)
        """
        # Verify conversation exists and belongs to user
        conversation = self.conversations_collection.find_one({
            "_id": conversation_id,
            "user_id": user_id
        })
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Get session
        session = self.sessions_collection.find_one({"_id": conversation_id})
        
        if not session:
            return []
            
        messages = session.get("messages", [])
        
        # Apply pagination (in-memory for now as documents are embedded)
        # For very large arrays, aggregation pipeline with $slice is better
        start = skip
        end = skip + limit
        paginated_messages = messages[start:end]
        
        return [
            {
                "role": "user" if i % 2 == 0 else "assistant", # Inferring role for now or need to store it in type/data
                "content": msg["data"]["content"],
                "created_at": msg["timestamp"]
            }
            for i, msg in enumerate(paginated_messages)
        ]
