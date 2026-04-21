"""
LangGraph StateGraph for the reimagined vijayebhav agent.

Topology:
  pedagogical_reasoner
      ↓ (conditional)
  prerequisite_repair | re_analogise | advance | thread_resolve | disengage
      ↓ (all → composer)
  response_composer
      ↓
  END
"""
import logging

from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.nodes import (
    pedagogical_reasoner,
    prerequisite_repair,
    re_analogise,
    advance,
    thread_resolve,
    disengage,
    response_composer,
)
from app.agents.memory.mongo_saver import get_mongo_saver

logger = logging.getLogger(__name__)

_compiled_graph = None


def route_from_reasoner(state: AgentState) -> str:
    """
    Pure routing function — reads teaching_mode set by pedagogical_reasoner.
    lesson_complete is handled gracefully via disengage.
    """
    mode = state.get("teaching_mode", "advance")
    if mode == "lesson_complete":
        return "disengage"
    valid = {"prerequisite_repair", "re_analogise", "advance", "thread_resolve", "disengage"}
    return mode if mode in valid else "advance"


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # ── NODES ───────────────────────────────────────────────
    g.add_node("pedagogical_reasoner", pedagogical_reasoner.run)
    g.add_node("prerequisite_repair", prerequisite_repair.run)
    g.add_node("re_analogise", re_analogise.run)
    g.add_node("advance", advance.run)
    g.add_node("thread_resolve", thread_resolve.run)
    g.add_node("disengage", disengage.run)
    g.add_node("response_composer", response_composer.run)

    # ── ENTRY ───────────────────────────────────────────────
    g.set_entry_point("pedagogical_reasoner")

    # ── CONDITIONAL ROUTING ─────────────────────────────────
    g.add_conditional_edges(
        "pedagogical_reasoner",
        route_from_reasoner,
        {
            "prerequisite_repair": "prerequisite_repair",
            "re_analogise": "re_analogise",
            "advance": "advance",
            "thread_resolve": "thread_resolve",
            "disengage": "disengage",
        },
    )

    # ── ALL TEACHING MODES → COMPOSER ───────────────────────
    for node_name in ("prerequisite_repair", "re_analogise", "advance",
                      "thread_resolve", "disengage"):
        g.add_edge(node_name, "response_composer")

    g.add_edge("response_composer", END)

    return g.compile(checkpointer=get_mongo_saver())


def get_graph():
    """Return the compiled graph singleton. Built once at startup."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
        logger.info("Reimagined agent graph compiled and cached.")
    return _compiled_graph
