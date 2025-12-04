from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from app.utility.security import get_current_user
from app.controllers.message_controller import MessageController

router = APIRouter(prefix="/messages", tags=["Messages"])

# Initialize controller
message_controller = MessageController()

# Request/Response Models
class MessageCreate(BaseModel):
    conversation_id: str
    role: str = Field(..., pattern="^(human|ai)$")
    content: str = Field(..., min_length=1)

class MessageResponse(BaseModel):
    conversation_id: str = Field(None)
    role: str
    content: str
    created_at: datetime

# Endpoints

@router.post("", response_model=MessageResponse, status_code=201)
async def create_message(
    message_data: MessageCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new message in a conversation"""
    return await message_controller.create_message(
        current_user["_id"],
        message_data
    )

@router.get("/conversation/{conversation_id}", response_model=List[MessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user)
):
    """Get all messages in a conversation"""
    return await message_controller.get_conversation_messages(
        conversation_id,
        current_user["_id"],
        skip=skip,
        limit=limit
    )
