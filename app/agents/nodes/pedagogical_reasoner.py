import logging

from app.agents.state import AgentState
from app.agents.nodes._llm import invoke_with_tool
from app.agents.schemas import PedagogicalReasoningSchema
from app.agents.world_model import store as wm_store
from app.agents.world_model.summariser import summarise_for_prompt
from app.agents.concept_graph import store as concept_store
from app.agents.concept_graph.traversal import compute_next_concept
from app.agents.memory.semantic_cache import SemanticCache
from app.agents.vi_prompts import build_reasoner_prompt

logger = logging.getLogger(__name__)
_cache = SemanticCache()


def run(state: AgentState) -> dict:
    """
    The most important node. Runs on every call.
    Loads the full student world model, runs concept graph traversal,
    and sets teaching_mode + target_concept in state.
    Does NOT produce a response string.
    """
    user = state.get("user", {})
    user_id = str(user.get("_id", ""))

    # 1. Load device config → personality params
    try:
        from app.db_utility.mongo_db import mongo_db
        config = mongo_db["device_config"].find_one({"user_id": user_id}) or {}
    except Exception:
        config = {}

    difficulty_level = config.get("difficulty_level", "Intermediate")
    response_type = config.get("response_type", "Detailed")
    learning_mode = config.get("learning_mode", "Normal")

    # 2. Load Student World Model
    model = wm_store.load(user_id)
    world_model_dict = _model_to_dict(model)
    world_model_summary = summarise_for_prompt(model)

    updates: dict = {
        "difficulty_level": difficulty_level,
        "response_type": response_type,
        "learning_mode": learning_mode,
        "world_model": world_model_dict,
        "world_model_summary": world_model_summary,
    }

    # 3. Semantic cache check — skip full reasoning on near-identical queries
    cached = _cache.lookup(state.get("query", ""))
    if cached:
        logger.info("Semantic cache hit — routing directly to composer")
        updates["agent_output"] = cached["response"]
        updates["teaching_mode"] = cached["mode"]
        updates["target_concept_id"] = model.current_path[model.current_path_pos] if model.current_path else ""
        return updates

    # 4. Partial state for prompt building
    partial = {**state, **updates}

    # 5. LLM — Pedagogical reasoning
    prompt = build_reasoner_prompt(partial)
    result = invoke_with_tool(prompt, PedagogicalReasoningSchema)

    if result is None:
        # Safe fallback
        updates["teaching_mode"] = "advance"
        updates["target_concept_id"] = model.current_path[model.current_path_pos] if model.current_path else state.get("query", "")
        updates["reasoning_trace"] = "Fallback: LLM tool call failed."
        _fill_concept_context(updates, updates["target_concept_id"], model)
        return updates

    updates["teaching_mode"] = result.teaching_mode
    updates["target_concept_id"] = result.target_concept_id
    updates["reasoning_trace"] = result.reasoning_trace

    # Seed initial wm_delta from reasoner observations
    wm_delta: dict = {}
    if result.concept_state_update:
        wm_delta["concept_state_updates"] = result.concept_state_update
    if result.detected_student_analogy and updates["target_concept_id"]:
        wm_delta["student_analogy"] = (updates["target_concept_id"], result.detected_student_analogy)
    if result.new_open_thread:
        wm_delta["new_open_thread"] = result.new_open_thread
    if result.curiosity_signal:
        wm_delta["curiosity_signal"] = result.curiosity_signal
    if result.fatigue_delta != 0.0:
        wm_delta["fatigue_delta"] = result.fatigue_delta
    updates["wm_delta"] = wm_delta

    # 6. Load concept node from Milvus/store
    _fill_concept_context(updates, result.target_concept_id, model)

    # 7. RAG — retrieve supporting chunks for concept
    try:
        from app.db_utility.vector_db import VectorDB
        vdb = VectorDB()
        node_name = updates.get("target_concept_name", result.target_concept_id)
        board = user.get("board")
        grade = user.get("grade")
        chunks = vdb.get_similar_documents(
            text=node_name, top_k=3, board=board, grade=grade
        )
        updates["retrieved_chunks"] = [c.get("content", "") for c in chunks] if chunks else []
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        updates["retrieved_chunks"] = []

    # 8. Override: run graph traversal if in active lesson
    if model.current_topic and model.current_path:
        try:
            current_id = model.current_path[model.current_path_pos]
            target_id = model.current_path[-1]
            next_id, computed_mode = compute_next_concept(current_id, target_id, model)
            updates["teaching_mode"] = computed_mode
            updates["target_concept_id"] = next_id
            if next_id != current_id:
                _fill_concept_context(updates, next_id, model)
        except Exception as e:
            logger.warning(f"Graph traversal failed: {e}")

    return updates


def _fill_concept_context(updates: dict, concept_id: str, model) -> None:
    """Load the ConceptNode and pick analogy/question into updates dict."""
    node = concept_store.get(concept_id)
    updates["concept_node"] = _node_to_dict(node)
    updates["target_concept_name"] = node.name

    # Pick analogy not yet tried for this student
    tried = set()
    for f in model.friction_log:
        if hasattr(f, "concept_id") and f.concept_id == concept_id:
            tried = set(f.analogies_tried)
        elif isinstance(f, dict) and f.get("concept_id") == concept_id:
            tried = set(f.get("analogies_tried", []))

    available = [a for a in node.common_analogies if a.get("text", "") not in tried]
    if available:
        updates["chosen_analogy"] = available[0]["text"]
    elif node.common_analogies:
        updates["chosen_analogy"] = node.common_analogies[0]["text"]
    else:
        updates["chosen_analogy"] = "everyday experience"

    updates["chosen_question"] = node.socratic_questions[0] if node.socratic_questions else ""


def _model_to_dict(model) -> dict:
    import dataclasses
    def to_dict(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {k: to_dict(v) for k, v in dataclasses.asdict(obj).items()}
        if isinstance(obj, list):
            return [to_dict(i) for i in obj]
        if isinstance(obj, dict):
            return {k: to_dict(v) for k, v in obj.items()}
        return obj
    return to_dict(model)


def _node_to_dict(node) -> dict:
    import dataclasses
    if dataclasses.is_dataclass(node):
        return dataclasses.asdict(node)
    return {}
