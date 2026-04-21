import logging

from app.agents.state import AgentState
from app.agents.nodes._llm import invoke
from app.agents.concept_graph.schema import ConceptNode
from app.agents.vi_prompts import build_advance_prompt

logger = logging.getLogger(__name__)


def run(state: AgentState) -> dict:
    """
    Standard teaching: explain concept with analogy + Socratic question.
    Uses curiosity map to find a motivating hook if available.
    """
    node_dict = state.get("concept_node", {})
    node = _dict_to_node(node_dict)
    model_data = state.get("world_model", {})

    analogy = state.get("chosen_analogy", "")
    chunks = state.get("retrieved_chunks", [])

    # Board-specific example
    user = state.get("user", {})
    board = user.get("board", "CBSE")
    board_example = node.board_examples.get(board, "") or next(iter(node.board_examples.values()), "")

    # Curiosity bridge — if student's curiosity map overlaps related_ids
    curiosity_hook = ""
    for curiosity_topic in model_data.get("curiosity_topics", [])[:2]:
        for related_id in (node.related_ids or []):
            if curiosity_topic.lower() in related_id.lower():
                curiosity_hook = curiosity_topic
                break
        if curiosity_hook:
            break

    # Get active tools if any
    active_tools = state.get("active_tools", [])
    tools = _get_active_tools(active_tools)

    prompt = build_advance_prompt(state, node, analogy, board_example, curiosity_hook, chunks)

    if tools:
        response = invoke(prompt)  # tool invocation handled via response_composer in future
    else:
        response = invoke(prompt)

    logger.info(f"advance: teaching '{node.concept_id}' with analogy '{analogy[:40]}'")
    return {"agent_output": response or _fallback(node.name)}


def _dict_to_node(d: dict) -> ConceptNode:
    if not d:
        return ConceptNode(
            concept_id="unknown", name="this concept",
            subject="general", grade_levels=[], boards=[],
            board_examples={}, common_analogies=[],
            related_ids=[], socratic_questions=[],
        )
    defaults = {k: (v.default if hasattr(v, "default") else None)
                for k, v in ConceptNode.__dataclass_fields__.items()}
    defaults.update({k: v for k, v in d.items() if k in defaults})
    return ConceptNode(**defaults)


def _get_active_tools(tool_names: list) -> list:
    try:
        from app.agents.tools.base import get_tool
        return [get_tool(name) for name in tool_names if get_tool(name)]
    except Exception:
        return []


def _fallback(concept_name: str) -> str:
    return (
        f"Let us explore {concept_name} together. "
        "The best way to understand this is to start with something you already know. "
        "Think of a time when you noticed something similar in everyday life. "
        "What comes to mind?"
    )
