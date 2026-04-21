import logging

from app.agents.state import AgentState
from app.agents.nodes._llm import invoke
from app.agents.vi_prompts import build_disengage_prompt

logger = logging.getLogger(__name__)


def run(state: AgentState) -> dict:
    """
    Fatigue signal detected OR lesson complete.
    Pivot gracefully — celebrate, summarise, shift to lighter activity.
    """
    model_data = state.get("world_model", {})
    is_lesson_complete = state.get("teaching_mode") == "lesson_complete"

    # What was covered in this session
    current_path = model_data.get("current_path", [])
    known_this_session = []
    for edge in model_data.get("knowledge_edges", []):
        edge_id = edge.get("concept_id") if isinstance(edge, dict) else getattr(edge, "concept_id", "")
        edge_state = edge.get("state") if isinstance(edge, dict) else getattr(edge, "state", "")
        edge_name = edge.get("concept_name") if isinstance(edge, dict) else getattr(edge, "concept_name", "")
        if edge_state == "known" and edge_id in current_path:
            known_this_session.append(edge_name or edge_id)

    prompt = build_disengage_prompt(state, known_this_session, is_lesson_complete)
    response = invoke(prompt)

    # Reset fatigue after disengage
    existing_delta = state.get("wm_delta") or {}
    existing_delta["fatigue_delta"] = -0.3

    logger.info(f"disengage: lesson_complete={is_lesson_complete}, covered={known_this_session}")
    return {
        "agent_output": response or _fallback(is_lesson_complete, known_this_session),
        "wm_delta": existing_delta,
    }


def _fallback(is_complete: bool, covered: list) -> str:
    if is_complete:
        covered_str = ", ".join(covered[:3]) if covered else "everything we set out to cover"
        return (
            f"That is a wrap on today's lesson — and you did brilliantly. "
            f"We covered {covered_str}. "
            "Think about how that connects to what you see around you every day. "
            "What shall we explore next time?"
        )
    return (
        "Let us take a short breather. We have been working hard and the brain needs "
        "a moment to absorb things. Tell me — is there something completely random "
        "you have been curious about lately? Anything at all."
    )
