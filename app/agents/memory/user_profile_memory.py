"""
memory/user_profile_memory.py
─────────────────────────────────────────────
MongoDB CRUD wrapper for the `user_memory` collection.

This collection stores facts the agent learns about the user mid-session
that are richer than the structured `users` document fields — arbitrary
key-value observations like:
  • "struggles with: chain rule in differentiation"
  • "loves: space exploration topics"
  • "responds well to: Socratic questioning"

These are loaded into context at session start and surfaced to the agent
via the system prompt for personalisation.
"""

from datetime import datetime, timezone
from typing import Optional, List
from pymongo.database import Database
from pymongo.collection import Collection


class UserProfileMemory:
    COLLECTION = "user_memory"

    def __init__(self, db: Database) -> None:
        self.col: Collection = db[self.COLLECTION]

    # ── Read ──────────────────────────────────────────────────────────────

    def get(self, user_id: str) -> Optional[dict]:
        """Return the full user_memory document for a user, or None."""
        return self.col.find_one({"user_id": user_id}, {"_id": 0})

    def get_observations(self, user_id: str) -> List[dict]:
        """Return the list of agent observations for a user, newest first."""
        doc = self.get(user_id)
        if not doc:
            return []
        observations = doc.get("observations", [])
        return list(reversed(observations))   # newest first

    def format_for_prompt(self, user_id: str, limit: int = 10) -> str:
        """
        Return a compact string summarising the most recent agent observations.
        Designed to be injected into the system prompt.
        """
        observations = self.get_observations(user_id)[:limit]
        if not observations:
            return ""
        lines = [f"  • {o['key']}: {o['value']}" for o in observations]
        return "Learned about this student:\n" + "\n".join(lines)

    # ── Write ─────────────────────────────────────────────────────────────

    def add_observation(self, user_id: str, key: str, value: str) -> None:
        """
        Append a new key-value observation to the user's memory.
        Overwrites a previous observation with the same key.
        """
        now = datetime.now(tz=timezone.utc)

        # Remove existing entry with same key (upsert-style for observations)
        self.col.update_one(
            {"user_id": user_id},
            {"$pull": {"observations": {"key": key}}},
        )
        # Append the new observation
        self.col.update_one(
            {"user_id": user_id},
            {
                "$push": {"observations": {"key": key, "value": value, "updated_at": now}},
                "$set":  {"updated_at": now},
                "$setOnInsert": {"created_at": now, "user_id": user_id},
            },
            upsert=True,
        )

    def clear(self, user_id: str) -> None:
        """Wipe all memory for a user."""
        self.col.delete_one({"user_id": user_id})
