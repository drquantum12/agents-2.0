"""
nodes/web_search.py
─────────────────────────────────────────────
Handles WEB_SEARCH intent using Gemini with Google Search grounding.

Why Gemini grounding instead of search-tool + separate LLM synthesis:
  • Single API call — Gemini retrieves AND synthesises in one shot.
  • Grounding metadata gives us verifiable citations (title + URI).
  • No hallucination risk from a separate synthesis step working on
    potentially truncated raw-text results.

Flow:
  1. Check WebSearchMemory cache for (user_id, query).
  2. Cache hit  → return stored response_text + format sources.
  3. Cache miss → build educational context query
                → call Gemini with GoogleSearch grounding tool
                → extract response text + grounding metadata
                → persist to MongoDB cache
                → return formatted response.

Configuration:
  Set GEMINI_MODEL to any Gemini model that supports grounding.
  Recommended: "gemini-2.0-flash"  (fast, cheap, grounding-capable)
               "gemini-2.5-flash-preview-05-20"  (higher quality)
"""

import logging
import os
from typing import List

from langchain_core.messages import AIMessage
from google import genai
from google.genai import types

from ..state import AgentState
from ..memory.web_search_memory import WebSearchMemoryManager, GroundedSearchResult
from ..prompts.web_search import build_grounded_query

logger = logging.getLogger(__name__)

# ── Gemini client (initialised once at import time) ───────────────────────────
_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

GEMINI_MODEL    = "gemini-2.5-flash"   # swap to any grounding-capable model
_GROUNDING_TOOL = types.Tool(google_search=types.GoogleSearch())
_GEN_CONFIG     = types.GenerateContentConfig(tools=[_GROUNDING_TOOL])


# ── Grounding helpers ─────────────────────────────────────────────────────────

def _call_gemini_grounded(query: str) -> GroundedSearchResult:
    """
    Fire a single Gemini call with Google Search grounding and extract:
      - response_text       : the synthesised answer
      - sources             : [{title, uri}, …]  from grounding chunks
      - search_queries_used : the actual queries Gemini sent to Google

    Raises on hard API failure — caller handles the exception.
    """
    response = _client.models.generate_content(
        model    = GEMINI_MODEL,
        contents = query,
        config   = _GEN_CONFIG,
    )

    response_text = response.text or ""

    # Extract grounding metadata safely (may be absent for short queries)
    sources:             List[dict] = []
    search_queries_used: List[str]  = []

    candidate = response.candidates[0] if response.candidates else None
    if candidate and candidate.grounding_metadata:
        meta = candidate.grounding_metadata

        # Grounding chunks → citation sources
        for chunk in (meta.grounding_chunks or []):
            if chunk.web and chunk.web.uri:
                sources.append({
                    "title": chunk.web.title or chunk.web.uri,
                    "uri":   chunk.web.uri,
                })

        # Deduplicate sources (same URI can appear in multiple chunks)
        seen_uris:   set[str] = set()
        unique_sources: List[dict] = []
        for src in sources:
            if src["uri"] not in seen_uris:
                seen_uris.add(src["uri"])
                unique_sources.append(src)
        sources = unique_sources

        # Actual search queries Gemini used
        search_queries_used = list(meta.web_search_queries or [])

    return GroundedSearchResult(
        response_text       = response_text,
        sources             = sources,
        search_queries_used = search_queries_used,
    )


def _format_sources_footer(sources: List[dict]) -> str:
    """
    Render a compact, readable sources list to append to the response.
    Returns an empty string if there are no sources.
    """
    if not sources:
        return ""
    lines = ["\n\n**Sources:**"]
    for i, src in enumerate(sources[:5], start=1):   # cap at 5 citations
        lines.append(f"{i}. [{src['title']}]({src['uri']})")
    return "\n".join(lines)


# ── Main node ─────────────────────────────────────────────────────────────────

def web_search_node(
    state:      AgentState,
    web_memory: WebSearchMemoryManager,
) -> dict:
    """
    Performs a grounded web search and returns a student-friendly answer
    with inline citations.
    """
    query   = state.get("query", "").strip()
    user_id = state.get("user_id", "")

    # ── 1. Cache lookup ───────────────────────────────────────────────────
    cached = web_memory.get_cached(user_id, query)
    if cached:
        logger.info("WebSearch: cache hit — query: %s", query[:60])
        final_text = cached["response_text"]
        # + _format_sources_footer(cached["sources"])
        return {
            "messages":           [AIMessage(content=final_text)],
            "awaiting_user_input": False,
        }

    # ── 2. Build educational-context query ────────────────────────────────
    grounded_query = build_grounded_query(query, state)

    # ── 3. Gemini grounded call ───────────────────────────────────────────
    try:
        result = _call_gemini_grounded(grounded_query)
        logger.info(
            "WebSearch: grounded response received — sources=%d, queries=%s",
            len(result["sources"]),
            result["search_queries_used"],
        )
    except Exception as exc:
        logger.error("WebSearch Gemini error: %s", exc)
        result = GroundedSearchResult(
            response_text       = (
                "I wasn't able to retrieve live information right now. "
                "Please try again in a moment, or rephrase your question."
            ),
            sources             = [],
            search_queries_used = [],
        )

    # ── 4. Persist to cache ───────────────────────────────────────────────
    # only cache non error responses with grounding metadata
    if result["sources"] and result["search_queries_used"]:
        web_memory.save(
            user_id             = user_id,
            query               = query,
            response_text       = result["response_text"],
            sources             = result["sources"],
            search_queries_used = result["search_queries_used"],
        )

    # ── 5. Build final message ────────────────────────────────────────────
    final_text = result["response_text"]
    # + _format_sources_footer(result["sources"])

    return {
        "messages":           [AIMessage(content=final_text)],
        "awaiting_user_input": False,
    }
