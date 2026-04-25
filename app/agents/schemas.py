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
        description=(
            "True ONLY if the student made a genuine attempt to answer and showed at least partial understanding. "
            "False for: 'I don't know', 'idk', 'no idea', 'not sure', 'I have no clue', blank or one-word non-answers, "
            "or any response that does not engage with the question at all. "
            "Being honest about not knowing is NOT the same as being correct."
        )
    )
    feedback: str = Field(
        ...,
        description=(
            "If is_correct=True: warm, encouraging praise acknowledging what they got right. "
            "If is_correct=False: be gentle and supportive, then clearly explain the correct answer so the student learns."
        )
    )
    understanding_level: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Rate the user's understanding from 1-10, where 1 is no understanding and 10 is complete mastery. 'I don't know' = 1."
    )


class TopicAnalysisSchema(BaseModel):
    """Schema for analyzing if user's query is related to current lesson or represents a topic change."""
    is_related: bool = Field(
        ...,
        description="True if the user's query is related to the current lesson topic, False if it's a completely different topic"
    )
    intent: Literal['answer', 'clarification', 'new_topic', 'off_topic_question', 'small_talk', 'repeat_request'] = Field(
        ...,
        description="User's intent: 'answer' (answering lesson question), 'clarification' (asking about current topic), 'new_topic' (wants to learn something new or get explanation for a new question), 'off_topic_question' (unrelated question), 'small_talk' (casual conversation, greetings, jokes), 'repeat_request' (user wants you to repeat what you said)"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence level in the analysis (0.0 to 1.0)"
    )
    suggested_action: Literal['continue_lesson', 'answer_and_continue', 'switch_topic', 'politely_redirect', 'handle_small_talk', 'repeat_last_message'] = Field(
        ...,
        description="Suggested action: 'continue_lesson' (proceed with current lesson), 'answer_and_continue' (answer question then continue), 'switch_topic' (exit lesson, go to general mode for new topic), 'politely_redirect' (redirect to current lesson), 'handle_small_talk' (respond to casual conversation warmly), 'repeat_last_message' (repeat what was previously said)"
    )


# ========================================
# V1 UPGRADE SCHEMAS
# ========================================

class RoutingSchema(BaseModel):
    """Smart router: classifies intent AND produces a lightweight student diagnosis in one call."""
    intent: Literal['small_talk', 'qa', 'teach', 'evaluate'] = Field(
        ...,
        description=(
            "'small_talk' — greeting, casual, off-topic personal conversation. "
            "'qa' — factual question, wants a direct answer (no multi-step lesson). "
            "'teach' — conceptual topic that deserves a structured step-by-step explanation. "
            "'evaluate' — student is answering a question the tutor previously posed."
        )
    )
    topic_slug: Optional[str] = Field(
        None,
        description=(
            "Snake_case topic identifier when intent is 'teach' or 'qa'. "
            "e.g. 'newtons_second_law', 'photosynthesis_light_reaction'. "
            "This becomes the key in the student memory document."
        )
    )
    topic_name: Optional[str] = Field(
        None,
        description="Human-readable version of the topic. e.g. 'Newton's Second Law'."
    )
    diagnosis: str = Field(
        ...,
        description=(
            "1 sentence: what does this student ACTUALLY need right now? "
            "Look at the memory summary. If they are shaky on a prerequisite, say so. "
            "BAD: 'Student asked about Newton's laws.' "
            "GOOD: 'Student asked about F=ma but memory shows shaky on force_basics — may need that first.'"
        )
    )


class LessonContextSchema(BaseModel):
    """Routes within an active lesson — used by smart_router when a lesson is in progress."""
    intent: Literal['teach', 'evaluate', 'small_talk', 'qa'] = Field(
        ...,
        description=(
            "'evaluate' if the student is answering the tutor's Socratic question. "
            "'teach' if the student asked a clarification or a related sub-question. "
            "'small_talk' if clearly off-topic (do not force into lesson). "
            "'qa' if the student is asking a meta/history question about their own progress, "
            "what topics they have studied, or any factual question unrelated to the current lesson."
        )
    )
    is_exiting_lesson: bool = Field(
        default=False,
        description="True if the student clearly wants to stop the current lesson."
    )
    repeat_requested: bool = Field(
        default=False,
        description="True if the student said they didn't hear or understand and wants a repeat."
    )


class MemoryFilterSchema(BaseModel):
    """
    LLM quality gate: decides which signals from a turn are worth persisting
    in the long-term student memory for future sessions.
    """
    persist_evaluation: bool = Field(
        ...,
        description=(
            "True only if the student's response was substantive enough to update "
            "their topic knowledge state. A one-word answer like 'yes', 'ok', or 'I don't know' "
            "is NOT substantive — return False."
        )
    )
    interests: list[str] = Field(
        default_factory=list,
        description=(
            "Any personal interests, hobbies, or curiosity topics the student "
            "mentioned this turn (e.g. 'cricket', 'space', 'cooking'). "
            "Empty list if none detected."
        )
    )
    open_thread: Optional[str] = Field(
        default=None,
        description=(
            "A question the student asked that was NOT fully answered this turn — "
            "worth revisiting in a future session. Null if none."
        )
    )
    reason: str = Field(
        ...,
        description="1 sentence explaining the persist_evaluation decision."
    )