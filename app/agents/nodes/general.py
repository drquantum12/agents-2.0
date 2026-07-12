"""
nodes/general.py
─────────────────────────────────────────────
Handles GENERAL intent — conversational, motivational, or meta queries
that don't fit explanation or web search.

Examples:
  "Hi, how are you?"
  "What topics can you teach me?"
  "I'm feeling stuck / frustrated"
  "That was a great explanation!"
"""

import logging
from langchain_core.messages import AIMessage
from app.agents.llm import llm

from ..state import AgentState
from ..prompts.general import build_general_prompt

logger = logging.getLogger(__name__)


def general_node(state: AgentState) -> dict:
    """
    Produces a warm, conversational response.
    If a lesson is active, may gently nudge the user back to it.
    """
    prompt   = build_general_prompt(state)
    response = llm.invoke(prompt).content.strip()

    logger.info("General node responded to: %s", state.get("query", "")[:60])
    return {
        "messages":           [AIMessage(content=response)],
        "awaiting_user_input": False,
    }
