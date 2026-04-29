"""
retrieve_context — fetches relevant curriculum chunks from Milvus.

Only reached when sub_intent is "new_topic" or "step_complete".
Uses a lazy-loaded VectorDB singleton to avoid cold-start overhead.
"""

import logging

from app.agents.state.schema import AgentState

logger = logging.getLogger(__name__)

_vector_db = None


def _get_vector_db():
    """Return the VectorDB singleton, initialising on first call."""
    global _vector_db
    if _vector_db is None:
        from app.db_utility.vector_db import VectorDB  # lazy import keeps startup fast

        _vector_db = VectorDB()
    return _vector_db


def fetch_for_query(query: str, student_profile: dict) -> list[dict]:
    """
    Inline context fetch for a specific query string.
    Called by teacher_node when a lesson step advances, so the next step
    has fresh curriculum context before the LLM generates its teaching response.
    Returns an empty list on failure so the node can degrade gracefully.
    """
    try:
        vdb = _get_vector_db()
        content, sources = vdb.get_similar_documents(
            text=query,
            top_k=3,
            board=student_profile.get("board", "CBSE"),
            grade=student_profile.get("grade", 10),
        )
        return [
            {
                "concept": query,
                "explanation": content,
                "analogies": "",
                "chapter": "",
                "subject": student_profile.get("subject", "Mathematics"),
                "doc_id": sources[0] if sources else "",
            }
        ]
    except Exception as exc:
        logger.error(f"fetch_for_query error: {exc}")
        return []


def retrieve_context(state: AgentState) -> dict:
    """
    Query Milvus for curriculum chunks relevant to the current lesson step.

    Returns:
        {"step_context": list[dict]} — empty list on failure.
    """
    sub_intent = state.get("sub_intent", "")
    active_topic = state.get("active_topic", "")
    lesson_plan = state.get("lesson_plan", [])
    current_step = state.get("current_step", 0)
    student_profile = state.get("student_profile", {})

    # Choose query text based on intent
    if sub_intent == "new_topic":
        query_text = active_topic
    else:
        query_text = lesson_plan[current_step] if current_step < len(lesson_plan) else active_topic

    logger.info(f"retrieve_context: querying '{query_text}'")

    try:
        vdb = _get_vector_db()
        content, sources = vdb.get_similar_documents(
            text=query_text,
            top_k=3,
            board=student_profile.get("board", "CBSE"),
            grade=student_profile.get("grade", 10),
        )
        step_context = [
            {
                "concept": query_text,
                "explanation": content,
                "analogies": "",
                "chapter": "",
                "subject": student_profile.get("subject", "Mathematics"),
                "doc_id": sources[0] if sources else "",
            }
        ]
        logger.info(f"retrieve_context: got {len(step_context)} chunk(s)")
        return {"step_context": step_context}

    except Exception as exc:
        logger.error(f"retrieve_context error: {exc}")
        return {"step_context": []}
