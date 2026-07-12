"""
nodes/react_agent.py
─────────────────────────────────────────────
The single LangGraph node that replaces the old 5-node routing graph.

Runs a proper ReAct (Reason + Act) loop:
  1. Set ContextVars so all tools can access signal_fn, memory managers,
     and user context without needing them as function parameters.
  2. Bind ALL_TOOLS to the LLM.
  3. Loop: LLM generates a response → if tool_calls present, execute each
     tool → append ToolMessages → repeat → until no more tool_calls or
     MAX_ITERATIONS reached.
  4. Collect state patches written by tools during the loop and merge
     them into the returned state delta.
  5. Return final AIMessage + updated state fields.

Thread safety:
  ContextVars are set inside this function which runs in the thread
  started by asyncio.to_thread(chat, ...).  The _signal_fn_var is set
  by chat() before graph.invoke() using the value passed in from the
  WS handler.  Each tool that needs the WS callback reads _signal_fn_var
  directly — no argument passing needed.
"""

import logging
import re
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from ..state import AgentState
from ..llm import llm
from ..memory.teacher_memory import TeacherMemoryManager
from ..memory.web_search_memory import WebSearchMemoryManager
from ..prompts.react_agent import build_system_prompt
from ..tools import ALL_TOOLS
from ..tools.context import (
    _state_patches_var,
    _user_context_var,
    _memory_var,
    _lesson_state_var,
)

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8


def _extract_text(content) -> str:
    """Normalise AIMessage.content to plain text.

    Some providers (e.g. Anthropic) return content as a list of blocks
    like [{"type": "text", "text": "..."}] instead of a plain string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


# Markdown/formatting tokens the LLM is told never to use, kept as a
# code-level safety net since prompt instructions alone are unreliable
# (temperature 0.7, long tool-loop contexts). Applied once, right before
# the final response is stored/translated/spoken, since every downstream
# consumer (history, translate_text, TTS) flows through final_content.
_BOLD_ITALIC_RE   = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|\*(.+?)\*|_(.+?)_")
_HEADING_RE       = re.compile(r"^\s{0,3}#{1,6}\s*", flags=re.MULTILINE)
_BULLET_RE        = re.compile(r"^\s*[-*•◦▸]\s+", flags=re.MULTILINE)
_NUMBERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+", flags=re.MULTILINE)
_CODE_FENCE_RE    = re.compile(r"```.*?```", flags=re.DOTALL)
_INLINE_CODE_RE   = re.compile(r"`([^`]*)`")
_HR_RE            = re.compile(r"^\s*[-─━═*_]{3,}\s*$", flags=re.MULTILINE)
# Catch-all: any formatting character that survived the structured passes above.
# Applied last so it only removes stray symbols — content is already extracted.
_STRAY_FORMAT_RE  = re.compile(r"[*#_\\|`~]")


def _strip_markdown(text: str) -> str:
    """Strip markdown/formatting symbols so the text is safe for TTS."""
    text = _CODE_FENCE_RE.sub(lambda m: m.group(0).strip("`"), text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _BOLD_ITALIC_RE.sub(lambda m: next(g for g in m.groups() if g is not None), text)
    text = _HEADING_RE.sub("", text)
    text = _HR_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _NUMBERED_LIST_RE.sub("", text)
    # Remove any stray formatting characters left after the structural passes.
    # This is the safety net for lone bare `*` (e.g. "word*"), unmatched `#`, etc.
    text = _STRAY_FORMAT_RE.sub("", text)
    return text


def react_agent_node(
    state: AgentState,
    teacher_memory: TeacherMemoryManager,
    web_memory: WebSearchMemoryManager,
) -> dict:
    """
    ReAct loop node. Replaces orchestrator + teacher + general + web_search
    + user_confirmation nodes with a single tool-calling loop.

    teacher_memory and web_memory are injected by functools.partial in
    graph.py — identical pattern to the old node wiring.
    """

    # ── 1. Initialise ContextVars for this turn ───────────────────────────
    patches: dict = {}
    _state_patches_var.set(patches)
    _user_context_var.set({
        "user_id": state.get("user_id", ""),
        "board":   state.get("board"),
        "grade":   state.get("grade"),
    })
    _memory_var.set({"teacher": teacher_memory, "web": web_memory})
    _lesson_state_var.set({
        "lesson_status": state.get("lesson_status", "OFF"),
        "topic":         state.get("topic"),
        "lesson_plan":   state.get("lesson_plan") or [],
        "subtopic_idx":  state.get("subtopic_idx", 0),
        "mode":          state.get("mode", "DEFAULT"),
    })
    # Note: _signal_fn_var is already set by chat() before graph.invoke().

    # ── 2. Build tool-bound LLM + tool lookup map ─────────────────────────
    tool_map        = {t.name: t for t in ALL_TOOLS}
    llm_with_tools  = llm.bind_tools(ALL_TOOLS)

    # ── 3. Assemble messages ──────────────────────────────────────────────
    system_msg  = SystemMessage(content=build_system_prompt(state))
    history     = list(state.get("messages") or [])
    current_q   = HumanMessage(content=state.get("query", ""))
    messages    = [system_msg] + history + [current_q]

    # ── 4. ReAct loop ─────────────────────────────────────────────────────
    final_content = "(no response)"
    last_ai_msg   = None

    for iteration in range(MAX_ITERATIONS):
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)
        last_ai_msg = ai_msg

        if not ai_msg.tool_calls:
            # No tool calls → this is the final natural-language answer
            raw_text = _extract_text(ai_msg.content).strip()
            final_content = _strip_markdown(raw_text) or "(no response)"
            if final_content == "(no response)":
                logger.warning(
                    "react_agent: LLM returned empty content on iter=%d | "
                    "raw_len=%d raw_preview=%r | user=%s",
                    iteration + 1,
                    len(raw_text),
                    raw_text[:120],
                    state.get("user_id", "?")[:12],
                )
            logger.info(
                "react_agent: completed in %d iteration(s) | user=%s",
                iteration + 1,
                state.get("user_id", "?")[:12],
            )
            break

        # Execute each requested tool call
        for tc in ai_msg.tool_calls:
            t_name = tc.get("name", "")
            t_args = tc.get("args", {})
            t_id   = tc.get("id", "")

            logger.info("react_agent[iter=%d]: tool=%s args=%s", iteration, t_name, t_args)

            tool_fn = tool_map.get(t_name)
            if tool_fn:
                try:
                    result = tool_fn.invoke(t_args)
                except Exception as exc:
                    result = f"Tool error in {t_name}: {exc}"
                    logger.error("react_agent tool error (%s): %s", t_name, exc)
            else:
                result = f"Unknown tool: {t_name}"
                logger.warning("react_agent: unknown tool '%s'", t_name)

            messages.append(ToolMessage(content=str(result), tool_call_id=t_id))

    else:
        # Exhausted MAX_ITERATIONS — use the last AIMessage that had content
        logger.warning(
            "react_agent: hit MAX_ITERATIONS (%d) for user=%s",
            MAX_ITERATIONS,
            state.get("user_id", "?")[:12],
        )
        for msg in reversed(messages):
            if (
                isinstance(msg, AIMessage)
                and msg.content
                and not getattr(msg, "tool_calls", None)
            ):
                final_content = _strip_markdown(_extract_text(msg.content).strip()) or "(no response)"
                break

    # ── 4b. Fallback: if LLM produced empty content and used no tools, check
    #         whether the query is a live-data question and call search_web
    #         directly.  This guards against gemini-2.5-flash thinking-mode
    #         glitches where the model generates only an internal thinking
    #         block with empty final output and no tool_calls.
    if final_content == "(no response)":
        query = state.get("query", "")
        _LIVE_KW = {
            "right now", "current", "today", "latest", "now", "price",
            "rate", "score", "news", "rupee", "dollar", "euro", "pound",
            "weather", "stock", "crypto", "bitcoin", "how much is",
            "what is the", "who is the", "who won", "election", "result",
        }
        q_lower = query.lower()
        if any(kw in q_lower for kw in _LIVE_KW):
            logger.warning(
                "react_agent: empty response on live-data query — "
                "falling back to direct search_web | user=%s",
                state.get("user_id", "?")[:12],
            )
            search_fn = tool_map.get("search_web")
            if search_fn:
                try:
                    search_result = search_fn.invoke({"query": query})
                    # One direct LLM call to synthesize the result (no tools)
                    synth = llm.invoke([
                        SystemMessage(
                            content=(
                                "Summarize this search result in 2-3 clear spoken sentences "
                                "for a voice assistant. Write exactly as you would speak to "
                                "someone. No bullet points, no markdown, no symbols."
                            )
                        ),
                        HumanMessage(content=f"User asked: {query}\n\nSearch result:\n{search_result[:2000]}"),
                    ])
                    synthesized = _strip_markdown(_extract_text(synth.content).strip())
                    if synthesized:
                        final_content = synthesized
                        logger.info("react_agent: fallback search succeeded | user=%s",
                                    state.get("user_id", "?")[:12])
                except Exception as exc:
                    logger.error("react_agent: fallback search_web failed: %s", exc)

    # ── 5. Build state delta ──────────────────────────────────────────────
    delta: dict = {
        "messages":        [AIMessage(content=final_content)],
        "tool_call_count": (state.get("tool_call_count") or 0) + 1,
    }

    # Apply state patches accumulated by tools during the loop
    for key in (
        "awaiting_user_input",
        "quiz_correct_answer",
        "lesson_status",
        "topic",
        "lesson_plan",
        "current_subtopic",
        "subtopic_idx",
        "weak_concepts",
        "step_context",
    ):
        if key in patches:
            delta[key] = patches[key]

    return delta
