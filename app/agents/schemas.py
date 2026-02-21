from pydantic import BaseModel, Field
from typing import Literal

MAX_STEPS = 5

class LessonPlanSchema(BaseModel):
    """Schema for structured lesson plan generation."""
    topic: str = Field(..., description="The main topic of the lesson (e.g., 'Photosynthesis')")
    steps: list[str] = Field(
        ..., 
        description=f"A list of up to {MAX_STEPS} detailed steps to cover in the lesson. Generate these steps yourself based on the topic."
    )


class EvaluationSchema(BaseModel):
    """Schema for evaluating user responses and determining next action."""
    action: Literal['proceed', 're-explain'] = Field(
        ...,
        description="Action to take: 'proceed' if user understood well, 're-explain' if they need more help"
    )
    feedback: str = Field(
        ...,
        description="Feedback or hint to provide to the user. If action is 'proceed', this can be encouraging. If 're-explain', provide a helpful hint or clarification."
    )
    understanding_level: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Rate the user's understanding from 1-10, where 1 is no understanding and 10 is complete mastery"
    )


class TopicAnalysisSchema(BaseModel):
    """Schema for analyzing if user's query is related to current lesson or a new topic."""
    is_related: bool = Field(
        ...,
        description="True if the user's query is related to the current lesson topic, False if it's a completely different topic"
    )
    intent: Literal['answer', 'clarification', 'new_topic', 'off_topic_question', 'small_talk'] = Field(
        ...,
        description="User's intent: 'answer' (answering lesson question), 'clarification' (asking about current topic), 'new_topic' (wants to learn something new), 'off_topic_question' (unrelated question), 'small_talk' (casual conversation, greetings, jokes)"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence level in the analysis (0.0 to 1.0)"
    )
    suggested_action: Literal['continue_lesson', 'answer_and_continue', 'switch_topic', 'politely_redirect', 'handle_small_talk'] = Field(
        ...,
        description="Suggested action: 'continue_lesson' (proceed with current lesson), 'answer_and_continue' (answer question then continue), 'switch_topic' (start new lesson), 'politely_redirect' (redirect to current lesson), 'handle_small_talk' (respond to casual conversation warmly)"
    )