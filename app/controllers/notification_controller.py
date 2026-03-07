from fastapi import HTTPException, status
from typing import Dict, Any, List

from app.db_utility.mongo_db import mongo_db

PAGE_SIZE = 5


class NotificationController:
    """Controller for handling notification operations"""

    def __init__(self):
        self.notifications_collection = mongo_db["notifications"]

    async def get_notifications(self, user_id: str, page: int = 1) -> Dict[str, Any]:
        """
        Get paginated notifications for a user (5 per page), newest first.

        Args:
            user_id: The authenticated user's ID
            page: 1-based page number

        Returns:
            Paginated notifications with metadata
        """
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page number must be 1 or greater"
            )

        skip = (page - 1) * PAGE_SIZE

        total = self.notifications_collection.count_documents({"user_id": user_id})

        cursor = (
            self.notifications_collection
            .find({"user_id": user_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(PAGE_SIZE)
        )

        notifications = []
        for doc in cursor:
            notifications.append({
                "id": doc["_id"],
                "user_id": doc["user_id"],
                "message": doc["message"],
                "type": doc["type"],
                "created_at": doc["created_at"],
            })

        return {
            "page": page,
            "page_size": PAGE_SIZE,
            "total": total,
            "has_next": (skip + PAGE_SIZE) < total,
            "notifications": notifications,
        }

    async def delete_notification(self, notification_id: str, user_id: str) -> Dict[str, str]:
        """
        Delete a notification by its ID, scoped to the requesting user.

        Args:
            notification_id: The notification's _id
            user_id: The authenticated user's ID

        Returns:
            Success message

        Raises:
            HTTPException: 404 if not found or not owned by user
        """
        result = self.notifications_collection.delete_one(
            {"_id": notification_id, "user_id": user_id}
        )

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )

        return {"message": "Notification deleted successfully"}
