from pydantic import BaseModel, Field
from typing import Literal

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