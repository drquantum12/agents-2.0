from .classifier import build_classifier_prompt
from .teacher import (
    build_relevance_check_prompt,
    build_topic_extract_prompt,
    build_short_explanation_prompt,
    build_lesson_plan_prompt,
    build_subtopic_explanation_prompt,
    build_strict_mode_prompt,
    build_lesson_intro_prompt,
)
from .general import build_general_prompt
from .web_search import build_grounded_query
