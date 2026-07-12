"""
tools/rag_tool.py
─────────────────────────────────────────────
retrieve_curriculum_context — RAG lookup against Milvus.

Automatically filters by the user's board and grade (read from
_user_context_var) so every result is syllabus-accurate.

Signals "searching" to the device before the embedding + Milvus call
so the user sees the data-scan animation during retrieval.

Graceful fallback: if Milvus is unreachable or finds nothing, returns ""
so the agent can continue with general-knowledge answers.
"""
import logging

from langchain_core.tools import tool
from app.db_utility.vector_db import VectorDB

from .context import _user_context_var
from .device_tools import _do_signal

logger = logging.getLogger(__name__)

# Module-level singleton — Milvus client initialisation is expensive
_vdb: VectorDB | None = None


def _get_vdb() -> VectorDB:
    global _vdb
    if _vdb is None:
        _vdb = VectorDB()
    return _vdb


@tool
def retrieve_curriculum_context(
    query:   str,
    subject: str = "",
    chapter: str = "",
) -> str:
    """
    Retrieve relevant curriculum content from the knowledge base before
    explaining any academic concept. This ensures your explanation is
    grounded in the student's actual syllabus (board and grade are applied
    automatically — you do not need to pass them).

    Use this BEFORE explaining any academic topic. If it returns content,
    use that content as the primary basis for your explanation. If it
    returns empty, fall back to general knowledge.

    Args:
        query:   The concept or topic to look up.
                 Examples: "photosynthesis", "Newton's second law", "quadratic equations"
        subject: Optional — narrows the search to a curriculum subject.
                 Examples: "Science", "Mathematics", "History", "English"
        chapter: Optional — narrows further by chapter name.
                 Examples: "Chemical Reactions", "Trigonometry", "The French Revolution"

    Returns curriculum explanations and analogies as a context string,
    or an empty string if nothing relevant was found.
    """
    _do_signal("searching")

    user_ctx = _user_context_var.get() or {}
    board    = user_ctx.get("board") or None
    grade    = user_ctx.get("grade") or None

    # grade may come through as "10" (string) — Milvus filter expects int
    grade_int: int | None = None
    if grade is not None:
        try:
            grade_int = int(str(grade))
        except (ValueError, TypeError):
            grade_int = None

    try:
        vdb = _get_vdb()
        context_text, sources = vdb.get_similar_documents(
            text    = query,
            top_k   = 3,
            board   = board,
            grade   = grade_int,
            subject = subject or None,
            chapter = chapter or None,
        )

        if not context_text or not context_text.strip():
            logger.info(
                "retrieve_curriculum_context: no results for '%s' "
                "(board=%s, grade=%s, subject=%s)",
                query[:60], board, grade, subject,
            )
            return ""

        source_labels = "; ".join(sources[:3]) if sources else "curriculum knowledge base"
        result = f"[Curriculum context — {source_labels}]\n{context_text}"
        logger.info(
            "retrieve_curriculum_context: %d chars for '%s'",
            len(context_text), query[:60],
        )
        return result

    except Exception as exc:
        # Never hard-fail — fall back to general knowledge silently
        logger.error("retrieve_curriculum_context error: %s", exc)
        return ""
