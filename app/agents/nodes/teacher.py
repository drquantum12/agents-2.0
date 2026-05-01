"""
nodes/teacher.py
─────────────────────────────────────────────
Handles EXPLANATION intent. Contains the full lesson decision tree from
the architecture diagram:

                        ┌──────────────┐
                        │  TEACHER NODE │
                        └──────┬───────┘
                               │
               ┌───────────────▼────────────────┐
               │  Query related to current lesson?│
               └───────┬────────────────┬────────┘
                      NO               YES
                       │                │
        ┌──────────────▼──────┐    ┌────▼─────────────────────┐
        │ Short explanation    │    │   lesson_status == ON?    │
        │ + Lesson offer       │    └────┬────────────┬─────────┘
        │ (awaiting=True)      │        NO            YES
        └─────────────────────┘         │              │
                                        │         ┌────▼────────────────┐
                                 ┌──────▼───┐     │  mode == STRICT?    │
                                 │ Offer to  │     └────┬───────────┬────┘
                                 │ (re)start │         YES          NO
                                 │ lesson    │          │            │
                                 └──────────┘   ┌──────▼──┐  ┌──────▼──────────┐
                                                │  Force  │  │ Explain subtopic │
                                                │  lesson │  │ + advance pointer│
                                                └─────────┘  └─────────────────┘

TeacherMemoryManager is injected via functools.partial in graph.py so the
node signature stays compatible with LangGraph (single `state` argument).
"""

import logging
from functools import partial
from typing import Optional

from langchain_core.messages import AIMessage
from app.agents.llm import llm

from ..state import AgentState
from ..memory.teacher_memory import TeacherMemoryManager
from ..prompts.teacher import (
    build_relevance_check_prompt,
    build_topic_extract_prompt,
    build_short_explanation_prompt,
    build_lesson_plan_prompt,
    build_subtopic_explanation_prompt,
    build_strict_mode_prompt,
    build_lesson_restart_offer_prompt,
)

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_related(query: str, topic: str, subtopic: Optional[str]) -> bool:
    """Ask LLM whether the query relates to the active lesson topic."""
    prompt = build_relevance_check_prompt(query, topic, subtopic or "N/A")
    result = llm.invoke(prompt).content.strip().upper()
    return result.startswith("YES")


def _extract_topic(query: str) -> str:
    """Extract the educational topic from a free-form query."""
    prompt = build_topic_extract_prompt(query)
    return llm.invoke(prompt).content.strip()


def _make_lesson_plan(topic: str, state: AgentState) -> list[str]:
    """Generate an ordered list of subtopics for a given topic."""
    prompt = build_lesson_plan_prompt(topic, state)
    raw = llm.invoke(prompt).content.strip()
    lines = [
        line.strip().lstrip("0123456789.-) ").strip()
        for line in raw.split("\n")
        if line.strip() and any(c.isalpha() for c in line)
    ]
    return lines[:10]  # cap at 10 subtopics


def _next_subtopic(lesson_plan: list[str], current: Optional[str]) -> Optional[str]:
    """Return the subtopic after `current` in the plan, or None if at the end."""
    if not lesson_plan:
        return None
    try:
        idx = lesson_plan.index(current) if current in lesson_plan else -1
        return lesson_plan[idx + 1] if idx + 1 < len(lesson_plan) else None
    except (ValueError, IndexError):
        return None


# ── Main node ─────────────────────────────────────────────────────────────────

def teacher_node(state: AgentState, teacher_memory: TeacherMemoryManager) -> dict:
    """
    Processes EXPLANATION intent through the full lesson decision tree.
    Returns a partial AgentState dict with updated fields.
    """
    query           = state.get("query", "").strip()
    lesson_status   = (state.get("lesson_status") or "OFF").upper()
    topic           = state.get("topic")
    current_sub     = state.get("current_subtopic")
    lesson_plan     = state.get("lesson_plan") or []
    mode            = (state.get("mode") or "DEFAULT").upper()
    user_id         = state.get("user_id", "")

    # ── Branch A: No active lesson, or query is off-topic ─────────────────
    is_on_lesson = (
        lesson_status == "ON"
        and topic
        and _is_related(query, topic, current_sub)
    )

    if not is_on_lesson:
        # Identify what topic the user is asking about
        new_topic = _extract_topic(query)

        # Give a brief teaser explanation
        short_exp = llm.invoke(
            build_short_explanation_prompt(query, state)
        ).content.strip()

        offer_text = (
            f"{short_exp}\n\n"
            f"📚 Want me to run a **full structured lesson on {new_topic}**? "
            f"I'll break it into clear steps and guide you through each one. "
            f"Just say **yes** to kick things off!"
        )

        # Persist the topic so user_confirmation can pick it up
        teacher_memory.upsert(user_id, {"topic": new_topic, "lesson_status": "OFF"})

        logger.info("Teacher: offering new lesson on '%s'", new_topic)
        return {
            "messages":           [AIMessage(content=offer_text)],
            "awaiting_user_input": True,
            "topic":               new_topic,
            "lesson_status":       "OFF",
        }

    # ── Branch B: Active lesson, STRICT mode ─────────────────────────────
    if mode == "STRICT":
        response = llm.invoke(build_strict_mode_prompt(state)).content.strip()
        logger.info("Teacher: STRICT mode — redirecting to '%s'", current_sub)
        return {
            "messages":           [AIMessage(content=response)],
            "awaiting_user_input": False,
        }

    # ── Branch C: Active lesson, DEFAULT mode — explain & advance ─────────
    explanation = llm.invoke(
        build_subtopic_explanation_prompt(state)
    ).content.strip()

    nxt = _next_subtopic(lesson_plan, current_sub)
    step_ctx = (
        f"Covered: '{current_sub}'. "
        + (f"Next: '{nxt}'." if nxt else "Lesson complete.")
    )

    # Sync advancing state to MongoDB
    teacher_memory.advance_subtopic(user_id, completed=current_sub or "", next_subtopic=nxt)

    logger.info("Teacher: explained '%s', advancing to '%s'", current_sub, nxt)
    return {
        "messages":           [AIMessage(content=explanation)],
        "awaiting_user_input": False,
        "current_subtopic":    nxt or current_sub,
        "step_context":        step_ctx,
    }
