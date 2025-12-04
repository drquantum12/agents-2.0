from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.utility.security import get_current_user
from app.controllers.conversation_controller import ConversationController
from app.models.conversation import ConversationCreate, ConversationUpdate

router = APIRouter(prefix="/conversations", tags=["Conversations"])

# Initialize controller
conversation_controller = ConversationController()

# Response Models
class ConversationResponse(BaseModel):
    id: str
    user_id: str
    topic: str
    created_at: datetime
    updated_at: datetime

# Endpoints

@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new conversation"""
    return await conversation_controller.create_conversation(
        current_user["_id"], 
        conversation_data
    )

@router.get("", response_model=List[ConversationResponse])
async def get_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get all conversations for the current user"""
    return await conversation_controller.get_user_conversations(
        current_user["_id"],
        skip=skip,
        limit=limit
    )

@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific conversation by ID"""
    return await conversation_controller.get_conversation(
        conversation_id,
        current_user["_id"]
    )

@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    update_data: ConversationUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update a conversation"""
    return await conversation_controller.update_conversation(
        conversation_id,
        current_user["_id"],
        update_data
    )

@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a conversation and all its messages"""
    return await conversation_controller.delete_conversation(
        conversation_id,
        current_user["_id"]
    )
