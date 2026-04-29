"""
Typed schema for the intent_router LLM classifier.

Used with ``fast_llm.with_structured_output(IntentClassification)`` so that
LangChain's function-calling integration forces the model to emit a
well-typed object — no fragile regex/JSON parsing on the happy path.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    """Structured output for the intent_router LLM classifier."""

    intent: Literal[
        "general_chat",
        "learning_intent",
        "lesson_continue",
        "lesson_digress",
        "lesson_stop",
    ] = Field(
        description=(
            "The student's intent:\n"
            "  general_chat    — casual talk, not about studying\n"
            "  learning_intent — explicitly wants to learn or understand a topic"
            " (also populate 'topic')\n"
            "  lesson_continue — engaging with or answering within the active lesson\n"
            "  lesson_digress  — asking something unrelated while mid-lesson\n"
            "  lesson_stop     — wants to end the current lesson"
        )
    )
    topic: str = Field(
        default="",
        description=(
            "The specific topic or concept the student wants to learn. "
            "Populate ONLY when intent='learning_intent', using the student's exact "
            "phrasing, cleaned up (e.g. 'photosynthesis', 'Pythagoras theorem', "
            "'how black holes form'). Leave empty for all other intents."
        ),
    )
