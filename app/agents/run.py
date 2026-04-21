"""
Entry point for the reimagined vijayebhav agent.

Signature is identical to the original core_agent.run_agent() so no
router changes are required. Called via asyncio.to_thread() from FastAPI.
"""
import logging

from app.agents.graph import get_graph

logger = logging.getLogger(__name__)


def run_agent(
    user: dict,
    query: str,
    session_id: str,
    language_code: str = "en-IN",
    extra_tools: list = None,
) -> str:
    """
    Run the reimagined pedagogical agent.

    Args:
        user:         MongoDB user document.
        query:        Student's text input (post STT if from voice).
        session_id:   LangGraph thread_id for state persistence.
        language_code: Detected language from Sarvam STT.
        extra_tools:  Per-call tool overrides (not persisted).

    Returns:
        Plain-text response string ready for TTS.
    """
    try:
        logger.info(f"[reimagined] run_agent user={user.get('_id')} query={query[:60]!r}")

        graph = get_graph()

        initial_state = {
            "query": query,
            "session_id": session_id,
            "user": user,
            "messages": [],
            "language_code": language_code,
            "active_tools": extra_tools or [],
            "tool_results": {},
            # Fields below will be populated by pedagogical_reasoner
            "world_model": {},
            "world_model_summary": "",
            "teaching_mode": "advance",
            "target_concept_id": "",
            "target_concept_name": "",
            "reasoning_trace": "",
            "concept_node": {},
            "chosen_analogy": "",
            "chosen_question": "",
            "retrieved_chunks": [],
            "wm_delta": {},
            "agent_output": "",
            "last_response": "",
            "difficulty_level": "Intermediate",
            "response_type": "Detailed",
            "learning_mode": "Normal",
        }

        config = {"configurable": {"thread_id": session_id}}
        final = graph.invoke(initial_state, config=config)

        response = final.get("last_response", "")
        if not response:
            response = "I am here and ready to help you learn. What would you like to explore?"

        logger.info(f"[reimagined] completed — response length={len(response)}")
        return response

    except Exception as e:
        logger.error(f"[reimagined] run_agent error: {e}", exc_info=True)
        raise
