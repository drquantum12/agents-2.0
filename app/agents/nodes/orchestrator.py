"""
nodes/orchestrator.py
─────────────────────────────────────────────
Entry-point node. Classifies the user's intent using the LLM and writes
`intent` into the state. Does NOT produce any user-facing message —
pure routing decision.

Downstream conditional edge uses state["intent"] to pick the next node:
  EXPLANATION       → teacher
  GENERAL           → general
  WEB_SEARCH        → web_search
  CONFIRM_WITH_USER → user_confirmation
"""

import logging
from langchain_core.messages import HumanMessage
from app.agents.llm import classifier_llm

from ..state import AgentState
from ..prompts.classifier import build_classifier_prompt

logger = logging.getLogger(__name__)


VALID_INTENTS = frozenset({
    "EXPLANATION",
    "GENERAL",
    "WEB_SEARCH",
    "CONFIRM_WITH_USER",
})


def orchestrator_node(state: AgentState) -> dict:
    """
    Classifies user intent and returns `{"intent": <label>}`.

    Falls back to "GENERAL" if the LLM returns anything unexpected.
    Also appends the user's query as a HumanMessage to the conversation.
    """
    query = state.get("query", "").strip()

    # Build the classification prompt from the full agent state
    prompt = build_classifier_prompt(state)

    try:
        response = classifier_llm.invoke(prompt)
        raw = response.content.strip().upper()
        # Strip punctuation / whitespace artefacts
        intent = raw.strip(".:,;!?\"' ")
    except Exception as exc:
        logger.error("Orchestrator LLM call failed: %s", exc)
        intent = "GENERAL"

    if intent not in VALID_INTENTS:
        logger.warning("Unexpected intent '%s' — defaulting to GENERAL", intent)
        intent = "GENERAL"

    logger.info("Intent classified: %s  |  query: %s", intent, query[:80])

    return {
        # Append the user turn to messages so subsequent nodes see it
        "messages": [HumanMessage(content=query)],
        "intent":   intent,
    }
