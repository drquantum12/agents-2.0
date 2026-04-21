import logging

from app.agents.state import AgentState
from app.agents.nodes._llm import invoke
from app.agents.vi_prompts import build_thread_resolve_prompt

logger = logging.getLogger(__name__)


def run(state: AgentState) -> dict:
    """
    Surface the oldest unresolved question from the student's open threads.
    This is the feature that makes students feel genuinely known.
    """
    model_data = state.get("world_model", {})
    open_threads = [
        t for t in model_data.get("open_threads", [])
        if not (t.get("resolved") if isinstance(t, dict) else getattr(t, "resolved", False))
    ]

    if not open_threads:
        logger.info("thread_resolve: no open threads — falling back to advance")
        from app.agents.nodes import advance
        return advance.run(state)

    thread = open_threads[0]  # oldest first
    thread_question = thread.get("question") if isinstance(thread, dict) else getattr(thread, "question", str(thread))

    prompt = build_thread_resolve_prompt(state, thread if not isinstance(thread, dict) else _dict_to_thread(thread))
    response = invoke(prompt)

    # Mark thread as resolved in wm_delta
    existing_delta = state.get("wm_delta") or {}
    resolved_ids = list(existing_delta.get("resolved_thread_ids", []))
    resolved_ids.append(thread_question)

    logger.info(f"thread_resolve: surfacing thread '{thread_question[:60]}'")
    return {
        "agent_output": response or _fallback(thread_question),
        "wm_delta": {**existing_delta, "resolved_thread_ids": resolved_ids},
    }


class _ThreadProxy:
    def __init__(self, question: str, raised_at):
        self.question = question
        self.raised_at = raised_at
        self.resolved = False


def _dict_to_thread(d: dict) -> _ThreadProxy:
    return _ThreadProxy(
        question=d.get("question", ""),
        raised_at=d.get("raised_at", ""),
    )


def _fallback(question: str) -> str:
    return (
        f"Actually, there is something you touched on earlier that I want to come back to. "
        f"You asked: {question}. "
        "I think we are at exactly the right point now to give that question a proper answer. "
        "Does that close the loop for you?"
    )
