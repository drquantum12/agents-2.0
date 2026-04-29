"""
LangGraph Companion Agent v3 — public entry point.

All logic is split across focused submodules:
  app.agents.state/   — AgentState, MongoDB, student profile I/O
  app.agents.routing/ — rule-based pattern matching
  app.agents.prompts/ — prompt builder functions (+ legacy prompts)
  app.agents.nodes/   — one file per LangGraph node
  app.agents.graph/   — StateGraph compilation and singleton cache

Callers (e.g. app/routers/agent.py) only need:
  from app.agents.core_agent import run_agent
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.graph import get_agent
from app.agents.state import (
    _sanitize_for_checkpoint,
    load_student_profile,
    save_student_profile,
)

logger = logging.getLogger(__name__)


def run_agent(user: dict, query: str, session_id: str) -> str:
    """
    Run the companion+mentor agent for one turn.

    Args:
        user:       User document dict — must contain '_id' or 'id'.
        query:      The student's message text.
        session_id: Used as the checkpointer thread_id; links turns into one session.

    Returns:
        The agent's text response.
    """
    try:
        user_id = str(user.get("_id", user.get("id", "unknown_user")))
        query_text = (query or "").strip() or "hi"
        logger.info(f"run_agent: user={user_id}, query='{query_text[:60]}'")

        student_profile = load_student_profile(user_id)
        config = {"configurable": {"thread_id": session_id}}
        agent = get_agent()

        # Only pass per-turn inputs. All other fields (mode, lesson_plan,
        # current_step, active_topic, etc.) are restored from the checkpointer
        # so they survive across turns. Passing them here would override the
        # checkpointed values and reset lesson state every turn.
        input_state = {
            "messages": [HumanMessage(content=query_text)],
            "user_id": user_id,
            "student_profile": _sanitize_for_checkpoint(student_profile),
        }

        result_state = agent.invoke(input_state, config=config)

        # Persist profile if any node flagged a change
        if result_state.get("world_model_dirty"):
            save_student_profile(
                user_id,
                _sanitize_for_checkpoint(result_state.get("student_profile", student_profile)),
            )

        # Extract the last AI message
        ai_messages = [m for m in result_state.get("messages", []) if isinstance(m, AIMessage)]
        response = ai_messages[-1].content if ai_messages else "I'm here to help!"

        # Strip any leaked STEP_VERDICT tags
        if "STEP_VERDICT:" in response:
            response = response.rsplit("STEP_VERDICT:", 1)[0].strip()

        logger.info("run_agent completed successfully")
        return response

    except Exception as exc:
        logger.error(f"run_agent error: {exc}", exc_info=True)
        raise
