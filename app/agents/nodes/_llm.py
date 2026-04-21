"""
Lightweight LLM helpers for the reimagined agent nodes.
Wraps the existing ChatGoogleGenerativeAI instance with convenience methods.
"""
import logging
from app.agents.llm import LLM

logger = logging.getLogger(__name__)

_llm_instance = None


def _get_llm():
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLM().get_llm()
    return _llm_instance


def invoke(prompt: str) -> str:
    """Single LLM call. Returns plain text content."""
    try:
        response = _get_llm().invoke(prompt)
        return response.content
    except Exception as e:
        logger.error(f"LLM invoke failed: {e}")
        return ""


def invoke_with_tool(prompt: str, tool_schema) -> object:
    """
    Structured output call using with_structured_output.
    Returns an instance of tool_schema, or None on failure.
    """
    try:
        chain = _get_llm().with_structured_output(tool_schema)
        return chain.invoke(prompt)
    except Exception as e:
        logger.error(f"LLM invoke_with_tool({tool_schema.__name__}) failed: {e}")
        return None
