import logging
from datetime import datetime, timezone

from app.db_utility.mongo_db import mongo_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Lazy singleton so the LLM is only imported when the filter is first called.
_filter_llm_with_tool = None


def _get_filter_llm():
    global _filter_llm_with_tool
    if _filter_llm_with_tool is None:
        from app.agents.llm import LLM
        from app.agents.schemas import MemoryFilterSchema
        _filter_llm_with_tool = LLM().get_llm().bind_tools(tools=[MemoryFilterSchema])
    return _filter_llm_with_tool


EMPTY_STUDENT_MEMORY = {
    "user_id": None,
    "updated_at": None,
    # topic_slug → { "state": "known"|"shaky"|"unseen", "last_seen": str, "attempts": int }
    "topic_states": {},
    # topic_slug → { "attempts": int, "last_fail": str }
    "friction": {},
    "interests": [],
    # [{ "question": str, "resolved": bool }]
    "open_threads": [],
    "current_topic": None,
    "lesson_subtopics": [],
    "lesson_step": 0,
    "awaiting_confirmation": False,
    # [{ "session_id": str, "date": str, "topics_touched": [...], "evaluations": [...] }]
    "session_log": [],
}


def get_student_memory(user_id: str) -> dict:
    """Load student memory from MongoDB. Returns empty template on first visit."""
    collection = mongo_db["student_memory"]
    mem = collection.find_one({"user_id": user_id}, {"_id": 0})
    if not mem:
        return {**EMPTY_STUDENT_MEMORY, "user_id": user_id}
    return mem


def build_memory_summary(mem: dict) -> str:
    """Compress student memory into ≤4 sentences for prompt injection."""
    parts = []

    shaky = [
        slug for slug, s in mem.get("topic_states", {}).items()
        if s.get("state") == "shaky"
    ][:3]
    if shaky:
        parts.append(f"Topics still shaky: {', '.join(shaky)}.")

    friction_items = sorted(
        mem.get("friction", {}).items(),
        key=lambda x: x[1].get("attempts", 0),
        reverse=True,
    )[:1]
    if friction_items:
        slug, f = friction_items[0]
        parts.append(f"{slug} has been explained {f['attempts']} times without success.")

    if mem.get("interests"):
        parts.append(f"Student shows interest in: {mem['interests'][0]}.")

    open_threads = [t for t in mem.get("open_threads", []) if not t.get("resolved")]
    if open_threads:
        parts.append(f"Unresolved question: '{open_threads[0]['question']}'")

    return " ".join(parts) if parts else "No prior learning history yet."


def filter_and_enrich_delta(delta: dict, state: dict) -> dict:
    """
    LLM quality gate (1 LLM call). Decides which signals from the current turn
    are worth persisting in the student's long-term memory.

    Adds to delta:
      "skip_topic_state_update": True  → evaluation was not substantive; skip topic_states write
      "new_interests": [str, ...]      → curiosity signals extracted this turn
      "new_open_thread": str | None    → unanswered question to revisit later

    Falls back to persisting everything if the LLM call fails.
    """
    from app.agents.prompts import MEMORY_FILTER_PROMPT

    query           = state.get("query", "")
    response_summary = (state.get("agent_output", "") or "")[:250]
    evaluation      = delta.get("evaluation")

    if evaluation:
        eval_summary = (
            f"Topic: {evaluation.get('topic_slug')}, "
            f"Correct: {evaluation.get('correct')}"
        )
    else:
        eval_summary = "None (no evaluation this turn)"

    try:
        prompt = MEMORY_FILTER_PROMPT.format(
            query=query,
            response_summary=response_summary,
            evaluation_summary=eval_summary,
        )
        response = _get_filter_llm().invoke(prompt)

        if response.tool_calls:
            data          = response.tool_calls[0]["args"]
            persist_eval  = data.get("persist_evaluation", True)
            new_interests = data.get("interests", [])
            open_thread   = data.get("open_thread")
            logger.info(
                f"Memory filter: persist_eval={persist_eval}, "
                f"interests={new_interests}, open_thread={open_thread!r}"
            )
        else:
            logger.warning("Memory filter: no tool call returned, persisting all")
            persist_eval, new_interests, open_thread = True, [], None

    except Exception as e:
        logger.warning(f"Memory filter LLM failed (persisting all): {e}")
        persist_eval, new_interests, open_thread = True, [], None

    # Apply filter decision: evaluation logged in session_log always,
    # but topic_states + friction only updated when substantive.
    if not persist_eval:
        delta["skip_topic_state_update"] = True

    if new_interests:
        delta["new_interests"] = new_interests
    if open_thread:
        delta["new_open_thread"] = open_thread

    return delta


def apply_memory_delta(mem: dict, delta: dict, state: dict) -> dict:
    """
    Pure Python. Zero LLM calls. Applies the (already-filtered) memory_delta
    onto the in-memory student doc.

    delta keys consumed here:
      "evaluation"              → { "topic_slug": str, "correct": bool, "step": int }
      "skip_topic_state_update" → bool (set by filter; suppresses topic_states/friction write)
      "lesson_started"          → { "topic_name": str, "topic_slug": str, "subtopics": list }
      "lesson_ended"            → bool
      "lesson_exited"           → bool
      "topics_touched"          → list[str]
      "new_interests"           → list[str]  (set by filter)
      "new_open_thread"         → str | None  (set by filter)
    """
    # --- Evaluation result → update topic_states + friction (if substantive) ---
    if delta.get("evaluation") and not delta.get("skip_topic_state_update"):
        ev   = delta["evaluation"]
        slug = ev.get("topic_slug")
        if slug:
            ts   = mem.setdefault("topic_states", {})
            prev = ts.get(slug, {"state": "unseen", "attempts": 0, "last_seen": None})

            if ev.get("correct"):
                prev["attempts"] = prev.get("attempts", 0) + 1
                prev["state"]    = "known" if prev["attempts"] >= 2 else "shaky"
            else:
                prev["state"] = "shaky"
                fr    = mem.setdefault("friction", {})
                entry = fr.setdefault(slug, {"attempts": 0})
                entry["attempts"] += 1
                entry["last_fail"] = _now_iso()

            prev["last_seen"] = _now_iso()
            ts[slug] = prev

    # --- Lesson started ---
    if delta.get("lesson_started"):
        ls = delta["lesson_started"]
        mem["current_topic"]    = ls.get("topic_name")
        mem["lesson_subtopics"] = ls.get("subtopics", [])
        mem["lesson_step"]      = 0
        mem["awaiting_confirmation"] = False

    # --- Lesson step advance ---
    mem["lesson_step"] = state.get("lesson_step", mem.get("lesson_step", 0))

    # --- Lesson completed ---
    if delta.get("lesson_ended"):
        mem["current_topic"]    = None
        mem["lesson_subtopics"] = []
        mem["lesson_step"]      = 0
        mem["awaiting_confirmation"] = False

    # --- Lesson exited early ---
    if delta.get("lesson_exited"):
        mem["current_topic"]    = None
        mem["lesson_subtopics"] = []
        mem["lesson_step"]      = 0
        mem["awaiting_confirmation"] = False

    # --- Interests (de-duplicated, capped at 20) ---
    new_interests = delta.get("new_interests", [])
    if new_interests:
        existing   = set(mem.get("interests", []))
        combined   = list(existing | set(new_interests))
        mem["interests"] = combined[:20]

    # --- Open threads ---
    open_thread = delta.get("new_open_thread")
    if open_thread:
        threads = mem.setdefault("open_threads", [])
        # Avoid exact duplicates
        if not any(t.get("question") == open_thread for t in threads):
            threads.append({"question": open_thread, "resolved": False})
        mem["open_threads"] = threads[-10:]  # keep last 10

    # --- Session log (v2 concept graph mining — always written) ---
    today_log = {
        "session_id":    state.get("session_id", ""),
        "date":          _now_iso(),
        "topics_touched": delta.get("topics_touched", []),
        "evaluations":   [delta["evaluation"]] if delta.get("evaluation") else [],
    }
    logs = mem.setdefault("session_log", [])
    logs.append(today_log)
    mem["session_log"] = logs[-50:]  # keep last 50 sessions

    return mem


def upsert_student_memory(user_id: str, mem: dict) -> None:
    """Write student memory to MongoDB (upsert by user_id)."""
    collection = mongo_db["student_memory"]
    mem["updated_at"] = _now_iso()
    collection.find_one_and_update(
        {"user_id": user_id},
        {"$set": mem},
        upsert=True,
    )
