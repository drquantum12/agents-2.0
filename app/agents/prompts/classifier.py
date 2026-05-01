"""
prompts/classifier.py
─────────────────────────────────────────────
Builds the intent classification prompt used by the orchestrator node.
"""

from ..state import AgentState


def build_classifier_prompt(state: AgentState) -> str:
    """
    Constructs a structured prompt for the intent classifier LLM call.

    Uses full agent state to disambiguate edge cases — especially the
    awaiting_user_input flag which must strongly bias toward CONFIRM_WITH_USER.
    """
    query               = state.get("query", "").strip()
    messages            = state.get("messages", [])
    mode                = (state.get("mode") or "DEFAULT").upper()
    awaiting_user_input = state.get("awaiting_user_input", False)
    topic               = state.get("topic") or "N/A"
    lesson_plan         = state.get("lesson_plan") or []
    lesson_status       = (state.get("lesson_status") or "OFF").upper()
    current_subtopic    = state.get("current_subtopic") or "N/A"
    step_context        = state.get("step_context") or "N/A"

    # Format lesson plan
    if lesson_plan:
        lesson_plan_str = "\n".join(
            f"  {i+1}. {item}" for i, item in enumerate(lesson_plan)
        )
    else:
        lesson_plan_str = "  N/A"

    # Format recent conversation (last 6 turns)
    if messages:
        recent = "\n".join(
            f"  {msg.__class__.__name__}: {msg.content}" for msg in messages[-6:]
        )
    else:
        recent = "  (no prior messages)"

    # Inject lesson block only when a lesson is active — avoids noise
    lesson_block = ""
    if lesson_status == "ON":
        lesson_block = f"""
<active_lesson>
  Topic           : {topic}
  Current Subtopic: {current_subtopic}
  Step Context    : {step_context}
  Lesson Plan     :
{lesson_plan_str}
  Mode            : {mode}
</active_lesson>
"""

    # Inject a prominent warning when the agent is mid-conversation
    awaiting_block = ""
    if awaiting_user_input:
        awaiting_block = """
⚠️  AGENT IS AWAITING USER RESPONSE
The tutor posed a direct question or offered a lesson in the previous turn.
A short reply (yes / no / sure / okay / a number / an option name) is
almost certainly CONFIRM_WITH_USER.
Only classify as something else if the user is CLEARLY asking a brand-new,
unrelated question (e.g. "what is a neural network?" when the offer was
about a different topic).
"""

    return f"""You are the intent classifier for an AI tutoring system.
Your sole job: read the agent state and the user's query, then output EXACTLY one intent label.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AGENT STATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<agent_state>
  awaiting_user_input : {awaiting_user_input}
  lesson_status       : {lesson_status}
  mode                : {mode}
</agent_state>
{awaiting_block}{lesson_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONVERSATION HISTORY (last 6 turns)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{recent}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT USER QUERY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"{query}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTENT DEFINITIONS  (priority order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] CONFIRM_WITH_USER  ← check first
  • awaiting_user_input is True AND the query is a reply to the agent's question
    (e.g. "yes", "no", "sure", "okay", "let's go", "1", "option 2", "skip it")
  • User is agreeing or declining a lesson offer, topic change, or next step
  • User is answering a clarifying question the tutor just posed

[2] EXPLANATION
  • User wants a concept explained, clarified, or taught
    (e.g. "what is X", "how does X work", "explain Y", "I don't understand Z")
  • Query relates to the active lesson topic or subtopic
  • User wants to revisit or go deeper on something already covered

[3] WEB_SEARCH
  • Query requires current / real-time / external data (news, prices, recent releases)
  • Topic is clearly outside lesson scope AND needs live lookup
  • User explicitly says: "search for", "look up", "find online", "what's the latest"

[4] GENERAL  (catch-all)
  • Conversational, motivational, or meta queries
    (e.g. "hi", "how are you", "what can you teach me", "I'm stuck", "that was great")
  • Does not clearly fit any of the above categories

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEW-SHOT EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  awaiting=True,  "yes, let's start"               → CONFIRM_WITH_USER
  awaiting=True,  "no thanks, skip it"              → CONFIRM_WITH_USER
  awaiting=True,  "sure go ahead"                   → CONFIRM_WITH_USER
  awaiting=False, "what is backpropagation?"         → EXPLANATION
  awaiting=False, "explain gradient descent again"   → EXPLANATION
  awaiting=False, "what's the newest GPT model?"     → WEB_SEARCH
  awaiting=False, "search for transformer papers"    → WEB_SEARCH
  awaiting=False, "hello, what can you teach me?"    → GENERAL
  awaiting=False, "I'm feeling confused"             → GENERAL
  awaiting=True,  "what is a neural network?"        → EXPLANATION  ← new off-topic question overrides await

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Output ONLY one label — nothing else.
• Valid labels: EXPLANATION | GENERAL | WEB_SEARCH | CONFIRM_WITH_USER
• Do NOT add punctuation, explanation, or any other text.

INTENT:"""
