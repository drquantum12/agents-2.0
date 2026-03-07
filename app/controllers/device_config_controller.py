from fastapi import HTTPException, status
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid

from app.db_utility.mongo_db import mongo_db


class DeviceConfigController:
    """Controller for handling device configuration operations"""

    VALID_LEARNING_MODES = {"Strict", "Normal"}
    VALID_RESPONSE_TYPES = {"Detailed", "Concise"}
    VALID_DIFFICULTY_LEVELS = {"Beginner", "Intermediate", "Advanced"}

    DEFAULT_CONFIG = {
        "learning_mode": "Normal",
        "response_type": "Detailed",
        "difficulty_level": "Beginner",
    }

    def __init__(self):
        self.collection = mongo_db["device_config"]

    async def get_device_config(self, user_id: str) -> Dict[str, Any]:
        """
        Get device configuration for a user.
        If no configuration exists, a default one is created and returned.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            Device configuration document.
        """
        config = self.collection.find_one({"user_id": user_id})

        if not config:
            # Create default config
            new_config = {
                "_id": str(uuid.uuid4()),
                "user_id": user_id,
                **self.DEFAULT_CONFIG,
                "created_at": datetime.now(timezone.utc),
                "updated_at": None,
            }
            self.collection.insert_one(new_config)
            config = new_config

        return {
            "id": config["_id"],
            "user_id": config["user_id"],
            "learning_mode": config["learning_mode"],
            "response_type": config["response_type"],
            "difficulty_level": config["difficulty_level"],
            "created_at": config.get("created_at"),
            "updated_at": config.get("updated_at"),
        }

    async def update_device_config(
        self, user_id: str, update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Partially update device configuration for a user.
        Creates a default config first if one does not exist.

        Args:
            user_id: The authenticated user's ID.
            update_data: Fields to update (learning_mode, response_type, difficulty_level).

        Returns:
            Updated device configuration document.

        Raises:
            HTTPException 400: If an invalid value is provided for any field.
        """
        # Validate values
        if "learning_mode" in update_data and update_data["learning_mode"] not in self.VALID_LEARNING_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid learning_mode. Must be one of: {sorted(self.VALID_LEARNING_MODES)}",
            )
        if "response_type" in update_data and update_data["response_type"] not in self.VALID_RESPONSE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid response_type. Must be one of: {sorted(self.VALID_RESPONSE_TYPES)}",
            )
        if "difficulty_level" in update_data and update_data["difficulty_level"] not in self.VALID_DIFFICULTY_LEVELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid difficulty_level. Must be one of: {sorted(self.VALID_DIFFICULTY_LEVELS)}",
            )

        # Ensure a config document exists
        config = self.collection.find_one({"user_id": user_id})
        if not config:
            # Create default config first
            await self.get_device_config(user_id)

        update_data["updated_at"] = datetime.now(timezone.utc)

        self.collection.update_one(
            {"user_id": user_id},
            {"$set": update_data},
        )

        return await self.get_device_config(user_id)
