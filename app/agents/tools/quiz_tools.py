"""
tools/quiz_tools.py
─────────────────────────────────────────────
quiz_user    — register a quiz question the LLM already composed, persist
               correct_answer in state, mark awaiting_user_input = True.
check_answer — compare student vs correct answer, clear state, return a
               structured verdict the LLM uses to generate warm feedback.

No internal LLM calls — the ReAct loop LLM generates the question and
feedback text itself, eliminating 1-2 redundant API calls per quiz turn.

State mutations go to _state_patches_var so react_agent_node can merge
them into the returned LangGraph state delta.
"""
import logging
from langchain_core.tools import tool
from .context import _state_patches_var

logger = logging.getLogger(__name__)


def _patch(key: str, value) -> None:
    patches = _state_patches_var.get()
    if patches is not None:
        patches[key] = value


@tool
def quiz_user(topic: str, question: str, correct_answer: str, difficulty: str = "medium") -> str:
    """
    Register a quiz question you have already composed and store the correct answer.
    The question will be spoken to the student; wait for their reply then call check_answer.

    YOU must compose the question and correct_answer before calling this tool.
    Do not call an extra tool to generate them — write them directly as arguments.

    Signal "asking" to the device BEFORE calling this tool.

    Args:
        topic:          Subject area (for logging). E.g. "Newton's second law"
        question:       The question to ask the student (spoken aloud).
        correct_answer: The definitive correct answer (stored in state, NOT spoken).
        difficulty:     "easy" | "medium" | "hard"  (default: "medium")

    Returns the question string — use it as your spoken response to the student.
    """
    difficulty = difficulty.lower().strip()
    if difficulty not in ("easy", "medium", "hard"):
        difficulty = "medium"

    _patch("quiz_correct_answer", correct_answer.strip())
    _patch("awaiting_user_input", True)

    logger.info("quiz_user: registered '%s' difficulty question on '%s'", difficulty, topic[:50])
    return question.strip()


@tool
def check_answer(student_answer: str, correct_answer: str) -> str:
    """
    Compare the student's answer against the correct answer and return a verdict.
    Call this when the student replies to a quiz question.

    YOU generate the warm feedback text yourself after seeing this verdict —
    do not call any other tool for it.

    Args:
        student_answer: What the student said.
        correct_answer: The stored correct answer (from quiz_correct_answer in state).

    Returns one of:
        "CORRECT"           — student got it right
        "PARTIAL: <detail>" — answer is partially correct, detail says what's missing
        "INCORRECT"         — student got it wrong

    After receiving the verdict, write 2-3 sentences of warm, spoken feedback yourself.
    """
    s = student_answer.strip().lower()
    c = correct_answer.strip().lower()

    _patch("quiz_correct_answer", None)
    _patch("awaiting_user_input", False)

    # Exact match
    if s == c:
        logger.info("check_answer: CORRECT")
        return "CORRECT"

    # Substring containment — partial credit heuristic
    # (LLM will refine the verdict contextually based on this hint)
    if c in s or s in c:
        logger.info("check_answer: PARTIAL (substring match)")
        return f"PARTIAL: answer contains key elements but is not complete or precise"

    # Key-word overlap — crude but avoids an LLM call
    c_words = set(c.split())
    s_words = set(s.split())
    overlap  = c_words & s_words - {"the", "a", "an", "is", "are", "of", "in", "and", "or"}
    if overlap and len(overlap) / max(len(c_words), 1) >= 0.5:
        missing = c_words - s_words - {"the", "a", "an", "is", "are", "of", "in", "and", "or"}
        detail  = f"missing: {', '.join(list(missing)[:3])}" if missing else "not precise enough"
        logger.info("check_answer: PARTIAL (keyword overlap)")
        return f"PARTIAL: {detail}"

    logger.info("check_answer: INCORRECT")
    return "INCORRECT"
