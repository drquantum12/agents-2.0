"""
Quiz creator tool — generates micro-quizzes and writes results to WorldModelDelta.

Contract: quiz results MUST flow back through WorldModelDelta so the knowledge
graph reflects what the student actually demonstrated.
"""
import logging
from typing import Optional, Tuple
from pydantic import BaseModel, Field

from app.agents.tools.base import VijayebhavTool, register_tool

logger = logging.getLogger(__name__)

QUIZ_PROMPT = """You are generating a 3-question quiz on: {concept_name}
Difficulty: {difficulty}

Generate exactly 3 questions — each answerable in one or two sentences.
Questions should test understanding, not just recall.
After each question, provide the ideal answer in parentheses.

Format as plain text — no bullets, no numbers. Write as spoken questions.
Example: "My first question is: ... (ideal answer: ...)"
"""


class QuizSchema(BaseModel):
    questions: list = Field(description="List of question strings")
    answers: list = Field(description="List of ideal answer strings")
    score: Optional[float] = Field(default=None, description="0.0–1.0 after student responds")


class QuizCreatorTool(VijayebhavTool):
    name = "quiz_creator"
    description = (
        "Generate a 3-question quiz on a concept. "
        "Use after a concept is taught to probe understanding. "
        "Input format: 'concept_id=<id>,difficulty=<Beginner|Intermediate|Advanced>'"
    )

    def run(self, input: str) -> Tuple[str, Optional[object]]:
        """
        Returns (spoken quiz text, WorldModelDelta).
        The delta is a stub — it will be populated after the student answers.
        Score-based delta update happens in the calling node.
        """
        from app.agents.concept_graph import store as concept_store
        from app.agents.nodes._llm import invoke_with_tool

        try:
            params = dict(p.split("=", 1) for p in input.split(",") if "=" in p)
            concept_id = params.get("concept_id", "").strip()
            difficulty = params.get("difficulty", "Intermediate").strip()

            node = concept_store.get(concept_id)

            prompt = QUIZ_PROMPT.format(
                concept_name=node.name,
                difficulty=difficulty,
            )
            result = invoke_with_tool(prompt, QuizSchema)

            if not result or not result.questions:
                return (self._fallback_quiz(node.name), None)

            spoken = self._format_for_speech(result)
            logger.info(f"QuizCreatorTool: generated quiz for '{concept_id}'")
            return (spoken, None)

        except Exception as e:
            logger.error(f"QuizCreatorTool.run failed: {e}")
            return ("I have prepared a quick quiz. Are you ready?", None)

    def _format_for_speech(self, result: QuizSchema) -> str:
        intros = ["Here is my first question.", "Second question.", "And finally, third question."]
        parts = []
        for i, (q, _) in enumerate(zip(result.questions, result.answers)):
            intro = intros[i] if i < len(intros) else f"Question {i+1}."
            parts.append(f"{intro} {q}")
        return " ".join(parts)

    def _fallback_quiz(self, concept_name: str) -> str:
        return (
            f"Let me ask you three quick questions about {concept_name}. "
            "First: can you explain the core idea in your own words? "
            "Second: can you give me one real-world example? "
            "Third: what would happen if this principle did not exist?"
        )


def apply_quiz_result(concept_id: str, score: float) -> object:
    """
    Build a WorldModelDelta from a quiz score.
    Call this after collecting the student's responses.
    score >= 0.7 → 'known', else → 'shaky'
    """
    from app.agents.world_model.updater import WorldModelDelta
    return WorldModelDelta(
        concept_state_updates={concept_id: "known" if score >= 0.7 else "shaky"},
        fatigue_delta=0.05,
    )


register_tool(QuizCreatorTool())
