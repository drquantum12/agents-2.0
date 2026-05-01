"""
prompts/web_search.py
─────────────────────────────────────────────
With Gemini grounding there is no longer a separate "synthesise raw results"
step — Gemini handles retrieval + generation in a single call.

This module now provides:
  build_grounded_query(query, state) → str
    Wraps the student's raw query with just enough educational context so
    Gemini knows how to frame its grounded answer (grade, curriculum, etc.).
    Keep it short — the grounding tool does the heavy lifting.
"""

from ..state import AgentState


def build_grounded_query(query: str, state: AgentState) -> str:
    """
    Prepends lightweight educational context to the student's query before
    sending it to Gemini with Google Search grounding enabled.

    We intentionally keep this brief. Over-engineering the prompt can
    interfere with the grounding model's internal retrieval decisions.

    Args:
        query : The raw user query string.
        state : Current AgentState (used for grade / board context).

    Returns:
        A context-enriched query string ready for Gemini.
    """
    grade = state.get("grade")
    board = state.get("board")

    parts: list[str] = []

    # Educational framing only when useful calibration info is available
    if grade and board:
        parts.append(
            f"I am a Grade {grade} student ({board} curriculum). "
            f"Please explain in terms appropriate for my level."
        )
    elif grade:
        parts.append(
            f"I am a Grade {grade} student. "
            f"Please explain in terms appropriate for my level."
        )

    parts.append(query)
    parts.append(
    "Respond in plain text-to-speech friendly spoken sentences only. "
    "Do not use markdown, bullet points, numbered lists, bold, asterisks, "
    "headers, URLs, or any special symbols — the answer will be read aloud."
)
    return " ".join(parts)
