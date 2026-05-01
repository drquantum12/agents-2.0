"""
memory/teacher_memory.py
─────────────────────────────────────────────
MongoDB CRUD wrapper for the `teacher_memory` collection.

Responsibilities:
  • Persist lesson state (topic, plan, status, current subtopic, step context)
    so it survives LangGraph checkpoint resets or cross-device sessions.
  • Provide a `sync_to_state()` helper that returns the fields AgentState
    expects — keeps node code clean.

The LangGraph checkpoint is the authoritative source DURING a session.
This collection is written to whenever lesson state changes and is the
source of truth for SESSION RESTORE (first turn of a new session).
"""

from typing import Optional, List
from pymongo.collection import Collection
from pymongo.database import Database


class TeacherMemoryManager:
    COLLECTION = "teacher_memory"

    def __init__(self, db: Database) -> None:
        self.col: Collection = db[self.COLLECTION]

    # ── Read ──────────────────────────────────────────────────────────────

    def get(self, user_id: str) -> Optional[dict]:
        """Return the teacher memory document for a user, or None."""
        return self.col.find_one({"user_id": user_id}, {"_id": 0})

    def sync_to_state(self, user_id: str) -> dict:
        """
        Return a dict of state-compatible keys loaded from teacher memory.
        Used when restoring a session so the checkpoint gets the right fields.
        """
        mem = self.get(user_id) or {}
        return {
            "topic":            mem.get("topic"),
            "lesson_plan":      mem.get("lesson_plan"),
            "lesson_status":    mem.get("lesson_status", "OFF"),
            "current_subtopic": mem.get("current_subtopic"),
            "step_context":     mem.get("step_context"),
        }

    # ── Write ─────────────────────────────────────────────────────────────

    def upsert(self, user_id: str, data: dict) -> None:
        """
        Merge `data` into the teacher memory document for this user.
        Creates a new document if none exists.
        """
        self.col.update_one(
            {"user_id": user_id},
            {"$set": data},
            upsert=True,
        )

    def start_lesson(
        self,
        user_id: str,
        topic: str,
        lesson_plan: List[str],
        first_subtopic: str,
    ) -> None:
        """Atomic write when a new lesson begins."""
        self.upsert(user_id, {
            "topic":            topic,
            "lesson_plan":      lesson_plan,
            "lesson_status":    "ON",
            "current_subtopic": first_subtopic,
            "step_context":     f"Starting lesson on '{topic}'. First subtopic: '{first_subtopic}'.",
        })

    def advance_subtopic(
        self,
        user_id: str,
        completed: str,
        next_subtopic: Optional[str],
    ) -> None:
        """Advance pointer after a subtopic is explained."""
        self.upsert(user_id, {
            "current_subtopic": next_subtopic,
            "step_context":     (
                f"Covered: '{completed}'. "
                + (f"Next: '{next_subtopic}'." if next_subtopic else "Lesson complete.")
            ),
        })

    def end_lesson(self, user_id: str) -> None:
        """Mark lesson as finished but keep topic/plan for reference."""
        self.upsert(user_id, {
            "lesson_status":    "OFF",
            "current_subtopic": None,
            "step_context":     None,
        })

    def clear_all(self, user_id: str) -> None:
        """Full reset — wipe all lesson data for a user."""
        self.col.delete_one({"user_id": user_id})
