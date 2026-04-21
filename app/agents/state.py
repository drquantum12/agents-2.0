from typing import TypedDict, Literal, Optional


class AgentState(TypedDict):
    # ── INPUT ───────────────────────────────────────────────
    query: str
    session_id: str
    user: dict               # from MongoDB users collection
    messages: list           # LangGraph message history
    language_code: str       # from SarvamAI STT (default 'en-IN')

    # ── DEVICE CONFIG ───────────────────────────────────────
    difficulty_level: Literal["Beginner", "Intermediate", "Advanced"]
    response_type: Literal["Concise", "Detailed"]
    learning_mode: Literal["Normal", "Strict"]

    # ── WORLD MODEL ─────────────────────────────────────────
    world_model: dict        # serialised StudentWorldModel
    world_model_summary: str  # ≤5 sentences for prompt injection

    # ── PEDAGOGICAL REASONING ──────────────────────────────
    teaching_mode: Literal[
        "prerequisite_repair",
        "re_analogise",
        "advance",
        "thread_resolve",
        "disengage",
        "lesson_complete",
    ]
    target_concept_id: str
    target_concept_name: str
    reasoning_trace: str     # why the reasoner chose this mode (debug only)

    # ── CONCEPT GRAPH CONTEXT ──────────────────────────────
    concept_node: dict       # full ConceptNode for target concept
    chosen_analogy: str      # picked from node.common_analogies
    chosen_question: str     # picked from node.socratic_questions
    retrieved_chunks: list   # Milvus RAG for this concept

    # ── WORLD MODEL DELTA ───────────────────────────────────
    # Populated by response_composer, applied by world model updater
    wm_delta: dict           # serialised WorldModelDelta

    # ── OUTPUT ─────────────────────────────────────────────
    agent_output: str        # raw from teaching mode node
    last_response: str       # final TTS-ready text

    # ── TOOLS ──────────────────────────────────────────────
    active_tools: list
    tool_results: dict
