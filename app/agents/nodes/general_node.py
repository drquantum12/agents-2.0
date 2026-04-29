"""
general_node — companion mode response generator.

Also handles the stop_teacher transition: resets all lesson state and adds
a farewell note to the system prompt so the response acknowledges the lesson ending.
"""

import logging

from langchain_core.messages import AIMessage, SystemMessage

from app.agents.llm import llm
from app.agents.prompts.companion import build_companion_system_prompt
from app.agents.routing import is_no
from app.agents.state.schema import AgentState

logger = logging.getLogger(__name__)


def general_node(state: AgentState) -> dict:
    """
    Generate a friendly companion response.

    Handles:
      - Plain general chat
      - stop_teacher: resets lesson state, adds farewell note to prompt
      - Decline after awaiting_lesson_confirmation
    """
    messages = state.get("messages", [])
    student_profile = state.get("student_profile", {})
    route = state.get("route", "")

    logger.info(f"general_node: route={route}")

    farewell_note = ""
    reset_state: dict = {}

    # ------------------------------------------------------------------
    # Transitioning out of teacher mode
    # ------------------------------------------------------------------
    if route == "stop_teacher" and state.get("mode") == "teacher":
        active_topic = state.get("active_topic", "")
        current_step = state.get("current_step", 0)
        lesson_plan = state.get("lesson_plan", [])
        farewell_note = (
            f"(Note: student ended lesson on '{active_topic}' "
            f"at step {current_step + 1} of {len(lesson_plan)})"
        )
        reset_state = {
            "mode": "general",
            "active_topic": None,
            "lesson_plan": [],
            "current_step": 0,
            "step_context": [],
            "pending_resume": False,
            "awaiting_lesson_confirmation": False,
            "pending_topic": None,
        }

    # ------------------------------------------------------------------
    # Close lesson-offer state on explicit decline
    # ------------------------------------------------------------------
    if state.get("awaiting_lesson_confirmation") and is_no(
        messages[-1].content if messages else ""
    ):
        reset_state.update({"awaiting_lesson_confirmation": False, "pending_topic": None})

    # Pass pending_topic so the companion knows to offer a lesson on that topic
    pending_topic = state.get("pending_topic") or ""
    system_prompt = build_companion_system_prompt(student_profile, farewell_note, pending_topic=pending_topic)

    try:
        response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
        return {"messages": [AIMessage(content=response.content)], **reset_state}
    except Exception as exc:
        logger.error(f"general_node error: {exc}")
        return {
            "messages": [AIMessage(content="I'm here to chat! What's on your mind?")],
            **reset_state,
        }
