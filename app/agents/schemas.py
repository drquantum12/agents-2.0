from pydantic import BaseModel, Field
from typing import Literal, Optional

MAX_STEPS = 5


class QueryClassificationSchema(BaseModel):
    """Schema for classifying whether a user query is general or needs detailed explanation."""
    query_type: Literal['general', 'explanation'] = Field(
        ...,
        description=(
            "'general' if the query is a simple/factual question, small talk, greeting, or casual conversation "
            "that can be answered in a few sentences. "
            "'explanation' if the query asks about a concept, process, or topic that would benefit from a "
            "structured, multi-step breakdown to truly understand it."
        )
    )
    topic: str = Field(
        ...,
        description="A clear, concise version of the topic or question the user is asking about."
    )


class LessonPlanSchema(BaseModel):
    """Schema for structured lesson plan generation."""
    topic: str = Field(..., description="The main topic of the lesson (e.g., 'Photosynthesis')")
    steps: list[str] = Field(
        ..., 
        description=f"A list of minimum 3 and maximum {MAX_STEPS} detailed sub-topic steps to cover in the lesson. Generate these steps yourself based on the topic."
    )


class EvaluationSchema(BaseModel):
    """Schema for evaluating user responses and determining next action."""
    is_correct: bool = Field(
        ...,
        description="True if the user's answer demonstrates understanding of the concept, False otherwise."
    )
    feedback: str = Field(
        ...,
        description=(
            "If is_correct=True: warm, encouraging praise acknowledging what they got right. "
            "If is_correct=False: appreciate the attempt, then clearly explain the correct answer."
        )
    )
    understanding_level: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Rate the user's understanding from 1-10, where 1 is no understanding and 10 is complete mastery"
    )


class ConfirmationSchema(BaseModel):
    """Schema for classifying a user's response to a lesson offer."""
    intent: Literal['yes', 'no', 'new_query'] = Field(
        ...,
        description=(
            "'yes' if the user is agreeing to or confirming the lesson offer (even with extra words like 'yes tell me more', 'sure go ahead', 'I'd love that'). "
            "'no' if the user is declining (e.g. 'no thanks', 'not now', 'I'm good'). "
            "'new_query' if the user ignored the offer and asked a completely new question."
        )
    )


class TopicAnalysisSchema(BaseModel):
    """Schema for analyzing if user's query is related to current lesson or represents a topic change."""
    is_related: bool = Field(
        ...,
        description="True if the user's query is related to the current lesson topic, False if it's a completely different topic"
    )
    intent: Literal['answer', 'clarification', 'new_topic', 'off_topic_question', 'small_talk'] = Field(
        ...,
        description="User's intent: 'answer' (answering lesson question), 'clarification' (asking about current topic), 'new_topic' (wants to learn something new or get explanation for a new question), 'off_topic_question' (unrelated question), 'small_talk' (casual conversation, greetings, jokes), 'repeat_request' (user wants you to repeat what you said)"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence level in the analysis (0.0 to 1.0)"
    )
    suggested_action: Literal['continue_lesson', 'answer_and_continue', 'switch_topic', 'politely_redirect', 'handle_small_talk'] = Field(
        ...,
        description="Suggested action: 'continue_lesson' (proceed with current lesson), 'answer_and_continue' (answer question then continue), 'switch_topic' (exit lesson, go to general mode for new topic), 'politely_redirect' (redirect to current lesson), 'handle_small_talk' (respond to casual conversation warmly), 'repeat_last_message' (repeat what was previously said)"
    )


# ── REIMAGINED ARCHITECTURE SCHEMAS ─────────────────────────────────────────

class PedagogicalReasoningSchema(BaseModel):
    """Tool schema for the Pedagogical Reasoner node."""
    teaching_mode: Literal[
        "prerequisite_repair",
        "re_analogise",
        "advance",
        "thread_resolve",
        "disengage",
        "lesson_complete",
    ] = Field(description="The teaching action to take this turn.")
    target_concept_id: str = Field(
        description=(
            "ID of concept to teach. For prerequisite_repair, this is the "
            "PREREQUISITE concept, not the one asked about."
        )
    )
    reasoning_trace: str = Field(
        description="1-2 sentences explaining the choice. Not shown to student."
    )
    concept_state_update: Optional[dict] = Field(
        default=None,
        description=(
            "concept_id → new state ('known'|'shaky'|'blocked'). "
            "Only populate if student answered a question this turn."
        ),
    )
    detected_student_analogy: Optional[str] = Field(
        default=None,
        description="If student offered a metaphor of their own, capture it.",
    )
    new_open_thread: Optional[str] = Field(
        default=None,
        description="Verbatim question the student raised that was not answered.",
    )
    curiosity_signal: Optional[str] = Field(
        default=None,
        description="Topic the student mentioned unprompted.",
    )
    fatigue_delta: float = Field(
        default=0.0,
        description="+0.1 if student shows confusion. -0.2 after disengage. 0.0 otherwise.",
    )


class ConceptPathSchema(BaseModel):
    """Used by lesson_planner to set initial concept path."""
    concept_ids: list = Field(
        description=(
            "Ordered concept IDs from concept graph for this topic. "
            "3 for Beginner, 4 for Intermediate, 5 for Advanced."
        )
    )
    topic_summary: str = Field(
        description="1-sentence summary of the overall lesson goal."
    )