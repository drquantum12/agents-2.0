"""
Student profile CRUD + msgpack-safe sanitization.

MongoDB collection: neurosattva.student_memory
  doc shape: { user_id, name, grade, board, interests, mastered_concepts, ... }
"""

import logging
from datetime import date, datetime

try:
    from bson import ObjectId
except Exception:
    ObjectId = None  # type: ignore[assignment]

from .db import student_memory_collection, student_profile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _sanitize_for_checkpoint(value):
    """Recursively convert Mongo / Python types into msgpack-safe primitives."""
    if ObjectId is not None and isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_for_checkpoint(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_checkpoint(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Profile I/O
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE_KEYS = {
    "name": "",
    "grade": 10,
    "board": "CBSE",
    "subject": "Mathematics",
    "learning_style": "example-driven",
    "personality_notes": "",
    "interests": [],
    "mastered_concepts": [],
    "struggling_concepts": [],
    "session_summaries": [],
    "total_sessions": 0,
    "last_active": None,
}


def load_student_profile(user_id: str) -> dict:
    """Load or auto-create the student's long-term world model from MongoDB."""
    try:
        profile = student_memory_collection.find_one({"user_id": user_id})
        if not profile:
            user = student_profile.find_one({"_id": user_id})
            profile = {
                **_DEFAULT_PROFILE_KEYS,
                "user_id": user_id,
                "name": user["name"] if user else "Student",
                "grade": user["grade"] if user else 10,
                "board": user["board"] if user else "CBSE",
            }
            student_memory_collection.insert_one(profile)
            logger.info(f"Created new student profile for {user_id}")
        profile.pop("_id", None)
        return _sanitize_for_checkpoint(profile)
    except Exception as exc:
        logger.error(f"Error loading student profile for {user_id}: {exc}")
        return {
            "user_id": user_id,
            "name": user_id,
            "grade": 10,
            "board": "CBSE",
            "learning_style": "example-driven",
            "interests": [],
            "mastered_concepts": [],
            "struggling_concepts": [],
        }


def save_student_profile(user_id: str, profile: dict) -> None:
    """Upsert the student's world model to MongoDB."""
    try:
        clean = _sanitize_for_checkpoint(profile)
        clean.pop("_id", None)
        clean["user_id"] = str(user_id)
        student_memory_collection.replace_one({"user_id": user_id}, clean, upsert=True)
        logger.info(f"Saved student profile for {user_id}")
    except Exception as exc:
        logger.error(f"Error saving student profile for {user_id}: {exc}")
