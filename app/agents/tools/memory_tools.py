"""
tools/memory_tools.py
─────────────────────────────────────────────
set_reminder    — schedule a future spoken reminder stored in MongoDB.
spaced_repeat   — schedule spaced-repetition reviews at 1d / 3d / 7d.
clarify_intent  — ask the user a structured clarifying question before acting.
"""
import logging
from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool
from app.db_utility.mongo_db import mongo_db
from .context import _user_context_var, _state_patches_var

logger = logging.getLogger(__name__)


def _patch(key: str, value) -> None:
    p = _state_patches_var.get()
    if p is not None:
        p[key] = value


# ── set_reminder ──────────────────────────────────────────────────────────────

@tool
def set_reminder(message: str, delay_minutes: int) -> str:
    """
    Schedule a reminder that will be spoken aloud by the device at a future time.
    Use this when the student asks to be reminded, or when you proactively want
    to follow up (e.g., "I'll remind you to revise this before your exam tomorrow").

    Args:
        message:       What to say to the student when the reminder fires.
        delay_minutes: How many minutes from now to deliver the reminder (min: 1).

    Returns a confirmation message to read to the student.
    """
    if delay_minutes < 1:
        delay_minutes = 1

    user_ctx = _user_context_var.get() or {}
    user_id  = user_ctx.get("user_id", "unknown")

    try:
        now     = datetime.now(tz=timezone.utc)
        fire_at = now + timedelta(minutes=delay_minutes)
        mongo_db["reminders"].insert_one({
            "user_id":    user_id,
            "message":    message,
            "fire_at":    fire_at,
            "delivered":  False,
            "created_at": now,
        })
        hours, mins = divmod(delay_minutes, 60)
        time_str = (
            f"{hours} hour{'s' if hours != 1 else ''} and {mins} minute{'s' if mins != 1 else ''}"
            if hours else
            f"{delay_minutes} minute{'s' if delay_minutes != 1 else ''}"
        )
        logger.info("set_reminder: '%s' in %d min for %s", message[:50], delay_minutes, user_id)
        return f"Done! I'll remind you in {time_str}: {message}"

    except Exception as exc:
        logger.error("set_reminder error: %s", exc)
        return f"Error setting reminder: {exc}"


# ── spaced_repeat ─────────────────────────────────────────────────────────────

@tool
def spaced_repeat(topic: str) -> str:
    """
    Schedule spaced-repetition review sessions for a topic the student just learned.
    Call this after completing any lesson subtopic to reinforce long-term retention.
    Automatically schedules reviews at 1 day, 3 days, and 7 days from now.

    Args:
        topic: The topic or concept to review (e.g. "Newton's laws", "photosynthesis")

    Returns a confirmation to read to the student.
    """
    user_ctx = _user_context_var.get() or {}
    user_id  = user_ctx.get("user_id", "unknown")

    try:
        now = datetime.now(tz=timezone.utc)
        records = [
            {
                "user_id":    user_id,
                "topic":      topic,
                "review_at":  now + timedelta(days=d),
                "interval_days": d,
                "delivered":  False,
                "created_at": now,
            }
            for d in (1, 3, 7)
        ]
        mongo_db["spaced_reviews"].insert_many(records)
        logger.info("spaced_repeat: 3 reviews scheduled for '%s' for %s", topic, user_id)
        return (
            f"Great! I've scheduled review sessions for '{topic}' "
            f"in 1 day, 3 days, and 7 days to lock it into long-term memory."
        )

    except Exception as exc:
        logger.error("spaced_repeat error: %s", exc)
        return f"Error scheduling reviews: {exc}"


# ── clarify_intent ────────────────────────────────────────────────────────────

@tool
def clarify_intent(question: str, options: str = "") -> str:
    """
    Ask the user a clarifying question before proceeding with a task.
    Use this ONLY when the user's request is genuinely ambiguous AND the
    wrong interpretation would waste significant effort or give a wrong answer.
    Do not over-clarify simple requests.

    Signal "asking" to the device BEFORE calling this tool.

    Args:
        question: The specific clarifying question to ask the student.
        options:  Optional comma-separated choices to present.
                  Example: "CBSE, ICSE, State board"

    Returns the formatted question to speak aloud.
    Sets awaiting_user_input = True so the next turn routes correctly.
    """
    _patch("awaiting_user_input", True)

    if options:
        opts = [o.strip() for o in options.split(",") if o.strip()]
        choices = ", or ".join(opts) if len(opts) > 1 else opts[0]
        return f"{question} Is it {choices}?"
    return question
