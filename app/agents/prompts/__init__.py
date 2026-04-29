# Re-export legacy prompts so existing callers (e.g. app/main.py) keep working:
#   from app.agents.prompts import AI_TUTOR_PROMPT, AI_DEVICE_TUTOR_PROMPT
from .legacy import AI_TUTOR_PROMPT, AI_DEVICE_TUTOR_PROMPT

__all__ = ["AI_TUTOR_PROMPT", "AI_DEVICE_TUTOR_PROMPT"]
