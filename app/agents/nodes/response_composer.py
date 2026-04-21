import logging
import re

from app.agents.state import AgentState
from app.agents.nodes._llm import invoke
from app.agents.world_model.schema import StudentWorldModel
from app.agents.world_model.updater import WorldModelDelta, FrictionUpdate, apply_delta
from app.agents.world_model import store as wm_store
from app.agents.memory.semantic_cache import SemanticCache
from app.agents.vi_prompts import build_composer_prompt

logger = logging.getLogger(__name__)
_cache = SemanticCache()


def run(state: AgentState) -> dict:
    """
    Final node before END.
    1. Personality shell pass — refines tone and strips markdown.
    2. Applies world model delta.
    3. Writes response to semantic cache.
    4. Writes last_response (TTS-ready).
    """
    raw = state.get("agent_output", "")

    # 1. Personality refinement pass
    if raw:
        prompt = build_composer_prompt(state, raw)
        final = invoke(prompt)
        if not final:
            final = raw  # use raw if refinement fails
    else:
        final = _generic_fallback(state)

    # 2. Strip markdown symbols for TTS
    final = _strip_tts_symbols(final)

    # 3. Apply world model delta
    user_id = str(state.get("user", {}).get("_id", ""))
    if user_id:
        try:
            model = wm_store.load(user_id)
            delta = _build_delta(state)
            apply_delta(model, delta)
        except Exception as e:
            logger.warning(f"World model delta application failed: {e}")

    # 4. Store in semantic cache
    try:
        _cache.store(
            query=state.get("query", ""),
            response=final,
            mode=state.get("teaching_mode", "advance"),
        )
    except Exception as e:
        logger.warning(f"Cache store failed: {e}")

    return {"last_response": final}


def _build_delta(state: dict) -> WorldModelDelta:
    raw_delta = state.get("wm_delta") or {}

    # friction_update: only if teaching_mode is re_analogise
    friction_update = None
    if state.get("teaching_mode") == "re_analogise":
        analogy = state.get("chosen_analogy", "")
        concept_id = state.get("target_concept_id", "")
        if analogy and concept_id:
            friction_update = FrictionUpdate(concept_id=concept_id, analogy=analogy)

    # student_analogy from raw_delta
    student_analogy = raw_delta.get("student_analogy")
    if isinstance(student_analogy, list) and len(student_analogy) == 2:
        student_analogy = tuple(student_analogy)

    return WorldModelDelta(
        concept_state_updates=raw_delta.get("concept_state_updates", {}),
        friction_update=friction_update,
        new_open_thread=raw_delta.get("new_open_thread"),
        resolved_thread_ids=raw_delta.get("resolved_thread_ids", []),
        curiosity_signal=raw_delta.get("curiosity_signal"),
        fatigue_delta=raw_delta.get("fatigue_delta", 0.0),
        student_analogy=student_analogy,
    )


def _strip_tts_symbols(text: str) -> str:
    """Remove markdown symbols that would be read aloud awkwardly by TTS."""
    # Remove bold/italic markers
    text = re.sub(r"\*+", "", text)
    # Remove headers
    text = re.sub(r"#{1,6}\s*", "", text)
    # Remove bullet dashes at line start
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)
    # Remove numbered list markers
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Remove backticks
    text = re.sub(r"`+", "", text)
    # Collapse multiple newlines into space
    text = re.sub(r"\n{2,}", " ", text)
    text = text.replace("\n", " ")
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _generic_fallback(state: dict) -> str:
    name = state.get("user", {}).get("name", "there")
    return f"That is a great question, {name}. Let me think about the best way to explain this to you."
