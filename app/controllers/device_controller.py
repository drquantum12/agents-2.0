"""
Device controller — helpers for device ownership operations.

All functions use the synchronous pymongo client (mongo_db) to match
the existing project pattern.
"""

import uuid
from datetime import datetime, timezone

from app.db_utility.mongo_db import mongo_db


def _upsert_device_config(user_id: str, device_id: str, now: datetime) -> None:
    """
    Ensure a device_config document exists for user_id.
    Sets device_id and device_online fields.
    On first insert only, sets learning_mode / response_type / difficulty_level defaults.
    """
    mongo_db["device_config"].find_one_and_update(
        {"user_id": user_id},
        {
            "$set": {
                "device_id": device_id,
                "device_online": True,
                "last_seen_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "_id": str(uuid.uuid4()),
                "user_id": user_id,
                "learning_mode": "Normal",
                "response_type": "Concise",
                "difficulty_level": "Beginner",
                "created_at": now,
            },
        },
        upsert=True,
    )


def _notify_user_device_transferred(
    old_user_id: str,
    device_id: str,
    new_user_id: str,
) -> None:
    """Insert a warning notification for the previous device owner."""
    now = datetime.now(timezone.utc)
    mongo_db["notifications"].insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": old_user_id,
        "message": f"Your device {device_id} has been claimed by another user.",
        "type": "warn",
        "created_at": now,
    })


def release_devices_on_account_deletion(user_id: str) -> None:
    """
    Called during account deletion.
    Releases all devices owned by user_id and closes their open history entries.
    """
    now = datetime.now(timezone.utc)

    # 1. Mark all active devices owned by this user as unclaimed
    mongo_db["devices"].update_many(
        {"owner_user_id": user_id, "ownership_status": "active"},
        {"$set": {
            "owner_user_id": None,
            "ownership_status": "unclaimed",
            "is_online": False,
            "updated_at": now,
        }},
    )

    # 2. Close any open ownership_history entries for this user
    mongo_db["devices"].update_many(
        {
            "ownership_history.user_id": user_id,
            "ownership_history.released_at": None,
        },
        {"$set": {
            "ownership_history.$.released_at": now,
            "ownership_history.$.release_reason": "account_deleted",
        }},
    )
