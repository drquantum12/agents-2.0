"""
Graph builder — compiles the LangGraph StateGraph and caches the result.

Node layout:
  START → intent_router → {retrieve_context → teacher_node}
                        → general_node
                        → teacher_node
  general_node  → END
  teacher_node  → END
"""

import logging

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import general_node, intent_router, retrieve_context, teacher_node
from app.agents.state.db import get_checkpointer
from app.agents.state.schema import AgentState

logger = logging.getLogger(__name__)

_cached_agent = None


def _route_after_intent(state: AgentState) -> str:
    """Conditional edge: decide next node after intent_router."""
    if state.get("sub_intent") in ["new_topic", "step_complete"]:
        return "retrieve_context"
    if state.get("route") in ["general", "stop_teacher"]:
        return "general_node"
    return "teacher_node"


def build_agent():
    """Compile and return the LangGraph agent."""
    workflow = StateGraph(AgentState)

    workflow.add_node("intent_router", intent_router)
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("general_node", general_node)
    workflow.add_node("teacher_node", teacher_node)

    workflow.add_edge(START, "intent_router")

    workflow.add_conditional_edges(
        "intent_router",
        _route_after_intent,
        {
            "retrieve_context": "retrieve_context",
            "general_node": "general_node",
            "teacher_node": "teacher_node",
        },
    )

    workflow.add_edge("retrieve_context", "teacher_node")
    workflow.add_edge("general_node", END)
    workflow.add_edge("teacher_node", END)

    app = workflow.compile(checkpointer=get_checkpointer())
    logger.info("Agent graph compiled successfully")
    return app


def get_agent():
    """Return the cached compiled agent, building it on first call."""
    global _cached_agent
    if _cached_agent is None:
        _cached_agent = build_agent()
        logger.info("Agent graph built and cached")
    return _cached_agent
