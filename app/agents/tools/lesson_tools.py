"""
tools/lesson_tools.py
─────────────────────────────────────────────
Four tools that manage the guided study-session lifecycle:

  start_lesson(topic, subtopics)
    → Called by the agent after it generates a subtopic breakdown.
      Initialises lesson state in TeacherMemory, sends lesson_progress
      signal to device (1 / N).

  advance_subtopic()
    → Called after the student answers a check-in question correctly.
      Moves the pointer forward. If all subtopics are done, ends the lesson.
      Sends updated lesson_progress signal.

  end_lesson(summary)
    → Closes the lesson, speaks a summary, clears state. Called by
      advance_subtopic automatically on completion, or by the agent if the
      student wants to stop early.

  flag_weak_concept(concept)
    → Records a concept the student got wrong. Does NOT advance the subtopic.
      The agent should reteach before advancing.

All four tools patch AgentState via _state_patches_var and send the
lesson_progress WS frame via _signal_fn_var so the device can render
the subtopic counter ("Subtopic 2 of 4").
"""

import json
import logging
from typing import List

from langchain_core.tools import tool

from .context import (
    _user_context_var,
    _memory_var,
    _lesson_state_var,
    _state_patches_var,
    _signal_fn_var,
)

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _patch(key: str, value) -> None:
    p = _state_patches_var.get()
    if p is not None:
        p[key] = value


def _send_lesson_progress(current: int, total: int) -> None:
    """Push {"type":"lesson_progress","current":N,"total":M} to the device."""
    fn = _signal_fn_var.get()
    if fn is None:
        return
    payload = json.dumps(
        {"type": "lesson_progress", "current": current, "total": total},
        separators=(',', ':'),
    )
    try:
        fn(payload)
        logger.info("lesson_progress: %d/%d sent to device", current, total)
    except Exception as exc:
        logger.warning("lesson_progress signal failed: %s", exc)


def _teacher_memory():
    mem = _memory_var.get() or {}
    return mem.get("teacher")


# ── start_lesson ──────────────────────────────────────────────────────────────

@tool
def start_lesson(topic: str, subtopics: List[str]) -> str:
    """
    Begin a structured lesson on a topic the student wants to learn.

    Call this AFTER you have generated a list of 3-5 subtopics that break
    the topic into logical teaching chunks. Do NOT call this for simple
    one-sentence answers — only for topics that genuinely need multi-step
    explanation.

    The tool saves the lesson plan, signals the device to show subtopic
    progress (1 of N), and returns a cue for you to start explaining the
    first subtopic.

    Args:
        topic:     The main topic being taught. E.g. "Newton's Laws of Motion"
        subtopics: Ordered list of 3-5 subtopic strings.
                   E.g. ["What is a force?", "Newton's First Law",
                          "Newton's Second Law", "Newton's Third Law",
                          "Real-world examples"]

    Returns a short instruction string confirming lesson has started.
    """
    if not subtopics or len(subtopics) < 2:
        return "Error: provide at least 2 subtopics to start a lesson."

    user_ctx  = _user_context_var.get() or {}
    user_id   = user_ctx.get("user_id", "")
    tm        = _teacher_memory()
    first     = subtopics[0]

    if tm and user_id:
        try:
            tm.start_lesson(user_id, topic, subtopics, first)
        except Exception as exc:
            logger.error("start_lesson: TeacherMemory write failed: %s", exc)

    # Patch AgentState so the system prompt sees the new lesson immediately
    _patch("lesson_status",    "ON")
    _patch("topic",            topic)
    _patch("lesson_plan",      subtopics)
    _patch("current_subtopic", first)
    _patch("subtopic_idx",     0)
    _patch("step_context",     f"Starting lesson on '{topic}'. First subtopic: '{first}'.")

    _send_lesson_progress(1, len(subtopics))

    logger.info("start_lesson: topic='%s' plan=%s user=%s", topic, subtopics, user_id[:12] if user_id else "?")
    return (
        f"Lesson started. Topic: '{topic}'. Plan: {subtopics}. "
        f"Now explain subtopic 1 of {len(subtopics)}: '{first}'. "
        f"After explaining, ask ONE specific probe question to check understanding "
        f"before calling advance_subtopic()."
    )


# ── advance_subtopic ──────────────────────────────────────────────────────────

@tool
def advance_subtopic() -> str:
    """
    Advance to the next subtopic after the student has demonstrated understanding.

    Call this ONLY after the student answers your check-in question correctly.
    If they answered incorrectly, reteach first — do NOT advance.

    If this was the last subtopic, the lesson ends automatically.

    Returns a cue for what to do next (explain next subtopic, or close lesson).
    """
    lesson = _lesson_state_var.get() or {}
    plan   = lesson.get("lesson_plan") or []
    idx    = lesson.get("subtopic_idx", 0)

    if not plan:
        return "No active lesson plan found. Has start_lesson been called?"

    completed  = plan[idx] if idx < len(plan) else plan[-1]
    next_idx   = idx + 1

    user_ctx = _user_context_var.get() or {}
    user_id  = user_ctx.get("user_id", "")
    tm       = _teacher_memory()

    if next_idx >= len(plan):
        # All subtopics done — end lesson automatically
        if tm and user_id:
            try:
                tm.advance_subtopic(user_id, completed, None, next_idx)
                tm.end_lesson(user_id)
            except Exception as exc:
                logger.error("advance_subtopic: TeacherMemory error: %s", exc)

        _patch("lesson_status",    "OFF")
        _patch("current_subtopic", None)
        _patch("subtopic_idx",     next_idx)
        _patch("step_context",     None)
        _send_lesson_progress(0, 0)   # 0/0 = lesson complete signal

        logger.info("advance_subtopic: all %d subtopics done for user=%s", len(plan), user_id[:12] if user_id else "?")
        return (
            f"All {len(plan)} subtopics of '{lesson.get('topic', 'the topic')}' are complete. "
            f"Now call end_lesson(summary) with a brief spoken summary of everything covered."
        )

    next_subtopic = plan[next_idx]

    if tm and user_id:
        try:
            tm.advance_subtopic(user_id, completed, next_subtopic, next_idx)
        except Exception as exc:
            logger.error("advance_subtopic: TeacherMemory write failed: %s", exc)

    _patch("current_subtopic", next_subtopic)
    _patch("subtopic_idx",     next_idx)
    _patch("step_context",     f"Covered: '{completed}'. Next: '{next_subtopic}'.")

    _send_lesson_progress(next_idx + 1, len(plan))

    logger.info(
        "advance_subtopic: %d→%d ('%s') user=%s",
        idx, next_idx, next_subtopic, user_id[:12] if user_id else "?"
    )
    return (
        f"Advanced to subtopic {next_idx + 1} of {len(plan)}: '{next_subtopic}'. "
        f"Explain this subtopic, then ask ONE specific probe question before advancing again."
    )


# ── end_lesson ────────────────────────────────────────────────────────────────

@tool
def end_lesson(summary: str) -> str:
    """
    Close the current lesson and speak a summary to the student.

    Call this after advance_subtopic() says the lesson is complete, or if
    the student explicitly asks to stop. Always provide a real summary —
    do not pass an empty string.

    Args:
        summary: 2-4 sentences spoken aloud summarising what was covered
                 and what the student should remember. No markdown.

    Returns the summary string to speak, plus a closing line.
    """
    user_ctx = _user_context_var.get() or {}
    user_id  = user_ctx.get("user_id", "")
    lesson   = _lesson_state_var.get() or {}
    topic    = lesson.get("topic", "the topic")
    tm       = _teacher_memory()

    if tm and user_id:
        try:
            tm.end_lesson(user_id)
        except Exception as exc:
            logger.error("end_lesson: TeacherMemory write failed: %s", exc)

    _patch("lesson_status",    "OFF")
    _patch("current_subtopic", None)
    _patch("subtopic_idx",     0)
    _patch("step_context",     None)
    _send_lesson_progress(0, 0)

    logger.info("end_lesson: topic='%s' user=%s", topic, user_id[:12] if user_id else "?")
    return summary


# ── flag_weak_concept ─────────────────────────────────────────────────────────

@tool
def flag_weak_concept(concept: str) -> str:
    """
    Record that the student answered a check-in question incorrectly on
    this concept. Does NOT advance the lesson — reteach first.

    Call this whenever the student gives a wrong answer so their weak
    spots are tracked for future spaced-repetition and revision.

    Args:
        concept: Short label for the concept they struggled with.
                 E.g. "Newton's Third Law action-reaction pairs"

    Returns a cue reminding you to reteach before advancing.
    """
    user_ctx = _user_context_var.get() or {}
    user_id  = user_ctx.get("user_id", "")
    tm       = _teacher_memory()

    if tm and user_id:
        try:
            tm.flag_weak_concept(user_id, concept)
        except Exception as exc:
            logger.error("flag_weak_concept: TeacherMemory write failed: %s", exc)

    # Append to in-state list so this session's prompt sees it immediately
    lesson = _lesson_state_var.get() or {}
    patches = _state_patches_var.get() or {}
    current_weak = patches.get("weak_concepts") or []
    _patch("weak_concepts", current_weak + [concept])

    logger.info("flag_weak_concept: '%s' for user=%s", concept, user_id[:12] if user_id else "?")
    return (
        f"Noted: student struggled with '{concept}'. "
        f"Reteach using a different analogy or example. "
        f"Do NOT call advance_subtopic() until they answer correctly."
    )
