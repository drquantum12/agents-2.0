"""
tools/search_tool.py
─────────────────────────────────────────────
search_web — Gemini-grounded web search with result caching.

Automatically signals "searching" to the device before the API call.
Uses the same Gemini grounding approach as the legacy web_search_node;
the WebSearchMemoryManager cache is preserved.
"""
import logging
import os
from typing import List

from langchain_core.tools import tool
from google import genai
from google.genai import types

from .context import _user_context_var, _memory_var
from .device_tools import _do_signal

logger = logging.getLogger(__name__)

_gemini_client  = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
_GEMINI_MODEL   = "gemini-2.5-flash"
_GROUNDING_TOOL = types.Tool(google_search=types.GoogleSearch())
_GEN_CONFIG     = types.GenerateContentConfig(tools=[_GROUNDING_TOOL])


@tool
def search_web(query: str) -> str:
    """
    Search the web for current, real-time, or factual information not in
    the curriculum knowledge base (news, live data, recent events, prices,
    latest model releases, current affairs, etc.).

    Returns a synthesised answer. Sources are embedded in the response.
    Do NOT use this for curriculum topics — use retrieve_curriculum_context first.
    """
    _do_signal("searching")

    user_ctx = _user_context_var.get() or {}
    user_id  = user_ctx.get("user_id", "")
    memories = _memory_var.get() or {}
    web_mem  = memories.get("web")

    # Cache lookup
    if web_mem and user_id:
        cached = web_mem.get_cached(user_id, query)
        if cached:
            logger.info("search_web: cache hit for '%s'", query[:60])
            return cached["response_text"]

    # Gemini grounded call
    try:
        response = _gemini_client.models.generate_content(
            model=_GEMINI_MODEL, contents=query, config=_GEN_CONFIG
        )
        text = response.text or ""

        # Extract grounding metadata
        sources: List[dict] = []
        search_queries: List[str] = []
        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.grounding_metadata:
            meta = candidate.grounding_metadata
            seen: set = set()
            for chunk in (meta.grounding_chunks or []):
                if chunk.web and chunk.web.uri and chunk.web.uri not in seen:
                    seen.add(chunk.web.uri)
                    sources.append({
                        "title": chunk.web.title or chunk.web.uri,
                        "uri":   chunk.web.uri,
                    })
            search_queries = list(meta.web_search_queries or [])

        # Persist to cache
        if web_mem and user_id and sources:
            web_mem.save(
                user_id=user_id, query=query,
                response_text=text, sources=sources,
                search_queries_used=search_queries,
            )

        logger.info("search_web: got %d sources for '%s'", len(sources), query[:60])
        return text

    except Exception as exc:
        logger.error("search_web error: %s", exc)
        return (
            "I wasn't able to retrieve live information right now. "
            "Please try again or rephrase your question."
        )
