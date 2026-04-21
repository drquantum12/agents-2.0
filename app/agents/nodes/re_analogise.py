import logging

from app.agents.state import AgentState
from app.agents.nodes._llm import invoke
from app.agents.concept_graph.schema import ConceptNode
from app.agents.vi_prompts import build_re_analogise_prompt

logger = logging.getLogger(__name__)


def run(state: AgentState) -> dict:
    """
    Student has failed on same concept 2+ times.
    Use a fresh analogy — ideally the student's own if they offered one.
    """
    node_dict = state.get("concept_node", {})
    node = _dict_to_node(node_dict)

    model_data = state.get("world_model", {})

    # Check for student's own analogy first
    student_analogy = None
    for f in model_data.get("friction_log", []):
        cid = f.get("concept_id") if isinstance(f, dict) else getattr(f, "concept_id", None)
        if cid == node.concept_id:
            student_analogy = f.get("student_analogy") if isinstance(f, dict) else getattr(f, "student_analogy", None)
            break

    chosen_analogy = state.get("chosen_analogy", "")

    prompt = build_re_analogise_prompt(state, node, chosen_analogy, student_analogy)
    response = invoke(prompt)

    logger.info(f"re_analogise: fresh approach for '{node.concept_id}'")
    return {"agent_output": response or _fallback(node.name)}


def _dict_to_node(d: dict) -> ConceptNode:
    if not d:
        return ConceptNode(
            concept_id="unknown", name="this concept",
            subject="general", grade_levels=[], boards=[],
            common_analogies=[{"text": "everyday experience", "effectiveness": 0.5}],
        )
    return ConceptNode(**{k: d.get(k, v.default if hasattr(v, "default") else None)
                          for k, v in ConceptNode.__dataclass_fields__.items()})


def _fallback(concept_name: str) -> str:
    return (
        f"You are on the right track — {concept_name} is genuinely one of the trickier "
        "ideas to build intuition for. Let me try a completely different way of looking at it. "
        "Think about it this way: what happens when you try to change something that is "
        "already in motion? That resistance is the heart of what we are discussing. "
        "Does that framing feel different to you?"
    )
