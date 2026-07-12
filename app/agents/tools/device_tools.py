"""
tools/device_tools.py
─────────────────────────────────────────────
signal_device_state — pushes an agent_state JSON text frame to the device
over the active WebSocket connection.

Valid states (must match ws_event_handler in user_actions.c):
  "thinking"   → neural_pulse animation
  "searching"  → data_scan animation
  "asking"     → ball_court animation

The callback in _signal_fn_var is a thread-safe wrapper created by the
WS handler using asyncio.run_coroutine_threadsafe so this tool can safely
call it from within the sync thread started by asyncio.to_thread().
"""
import json
import logging
from langchain_core.tools import tool
from .context import _signal_fn_var

logger = logging.getLogger(__name__)

VALID_STATES = frozenset({"thinking", "searching", "asking"})


def _do_signal(state: str) -> None:
    """Internal helper — shared by device_tools and other tool modules."""
    fn = _signal_fn_var.get()
    if fn is None:
        logger.warning("_do_signal(%s): signal_fn is None — no WS callback set", state)
        return
    payload = json.dumps({"type": "agent_state", "value": state}, separators=(',', ':'))
    logger.info("_do_signal: sending '%s'", payload)
    try:
        fn(payload)
    except Exception as exc:
        logger.warning("device signal failed (state=%s): %s", state, exc)


@tool
def signal_device_state(state: str) -> str:
    """
    Update the visual state shown on the AI device screen.
    Always call this BEFORE the operation it describes, not after.

    Valid values:
      "thinking"  — agent is reasoning or processing (neural-pulse animation)
      "searching" — agent is fetching external data (data-scan animation)
      "asking"    — agent needs user input / is posing a question (ball-court animation)

    Examples:
      signal_device_state("thinking")   before a complex reasoning step
      signal_device_state("searching")  before search_web or retrieve_curriculum_context
      signal_device_state("asking")     before clarify_intent or quiz_user
    """
    if state not in VALID_STATES:
        return f"Invalid state '{state}'. Must be one of: {', '.join(sorted(VALID_STATES))}"

    _do_signal(state)
    logger.info("signal_device_state: sent '%s'", state)
    return f"Device display updated to '{state}'"
