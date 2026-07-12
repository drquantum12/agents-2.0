"""
nodes/user_confirmation.py
─────────────────────────────────────────────
Handles CONFIRM_WITH_USER intent — the user is responding to a question
or offer the tutor made in the previous turn.

Primary scenario:  user accepted a lesson offer
  → generate lesson plan
  → set lesson_status = ON
  → explain first subtopic
  → sync to TeacherMemory

Secondary scenario: user declined
  → acknowledge, clear awaiting flag

Tertiary scenario: ambiguous reply
  → ask for yes/no clarification (keep awaiting_user_input = True)
"""

import logging
from langchain_core.messages import AIMessage
from app.agents.llm import llm

from ..state import AgentState
from ..memory.teacher_memory import TeacherMemoryManager
from ..prompts.teacher import build_lesson_intro_prompt, build_lesson_plan_prompt

logger = logging.getLogger(__name__)

# ── Keyword sets for lightweight confirmation detection ───────────────────────
_YES_SIGNALS = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "go", "start",
    "begin", "let's go", "lets go", "go ahead", "sounds good", "definitely",
    "absolutely", "of course", "please", "why not", "alright", "sure thing",
}
_NO_SIGNALS = {
    "no", "nope", "nah", "skip", "not now", "later", "cancel", "stop",
    "pass", "don't", "dont", "not interested", "maybe later", "nevermind",
    "never mind",
}


def _detect_confirmation(query: str) -> str:  # "YES" | "NO" | "UNCLEAR"
    q = query.lower().strip().rstrip(".,!?")
    tokens = set(q.split())

    # Multi-word phrase check
    for phrase in _YES_SIGNALS:
        if phrase in q:
            return "YES"
    for phrase in _NO_SIGNALS:
        if phrase in q:
            return "NO"

    # Single-token check
    if tokens & _YES_SIGNALS:
        return "YES"
    if tokens & _NO_SIGNALS:
        return "NO"

    return "UNCLEAR"


def _make_lesson_plan(topic: str, state: AgentState) -> list[str]:
    """Ask LLM to build a subtopic list for the topic."""
    prompt = build_lesson_plan_prompt(topic, state)
    raw = llm.invoke(prompt).content.strip()
    lines = [
        line.strip().lstrip("0123456789.-) ").strip()
        for line in raw.split("\n")
        if line.strip() and any(c.isalpha() for c in line)
    ]
    return lines[:10]


# ── Main node ─────────────────────────────────────────────────────────────────

def user_confirmation_node(
    state: AgentState,
    teacher_memory: TeacherMemoryManager,
) -> dict:
    """
    Resolves a pending yes/no from the user.

    Returns a partial AgentState dict.
    """
    query   = state.get("query", "").strip()
    topic   = state.get("topic")
    user_id = state.get("user_id", "")

    confirmation = _detect_confirmation(query)
    logger.info("UserConfirmation: detected '%s' from query: %s", confirmation, query[:60])

    # ── YES: start the lesson ──────────────────────────────────────────────
    if confirmation == "YES" and topic:
        lesson_plan   = _make_lesson_plan(topic, state)
        first_sub     = lesson_plan[0] if lesson_plan else topic
        step_ctx      = f"Starting lesson on '{topic}'. First subtopic: '{first_sub}'."

        intro_prompt  = build_lesson_intro_prompt(topic, first_sub, lesson_plan, state)
        intro_message = llm.invoke(intro_prompt).content.strip()

        # Persist to MongoDB
        teacher_memory.start_lesson(
            user_id       = user_id,
            topic         = topic,
            lesson_plan   = lesson_plan,
            first_subtopic= first_sub,
        )

        logger.info("UserConfirmation: lesson started — topic='%s', plan=%s", topic, lesson_plan)
        return {
            "messages":           [AIMessage(content=intro_message)],
            "lesson_status":      "ON",
            "lesson_plan":        lesson_plan,
            "current_subtopic":   first_sub,
            "step_context":       step_ctx,
            "awaiting_user_input": False,
        }

    # ── YES but no topic set (edge case) ──────────────────────────────────
    if confirmation == "YES" and not topic:
        response = (
            "I'm not sure what topic you'd like to learn about! "
            "Could you let me know? For example: \"Teach me about photosynthesis.\""
        )
        return {
            "messages":           [AIMessage(content=response)],
            "awaiting_user_input": False,
        }

    # ── NO: decline gracefully ────────────────────────────────────────────
    if confirmation == "NO":
        response = (
            "No worries! 😊 Whenever you're ready to explore a topic in depth, "
            "just ask. I'm here to help."
        )
        return {
            "messages":           [AIMessage(content=response)],
            "awaiting_user_input": False,
        }

    # ── UNCLEAR: re-prompt ────────────────────────────────────────────────
    response = (
        "I didn't quite catch that — did you want to start the lesson? "
        "Please reply with **yes** or **no**."
    )
    return {
        "messages":           [AIMessage(content=response)],
        "awaiting_user_input": True,
    }
