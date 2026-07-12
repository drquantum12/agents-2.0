"""
tools/profile_tools.py
─────────────────────────────────────────────
get_user_profile    — read the student's learning profile from MongoDB.
update_user_profile — write a profile field the agent learned mid-session.

The agent should call get_user_profile when it needs to personalise a
response and the grade/board are not already available in context.
It should call update_user_profile whenever it observes something new
about the student (a topic they struggle with, a preferred pace, etc.).
"""
import logging
from langchain_core.tools import tool
from app.db_utility.mongo_db import mongo_db
from .context import _user_context_var

logger = logging.getLogger(__name__)

# Only these fields may be written to prevent accidental data corruption.
_UPDATABLE_FIELDS = frozenset({
    "grade",
    "board",
    "interests",
    "learning_pace",       # "slow" | "normal" | "fast"
    "preferred_language",  # BCP-47 code, e.g. "en-IN", "hi-IN"
    "weak_topics",
    "strong_topics",
})


@tool
def get_user_profile(user_id: str) -> str:
    """
    Retrieve the student's learning profile: grade, board, interests,
    learning pace, and topic strengths/weaknesses.

    Use this when you need to personalise a lesson or response and
    the grade/board are not already known from the conversation.

    Args:
        user_id: The student's MongoDB user ID

    Returns a plain-text summary of the profile fields.
    """
    try:
        user = mongo_db["users"].find_one(
            {"_id": user_id},
            {"password": 0, "firebase_uid": 0},
        )
        if not user:
            return f"No profile found for user {user_id}"

        lines: list[str] = []
        for field, label in [
            ("name",               "Name"),
            ("grade",              "Grade"),
            ("board",              "Board"),
            ("interests",          "Interests"),
            ("learning_pace",      "Learning pace"),
            ("preferred_language", "Preferred language"),
            ("weak_topics",        "Weak topics"),
            ("strong_topics",      "Strong topics"),
        ]:
            val = user.get(field)
            if val:
                lines.append(f"{label}: {val}")

        logger.info("get_user_profile: retrieved profile for %s", user_id)
        return "\n".join(lines) if lines else "Profile exists but no learning fields are set yet."

    except Exception as exc:
        logger.error("get_user_profile error: %s", exc)
        return f"Error retrieving profile: {exc}"


@tool
def update_user_profile(user_id: str, field: str, value: str) -> str:
    """
    Update a field in the student's learning profile based on what you
    observed during this conversation. Use this proactively to improve
    future personalisation.

    Updatable fields:
      grade, board, interests, learning_pace, preferred_language,
      weak_topics, strong_topics

    Args:
        user_id: The student's MongoDB user ID
        field:   The profile field to update (from the list above)
        value:   The new value to store

    Returns a confirmation string.
    """
    if field not in _UPDATABLE_FIELDS:
        return (
            f"Cannot update field '{field}'. "
            f"Allowed: {', '.join(sorted(_UPDATABLE_FIELDS))}"
        )

    try:
        mongo_db["users"].update_one(
            {"_id": user_id},
            {"$set": {field: value}},
        )

        # Refresh the in-flight ContextVar cache for board/grade
        ctx = _user_context_var.get()
        if ctx and field in ("board", "grade"):
            ctx[field] = value

        logger.info("update_user_profile: %s.%s = %r", user_id, field, value)
        return f"Profile updated — {field}: {value}"

    except Exception as exc:
        logger.error("update_user_profile error: %s", exc)
        return f"Error updating profile: {exc}"
