from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Literal, Optional
from datetime import datetime

from app.utility.security import get_current_user
from app.controllers.notification_controller import NotificationController

router = APIRouter(prefix="/notifications", tags=["Notifications"])

notification_controller = NotificationController()


# Response Models

class NotificationItem(BaseModel):
    id: str
    user_id: str
    message: str
    type: Literal["info", "warn", "err"]
    created_at: datetime


class PaginatedNotificationsResponse(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool
    notifications: List[NotificationItem]


class DeleteNotificationResponse(BaseModel):
    message: str


# Endpoints

@router.get("", response_model=PaginatedNotificationsResponse)
async def get_notifications(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    current_user: dict = Depends(get_current_user),
):
    """Get paginated notifications for the current user (5 per page), newest first."""
    return await notification_controller.get_notifications(current_user["_id"], page)


@router.delete("/{notification_id}", response_model=DeleteNotificationResponse)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a specific notification by ID. Only the owning user may delete it."""
    return await notification_controller.delete_notification(notification_id, current_user["_id"])
