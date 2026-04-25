Honest answer: yes, there's a very sensible v1 that gets you 80% of the teaching quality with 20% of the infrastructure work. Let me think through what the real constraints are.

The reimagined architecture has three components that need pre-built data before they work: the concept graph (prerequisite edges, per-concept analogies, friction rates), the Student World Model schema with its five sub-components, and the Milvus collections restructured around concept nodes. None of that exists yet.

What you *do* have right now: Milvus with chunked subject content, MongoDB, and the existing vijayebhav_v2 agent structure. The question is what's the smartest bridge.

---

## The v1 philosophy: borrow the Pedagogical Reasoner's *thinking* without needing its data

The reimagined architecture's core insight — "ask what they need, not what they asked" — doesn't actually require a pre-built concept graph. That insight can be partially expressed through a smarter prompt and a lightweight MongoDB world model that builds itself from scratch as students use the system.Good, I have the full picture. Let me now think through the v1 design clearly.

---

## What v1 needs to be

The honest constraint is this: you have chunked content in Milvus and MongoDB. No concept graph, no prerequisite edges, no per-concept analogies. Building all that before you can ship is the wrong order — you want real students using the system *generating* the signals that will eventually populate the concept graph. The concept graph should emerge from usage, not precede it.

So v1's job is to be genuinely useful to students immediately while quietly collecting the raw data that v2 will need. Every design decision below serves both goals simultaneously.

---

## The v1 architecture: 4 nodes, 2 memory layers, 1 key insight borrowed from v2

The one insight worth borrowing immediately — even without the concept graph — is the **lightweight Student Memory Document**. It's not the full Student World Model, but it's a MongoDB document that grows over time and gives the LLM enough context to stop treating every session like a first meeting. This is the highest-ROI thing you can build right now.

Here's the full v1 architecture:

```
student turn
     │
     ▼
┌─────────────────────────────────────────────┐
│  context_loader  (no LLM)                  │  ← Load checkpoint + student memory doc
│  Milvus RAG retrieval                       │  ← Your existing chunked content
└─────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────┐
│  smart_router  (1 LLM call)                 │  ← classify + diagnose in ONE call
└─────────────────────────────────────────────┘
     │
     ├── small_talk ──────────────────────┐
     ├── qa (general or RAG-backed)        │
     ├── teach (explain + Socratic)        │   all → response_composer
     └── evaluate (score + advance)  ─────┘
                                          │
                                          ▼
                              ┌─────────────────────┐
                              │  response_composer   │  ← personality + TTS strip
                              │  + memory_updater    │  ← write to student doc (no LLM)
                              └─────────────────────┘
```

Four nodes total. The key difference from your current `core_agent.py` is the **smart_router** combines intent classification and a lightweight student diagnosis into a single LLM call, and the **memory_updater** inside the composer starts building the student document from day one.

---

## The Student Memory Document (v1 version)

This is the v1 approximation of the full Student World Model. Simple enough to implement today, structured enough that v2 can migrate it directly.

```python
# agent/memory/student_memory.py

# MongoDB collection: student_memory  (one doc per user)
# Created empty on first interaction, grows over sessions

EMPTY_STUDENT_MEMORY = {
    "user_id": None,
    "updated_at": None,

    # ── WHAT THEY KNOW (built from evaluation results) ──────────
    # topic_slug → { "state": "known"|"shaky"|"unseen",
    #                "last_seen": datetime,
    #                "attempts": int }
    # topic_slug is LLM-generated: e.g. "newtons_second_law"
    # This is the precursor to the full concept graph edge
    "topic_states": {},

    # ── WHERE THEY GOT STUCK (built from friction) ───────────────
    # topic_slug → { "attempts": int, "last_fail": datetime }
    # When attempts >= 2: re-explain with different RAG chunks
    "friction": {},

    # ── WHAT THEY CARE ABOUT (built from curiosity signals) ──────
    # Simple list — LLM extracts this from off-topic mentions
    "interests": [],

    # ── OPEN THREADS (questions not fully answered) ───────────────
    "open_threads": [],

    # ── LESSON STATE (session-persistent) ─────────────────────────
    # Cleared on session close if lesson is done
    # Preserved across sessions if lesson was interrupted
    "current_topic": None,
    "lesson_subtopics": [],   # LLM-generated, 3-5 items
    "lesson_step": 0,
    "awaiting_confirmation": False,

    # ── RAW SIGNALS (v2 will mine these for concept graph) ────────
    # Keep everything the LLM observes — even if v1 doesn't use it
    "session_log": []
    # [{ "session_id": ..., "date": ...,
    #    "topics_touched": [...],
    #    "curiosity_mentions": [...],
    #    "evaluations": [{"topic": ..., "correct": bool}] }]
}
```

The `session_log` at the bottom is the most important field for the v1→v2 migration. Every session appends a compact record. When you're ready to build the concept graph, you mine this log to find which topics cause friction, what curiosity signals repeat, and what prerequisite gaps your students actually hit. The graph grows from real usage rather than being hand-authored.

---

## AgentState (v1)

```python
# agent/state.py
from typing import TypedDict, Literal, Optional

class AgentState(TypedDict):
    # ── INPUT ──────────────────────────────────────────────
    query:           str
    session_id:      str
    user:            dict
    messages:        list       # LangGraph history
    language_code:   str

    # ── DEVICE CONFIG ──────────────────────────────────────
    difficulty_level: Literal["Beginner", "Intermediate", "Advanced"]
    response_type:    Literal["Concise", "Detailed"]
    learning_mode:    Literal["Normal", "Strict"]

    # ── STUDENT MEMORY (loaded from MongoDB) ───────────────
    student_memory:   dict      # full StudentMemory doc
    memory_summary:   str       # ≤4 sentence prompt injection

    # ── RAG ────────────────────────────────────────────────
    retrieved_chunks: list[str] # from Milvus

    # ── ROUTING ────────────────────────────────────────────
    intent: Literal["small_talk", "qa", "teach", "evaluate"]
    topic_slug:      Optional[str]   # e.g. "newtons_second_law"
    topic_name:      Optional[str]   # e.g. "Newton's Second Law"
    diagnosis:       Optional[str]   # why this routing decision

    # ── LESSON STATE (mirrors student_memory for this turn) ─
    current_topic:        Optional[str]
    lesson_subtopics:     list[str]
    lesson_step:          int
    awaiting_confirmation: bool

    # ── MEMORY DELTA (written by response_composer) ─────────
    # Structured diff — updater applies this to MongoDB doc
    memory_delta:    dict

    # ── OUTPUT ─────────────────────────────────────────────
    agent_output:    str
    last_response:   str
```

---

## The 4 nodes

### Node 1: `context_loader` (no LLM)

```python
# agent/nodes/context_loader.py

async def run(state: AgentState) -> AgentState:

    user = state["user"]

    # 1. Load device config
    config = await db.device_config.find_one({"user_id": user["_id"]})
    state["difficulty_level"] = config.get("difficulty_level", "Intermediate")
    state["response_type"]    = config.get("response_type",    "Detailed")
    state["learning_mode"]    = config.get("learning_mode",    "Normal")

    # 2. Load student memory doc (or empty if first time)
    mem = await db.student_memory.find_one({"user_id": user["_id"]})
    if not mem:
        mem = {**EMPTY_STUDENT_MEMORY, "user_id": user["_id"]}
    state["student_memory"] = mem

    # 3. Build memory summary for prompt injection
    state["memory_summary"] = build_memory_summary(mem)

    # 4. Mirror lesson state from memory into top-level state
    state["current_topic"]         = mem.get("current_topic")
    state["lesson_subtopics"]      = mem.get("lesson_subtopics", [])
    state["lesson_step"]           = mem.get("lesson_step", 0)
    state["awaiting_confirmation"] = mem.get("awaiting_confirmation", False)

    # 5. RAG — retrieve from Milvus using query
    # Your existing chunked content is used directly here
    state["retrieved_chunks"] = await milvus_search(
        query=state["query"],
        top_k=4,
        # Filter by student's grade/board if your chunks have metadata
        filters={"grade": user.get("grade"), "board": user.get("board")}
    )

    return state


def build_memory_summary(mem: dict) -> str:
    """
    Compress student memory into ≤4 sentences for prompt injection.
    This is the v1 equivalent of the full summariser.
    """
    parts = []

    # Shaky topics (top 3)
    shaky = [slug for slug, s in mem.get("topic_states", {}).items()
             if s["state"] == "shaky"][:3]
    if shaky:
        parts.append(f"Topics still shaky: {', '.join(shaky)}.")

    # Friction (most attempted)
    friction = sorted(mem.get("friction", {}).items(),
                      key=lambda x: x[1]["attempts"], reverse=True)[:1]
    if friction:
        slug, f = friction[0]
        parts.append(f"{slug} has been attempted {f['attempts']} times.")

    # Interests
    if mem.get("interests"):
        parts.append(f"Student shows interest in: {mem['interests'][0]}.")

    # Open threads
    open_ = [t for t in mem.get("open_threads", []) if not t.get("resolved")]
    if open_:
        parts.append(f"Unresolved question: '{open_[0]['question']}'")

    return " ".join(parts) if parts else "No prior learning history yet."
```

---

### Node 2: `smart_router` (1 LLM call)

This is where v1 borrows the most from the reimagined architecture. Instead of a pure intent classifier, it does a light diagnosis in the same call — asking "what does this student actually need?" The difference is subtle in the prompt but significant in the output.

```python
# agent/nodes/smart_router.py

async def run(state: AgentState) -> AgentState:

    # Fast-path: if in active lesson, skip full classification
    if state.get("current_topic") and state.get("lesson_subtopics"):
        result = await llm.invoke_with_tool(
            prompt=build_lesson_context_prompt(state),
            tool_schema=LessonContextSchema
        )
        state["intent"] = result.intent  # "teach" or "evaluate"
    else:
        result = await llm.invoke_with_tool(
            prompt=build_routing_prompt(state),
            tool_schema=RoutingSchema
        )
        state["intent"]     = result.intent
        state["topic_slug"] = result.topic_slug
        state["topic_name"] = result.topic_name
        state["diagnosis"]  = result.diagnosis

    return state
```

**Routing prompt** — the diagnosis field is what makes this smarter than a plain classifier:

```
ROUTING_PROMPT = """
{persona}

WHAT YOU KNOW ABOUT THIS STUDENT:
{memory_summary}

STUDENT QUERY: "{query}"

Use the RoutingSchema tool. Fields:

intent: one of
  "small_talk"  — greeting, casual, off-topic personal
  "qa"          — factual question, wants a direct answer
  "teach"       — conceptual topic, deserves structured explanation
  "evaluate"    — student is answering a question you posed

topic_slug: snake_case topic identifier if applicable
  e.g. "newtons_second_law", "photosynthesis_light_reaction"
  This becomes the key in the student memory document.

topic_name: human-readable version of the topic

diagnosis: 1 sentence — what does this student ACTUALLY need right now?
  Look at memory_summary. If they have been struggling with a prerequisite,
  say so. If this is a topic they have shown shaky understanding of before,
  say so. If there is an open thread that this query relates to, say so.
  This is for your own reasoning — not shown to the student.

IMPORTANT: diagnosis should go BEYOND the query text.
  BAD:  "Student asked about Newton's laws."
  GOOD: "Student asked about F=ma but memory shows they are shaky on
         'force_basics' — may need to establish that first."
"""
```

**Lesson context prompt** — used when a lesson is already active:

```
LESSON_CONTEXT_PROMPT = """
{persona}

Active lesson: {current_topic}
Current subtopic: {lesson_subtopics[lesson_step]}
Awaiting student answer: {awaiting_confirmation is False and lesson_step > 0}

STUDENT SAYS: "{query}"

Use LessonContextSchema:

intent: "evaluate" if student is answering your question,
        "teach"    if student asked a clarification / new sub-question,
        "small_talk" if clearly off-topic (do not force into lesson)

is_exiting_lesson: true if student clearly wants to stop
repeat_requested: true if student said they didn't hear / understand
"""
```

---

### Node 3: `responder` (1 LLM call, 3 sub-paths)

Instead of 5 specialist nodes, v1 has one responder node that handles `qa`, `teach`, and `evaluate` with different prompts. Small talk is handled inline — zero LLM cost.

```python
# agent/nodes/responder.py

async def run(state: AgentState) -> AgentState:

    intent = state["intent"]

    # ── small_talk: regex fast-path ──────────────────────────
    if intent == "small_talk":
        state["agent_output"] = await llm.invoke(
            prompt=build_small_talk_prompt(state)
        )
        return state

    # ── qa: RAG-backed direct answer ─────────────────────────
    if intent == "qa":
        state["agent_output"] = await llm.invoke(
            prompt=build_qa_prompt(state)
        )
        # Offer lesson if topic is conceptual
        if state.get("topic_slug"):
            state["memory_delta"]["offer_lesson"] = state["topic_slug"]
        return state

    # ── teach: plan if no active lesson, explain if active ───
    if intent == "teach":
        if not state["lesson_subtopics"]:
            # First time teaching this topic — generate lesson plan
            plan = await llm.invoke_with_tool(
                prompt=build_lesson_plan_prompt(state),
                tool_schema=LessonPlanSchema
            )
            state["lesson_subtopics"]      = plan.subtopics
            state["lesson_step"]           = 0
            state["awaiting_confirmation"] = True
            state["current_topic"]         = state["topic_name"]
            # Set intro as output
            state["agent_output"] = await llm.invoke(
                prompt=build_lesson_intro_prompt(state, plan.subtopics)
            )
        else:
            # Active lesson — check friction, then explain
            topic_slug = state["topic_slug"] or state["current_topic"]
            friction   = state["student_memory"].get("friction", {})
            attempts   = friction.get(topic_slug, {}).get("attempts", 0)

            state["agent_output"] = await llm.invoke(
                prompt=build_explain_prompt(state, attempts)
            )
        return state

    # ── evaluate: score + always advance ─────────────────────
    if intent == "evaluate":
        result = await llm.invoke_with_tool(
            prompt=build_eval_prompt(state),
            tool_schema=EvalSchema
        )
        # Advance unconditionally
        state["lesson_step"] = state["lesson_step"] + 1
        state["agent_output"] = await llm.invoke(
            prompt=build_feedback_prompt(state, result)
        )
        # Write eval result into delta
        state["memory_delta"]["evaluation"] = {
            "topic_slug": state.get("topic_slug") or state["current_topic"],
            "correct":    result.is_correct,
            "step":       state["lesson_step"] - 1,
        }
        return state

    return state
```

**Key prompt — `build_explain_prompt`** — this is where the v1 re-analogise logic lives without needing the concept graph:

```
EXPLAIN_PROMPT = """
{persona}

WHAT YOU KNOW ABOUT THIS STUDENT:
{memory_summary}

TEACHING: {current_subtopic}
STEP: {lesson_step} of {total_steps}

RELEVANT CONTENT FROM KNOWLEDGE BASE:
{retrieved_chunks}

{"IMPORTANT: This student has attempted this concept " + str(attempts) +
 " times. The previous explanation did not fully land. " +
 "Use a COMPLETELY DIFFERENT approach — new analogy, new entry point, " +
 "simpler language. Do not repeat what was said before." if attempts >= 2 else ""}

INSTRUCTIONS:
1. Analogy first. Connect to something the student already knows.
2. Use {board}-specific examples where possible.
3. Formal definition only if difficulty is Intermediate or Advanced.
4. End with ONE Socratic question about this subtopic.
   Strict mode: always. Normal mode: only if natural.
5. Plain text only — no markdown, no bullets, no symbols.
"""
```

---

### Node 4: `response_composer` + `memory_updater` (1 LLM call + 0 LLM for memory)

```python
# agent/nodes/response_composer.py

async def run(state: AgentState) -> AgentState:

    # 1. Personality pass
    final = await llm.invoke(
        prompt=build_composer_prompt(state, state["agent_output"])
    )

    # 2. Strip TTS symbols
    final = strip_tts_symbols(final)

    # 3. Open thread check — surface if natural pause
    open_ = [t for t in state["student_memory"].get("open_threads", [])
             if not t.get("resolved")]
    if open_ and _is_natural_pause(state):
        hook = f"You asked before: '{open_[0]['question']}' — "
        final = hook + final
        state["memory_delta"]["resolve_thread"] = open_[0]["question"]

    state["last_response"] = final

    # 4. Update student memory doc — no LLM, pure Python
    await update_student_memory(state)

    return state


async def update_student_memory(state: AgentState):
    """
    Pure Python. Zero LLM calls. Writes memory_delta to MongoDB.
    """
    mem   = state["student_memory"]
    delta = state.get("memory_delta", {})
    user_id = state["user"]["_id"]

    # Update topic state from evaluation
    if "evaluation" in delta:
        ev = delta["evaluation"]
        slug = ev["topic_slug"]
        ts   = mem.setdefault("topic_states", {})
        prev = ts.get(slug, {"state": "unseen", "attempts": 0})

        if ev["correct"]:
            prev["attempts"] = prev.get("attempts", 0) + 1
            # Promote to known only after 2 correct answers
            if prev["attempts"] >= 2:
                prev["state"] = "known"
            else:
                prev["state"] = "shaky"
        else:
            prev["state"] = "shaky"
            # Log friction
            fr = mem.setdefault("friction", {})
            entry = fr.setdefault(slug, {"attempts": 0})
            entry["attempts"] += 1
            entry["last_fail"] = datetime.utcnow().isoformat()

        ts[slug] = prev

    # Update lesson state
    mem["current_topic"]         = state["current_topic"]
    mem["lesson_subtopics"]      = state["lesson_subtopics"]
    mem["lesson_step"]           = state["lesson_step"]
    mem["awaiting_confirmation"] = state["awaiting_confirmation"]

    # Lesson complete → clear lesson state but keep topic_states
    if state["lesson_step"] >= len(state["lesson_subtopics"]) > 0:
        mem["current_topic"]    = None
        mem["lesson_subtopics"] = []
        mem["lesson_step"]      = 0

    # Resolve thread
    if "resolve_thread" in delta:
        for t in mem.get("open_threads", []):
            if t["question"] == delta["resolve_thread"]:
                t["resolved"] = True

    # Append to session_log (for v2 concept graph mining later)
    today_log = {
        "session_id": state["session_id"],
        "date":       datetime.utcnow().isoformat(),
        "topics_touched": [state.get("topic_slug")],
        "evaluations": [delta["evaluation"]] if "evaluation" in delta else [],
    }
    mem.setdefault("session_log", []).append(today_log)
    # Keep last 50 sessions only
    mem["session_log"] = mem["session_log"][-50:]

    mem["updated_at"] = datetime.utcnow().isoformat()

    await db.student_memory.find_one_and_update(
        {"user_id": user_id},
        {"$set": mem},
        upsert=True
    )
```

---

## The graph wiring

```python
# agent/graph.py

from langgraph.graph import StateGraph, END
from agent.nodes import context_loader, smart_router, responder, response_composer

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("context_loader",    context_loader.run)
    g.add_node("smart_router",      smart_router.run)
    g.add_node("responder",         responder.run)
    g.add_node("response_composer", response_composer.run)

    g.set_entry_point("context_loader")
    g.add_edge("context_loader",    "smart_router")
    g.add_edge("smart_router",      "responder")
    g.add_edge("responder",         "response_composer")
    g.add_edge("response_composer", END)

    return g.compile(checkpointer=get_mongo_saver())
```

Completely linear. No conditional edges in v1 — the routing logic is encoded in the `responder` node itself via the `intent` field. This makes debugging trivial and the graph easy to reason about.

---

## The migration path from v1 → v2

This is the most important thing to get right now. Every v1 design decision above was made with one eye on v2:

`topic_states` in the student memory doc maps directly to `knowledge_edges` in the Student World Model. Same concept, different field name. The migration is a rename + schema enrichment.

`friction` maps to `friction_log`. Add `analogies_tried[]` when you build v2.

`session_log` is the gold mine. Run a batch job over it when you're ready to seed the concept graph — the topics that appear in friction entries across many users are exactly the nodes that need prerequisite edges and multiple analogies.

`topic_slug` (LLM-generated) becomes `concept_id` in v2. They're the same thing — just add Milvus storage when you have the concept graph built.

The `smart_router`'s `diagnosis` field is doing a lightweight version of the Pedagogical Reasoner's work. When you build v2, you replace this single LLM call with the full reasoner that has the concept graph to traverse. The prompts are structurally identical — just enriched.

---

## LLM call budget comparison

| Scenario | v1 calls | v2 calls |
|---|---|---|
| Small talk | 1 (router) + 1 (composer) = 2 | 1 (reasoner) + 1 (composer) = 2 |
| Q&A | 1 (router) + 1 (responder) + 1 (composer) = 3 | 3 (same) |
| Teach (new topic) | 1 + 1 (plan) + 1 (explain) + 1 (composer) = 4 | 1 + 1 + 1 + 1 = 4 |
| Evaluate + advance | 1 + 1 (eval) + 1 (feedback) + 1 (composer) = 4 | same |
| Memory update | 0 (pure Python) | 0 (pure Python) |

Identical call budget. v2's advantage is qualitative, not quantitative — it makes better routing decisions because it has the concept graph, not because it makes more LLM calls.