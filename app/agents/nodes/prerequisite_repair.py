import logging

from app.agents.state import AgentState
from app.agents.nodes._llm import invoke
from app.agents.concept_graph.schema import ConceptNode
from app.agents.world_model.schema import StudentWorldModel
from app.agents.vi_prompts import build_prereq_repair_prompt

logger = logging.getLogger(__name__)


def run(state: AgentState) -> dict:
    """
    Student is missing a prerequisite.
    Teach it first, then bridge back to the original concept.
    The concept node was already loaded by the pedagogical_reasoner.
    """
    node_dict = state.get("concept_node", {})
    node = ConceptNode(**{k: node_dict.get(k, v.default if hasattr(v, "default") else None)
                          for k, v in ConceptNode.__dataclass_fields__.items()}) if node_dict else _stub_node()

    analogy = state.get("chosen_analogy", node.common_analogies[0]["text"] if node.common_analogies else "")
    model_data = state.get("world_model", {})

    # Find what was ORIGINALLY being taught (the blocked concept)
    path = model_data.get("current_path", [])
    path_pos = model_data.get("current_path_pos", 0)
    original_concept_id = path[path_pos] if path and path_pos < len(path) else state.get("query", "")

    # Get original concept name
    try:
        from app.agents.concept_graph import store as concept_store
        original_name = concept_store.get_name(original_concept_id)
    except Exception:
        original_name = original_concept_id.split(".")[-1].replace("_", " ").title() if "." in original_concept_id else original_concept_id

    prompt = build_prereq_repair_prompt(state, node, analogy, original_name)
    response = invoke(prompt)

    logger.info(f"prerequisite_repair: teaching '{node.concept_id}' before '{original_concept_id}'")
    return {"agent_output": response or _fallback(node.name, original_name)}


def _stub_node() -> ConceptNode:
    return ConceptNode(
        concept_id="unknown",
        name="this concept",
        subject="general",
        grade_levels=[],
        boards=[],
        common_analogies=[{"text": "everyday experience", "effectiveness": 0.5}],
        socratic_questions=["Can you explain this in your own words?"],
    )


def _fallback(prereq_name: str, original_name: str) -> str:
    return (
        f"Before we get to {original_name}, there is one foundational idea "
        f"that will make everything click — {prereq_name}. "
        f"Once we have this sorted, {original_name} will feel much more natural. "
        "What do you already know about this?"
    )
