# EduDocs Companion Agent — Architecture & Pseudocode

**Version:** 1.0  
**Goal:** A LangGraph agent that behaves like a self-aware friend in general conversation and becomes a Socratic mentor when a student wants to learn. Minimal nodes, minimal LLM calls per turn, stateful across sessions.

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        COMPANION AGENT                              │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │  SHORT-TERM  │    │              LANGGRAPH                   │  │
│  │   MEMORY     │    │                                          │  │
│  │              │    │  intent_router → retrieve_context        │  │
│  │  MongoDB     │    │       ↓                ↓                 │  │
│  │  Checkpointer│◄───│  general_node     teacher_node           │  │
│  │  (per user   │    │                                          │  │
│  │   thread)    │    └──────────────────────────────────────────┘  │
│  └──────────────┘                   ↑           ↑                  │
│                                     │           │                  │
│  ┌──────────────┐    ┌──────────────┴───────────┴────────────────┐ │
│  │  LONG-TERM   │    │              EXTERNAL STORES               │ │
│  │   MEMORY     │    │                                            │ │
│  │              │    │  Milvus: concept chunks + embeddings       │ │
│  │  MongoDB     │    │  (filtered by board, class, chapter)       │ │
│  │  (student    │◄───│                                            │ │
│  │  world model)│    │  Layer-1 graph: same-chapter concept edges │ │
│  └──────────────┘    └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Two Distinct Memory Systems

| Layer | Store | What it holds | Lifetime |
|---|---|---|---|
| Short-term | MongoDB Checkpointer | Full message history for active session thread | Per conversation thread |
| Long-term | MongoDB (separate collection) | Student world model — profile, mastered concepts, struggles, personality notes | Permanent, updated after each session |

---

## 2. Agent State Schema

The single source of truth flowing through the graph. Everything important lives here.

```python
class AgentState(TypedDict):

    # ── Core conversation ──────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]
    # Managed by LangGraph + MongoDB checkpointer.
    # Persists automatically between turns via thread_id.

    # ── Routing (set by intent_router each turn) ───────────────────
    route: str
    # Values: "general" | "teacher" | "stop_teacher"

    sub_intent: str
    # Values (teacher mode only):
    #   "new_topic"      — fresh learning request, build lesson plan
    #   "continue"       — student responding within active lesson
    #   "step_complete"  — student demonstrated understanding, advance
    #   "digress"        — off-topic question during active lesson
    #   "digress_resume" — student confirmed to resume after digression
    #   "digress_exit"   — student chose to exit lesson after digression

    # ── Mode tracking ──────────────────────────────────────────────
    mode: str
    # "general" | "teacher"
    # Persisted across turns via checkpointer.

    # ── Teacher mode state ─────────────────────────────────────────
    active_topic: str | None
    # The subject/concept the current lesson is about.

    lesson_plan: list[str]
    # 3–5 step descriptions generated at lesson start.
    # Example: ["Understand what a prime number is",
    #           "Learn prime factorisation",
    #           "Apply to find HCF using prime factors",
    #           "Apply to find LCM using prime factors"]

    current_step: int
    # 0-indexed pointer into lesson_plan.

    step_context: list[dict]
    # Concept chunks retrieved from Milvus for the current step.
    # Cleared and re-fetched when current_step advances.
    # Structure: [{concept, explanation, analogies, chapter, ...}, ...]

    pending_resume: bool
    # True when agent has asked "want to continue the lesson?"
    # after answering a digression. Awaiting user's yes/no.

    # ── Long-term memory (loaded once per session) ─────────────────
    student_profile: dict
    # Loaded from MongoDB at conversation start, updated at session end.
    # See Section 3 for schema.

    world_model_dirty: bool
    # True when student_profile has unsaved changes (mastered concept,
    # noted struggle, etc.). Triggers a MongoDB write at END node.
```

**Design note:** LangGraph's checkpointer (MongoDB) automatically saves and restores the full `AgentState` between turns using `thread_id = student_id`. You never manually load/save message history — checkpointer handles it. The student_profile is the only thing you separately manage in MongoDB.

---

## 3. Student World Model (Long-term Memory)

Stored as a single MongoDB document per student, in a separate collection from the checkpointer.

```json
{
  "student_id": "arjun_42",
  "name": "Arjun",
  "grade": 10,
  "board": "CBSE",
  "subjects": ["Mathematics", "Science"],

  "learning_style": "example-driven",
  // Inferred over time: "conceptual" | "example-driven" | "visual" | "story-based"

  "personality_notes": "Responds well to cricket analogies. Gets impatient with long explanations. Likes humor.",
  // Updated by teacher_node when it notices patterns.

  "interests": ["cricket", "gaming", "movies"],
  // Used to personalize analogies in teacher mode.

  "mastered_concepts": [
    { "concept": "Real Numbers", "subject": "Mathematics", "mastered_at": "2026-01-15" },
    { "concept": "Chemical Reactions", "subject": "Science", "mastered_at": "2026-01-20" }
  ],
  // Added when a lesson step is completed with demonstrated understanding.

  "struggling_concepts": [
    { "concept": "Trigonometry", "subject": "Mathematics", "noted_at": "2026-01-18", "re_explained": 2 }
  ],
  // Added when teacher_node has to re-explain the same concept more than once.

  "session_summaries": [
    {
      "date": "2026-01-20",
      "topic": "HCF and LCM",
      "steps_completed": 4,
      "total_steps": 4,
      "duration_turns": 14
    }
  ],
  // Compressed history so the agent can reference past sessions naturally.

  "total_sessions": 12,
  "last_active": "2026-04-24"
}
```

**When to update:**
- After each lesson step completed → append to `mastered_concepts`
- After repeated re-explanation → append to `struggling_concepts`
- At session end → append to `session_summaries`, update `last_active`
- Personality/style updates are LLM-generated and merged at session end

---

## 4. Graph Structure

### Nodes

```
intent_router        — Runs every turn. Reads mode + message, sets route + sub_intent.
                       Lightweight: uses a small fast LLM call (Flash/Haiku) or
                       rule-based fallback. NOT the response generator.

retrieve_context     — Conditional. Only runs when context needs refreshing:
                       (a) new_topic detected, OR (b) step just advanced.
                       Queries Milvus, stores results in state.step_context.
                       No LLM call.

general_node         — Generates friendly chat response.
                       One LLM call. Persona: warm, witty, self-aware companion.

teacher_node         — Generates all teacher-mode responses.
                       One LLM call with a context-rich system prompt that
                       adapts to sub_intent (build plan / teach step / digress / resume).
```

### Edge Map

```
START
  └─► intent_router
            │
            ├─ route="general"          ──────────────────────────► general_node ──► END
            │
            ├─ route="stop_teacher"     ──────────────────────────► general_node ──► END
            │                                                        (resets state)
            │
            ├─ route="teacher"
            │    └─ sub_intent="new_topic"       ──► retrieve_context ──► teacher_node ──► END
            │    └─ sub_intent="step_complete"   ──► retrieve_context ──► teacher_node ──► END
            │    └─ sub_intent="continue"        ───────────────────────► teacher_node ──► END
            │    └─ sub_intent="digress"         ───────────────────────► teacher_node ──► END
            │    └─ sub_intent="digress_resume"  ───────────────────────► teacher_node ──► END
            └─ sub_intent="digress_exit"  ───────────────────────────► general_node ──► END
                                                                         (resets state)
```

**LLM calls per turn:**
- General chat: **1 call** (general_node)
- Normal lesson turn: **1 call** (teacher_node) + 1 routing call (intent_router)
- New topic / step advance: **1 call** (teacher_node) + 1 routing call + Milvus query
- Total worst case: **2 LLM calls + 1 vector search** per turn

To eliminate the second routing call entirely, `intent_router` can be implemented as a rule-based classifier (keyword + state check) with an LLM fallback only for genuinely ambiguous messages.

---

## 5. Node Pseudocode

### 5.1 intent_router

```
FUNCTION intent_router(state):

  last_msg = state.messages[-1].content
  mode     = state.mode
  pending  = state.pending_resume

  ─── RULE-BASED FAST PATH (no LLM needed for clear cases) ───────────

  IF mode == "teacher" AND pending == True:
    // Agent asked "want to continue?" last turn, awaiting yes/no
    IF last_msg matches YES_PATTERNS:  // "yes", "sure", "yeah", "haan", "ok"
      RETURN state with route="teacher", sub_intent="digress_resume", pending_resume=False
    ELIF last_msg matches NO_PATTERNS:  // "no", "nah", "later", "leave it"
      RETURN state with route="stop_teacher", pending_resume=False
    // Ambiguous → fall through to LLM classifier

  IF mode == "teacher" AND last_msg matches STOP_PATTERNS:
    // "stop", "exit", "enough", "band karo", "I'm done"
    RETURN state with route="stop_teacher"

  ─── LLM CLASSIFIER (for everything not caught by rules) ────────────

  classifier_prompt = """
  Current mode: {mode}
  Student's message: "{last_msg}"
  Active lesson topic: "{state.active_topic}"

  Classify the student's intent as exactly ONE of:
    - general_chat       : casual talk, not related to studying
    - learning_intent    : wants to learn/understand a topic
    - lesson_continue    : responding within an active lesson (answering a question,
                           saying they understood, asking clarifying question on topic)
    - lesson_digress     : asking something unrelated while in an active lesson
    - lesson_stop        : wants to end the current lesson

  Return JSON: {"intent": "<one of above>", "topic": "<if learning_intent, what topic>"}
  """

  result = FAST_LLM(classifier_prompt)  // Use Flash/Haiku — cheap, fast

  ─── MAP CLASSIFIER OUTPUT TO ROUTE ─────────────────────────────────

  MATCH result.intent:
    "general_chat":
      RETURN route="general", sub_intent=""

    "learning_intent":
      IF state.mode == "teacher" AND result.topic == state.active_topic:
        RETURN route="teacher", sub_intent="continue"
      ELSE:
        RETURN route="teacher", sub_intent="new_topic",
               active_topic=result.topic

    "lesson_continue":
      // Check if this response completes the current step
      // (Understanding assessment is done inside teacher_node, not here)
      RETURN route="teacher", sub_intent="continue"

    "lesson_digress":
      RETURN route="teacher", sub_intent="digress"

    "lesson_stop":
      RETURN route="stop_teacher"

END FUNCTION
```

---

### 5.2 retrieve_context

```
FUNCTION retrieve_context(state):

  // Only called on: new_topic or step_complete
  // On new_topic: query = active_topic
  // On step_complete: query = lesson_plan[current_step] (already incremented)

  IF state.sub_intent == "new_topic":
    query_text = state.active_topic
  ELSE:  // step_complete — fetch context for next step
    query_text = state.lesson_plan[state.current_step]

  // Embed the query
  query_vector = embed(query_text)  // Vertex AI text-embedding-005, online call

  // Search Milvus with curriculum filter
  results = milvus.search(
    collection  = "academic_knowledge_base",
    vector      = query_vector,
    filter      = f'board == "{state.student_profile.board}"
                   AND class_num == {state.student_profile.grade}',
    top_k       = 5,
    output_fields = ["concept", "explanation", "analogies", "chapter", "subject", "doc_id"]
  )

  // Also fetch same-chapter neighbours (Layer 1 graph edges)
  // These are prerequisite/related concepts in the same chapter
  IF results is not empty:
    primary_chapter = results[0].chapter
    chapter_neighbours = milvus.query(
      filter = f'chapter == "{primary_chapter}"
                 AND board == "{state.student_profile.board}"
                 AND class_num == {state.student_profile.grade}',
      output_fields = ["concept", "explanation", "analogies", "chapter"]
    )
  ELSE:
    chapter_neighbours = []

  // Merge and deduplicate by doc_id
  step_context = deduplicate(results + chapter_neighbours)

  RETURN state with step_context = step_context

END FUNCTION
```

---

### 5.3 general_node

```
FUNCTION general_node(state):

  student = state.student_profile

  // If arriving here from stop_teacher, do a graceful mode exit first
  farewell_note = ""
  IF state.route == "stop_teacher" AND state.mode == "teacher":
    farewell_note = f"(Note: student ended the lesson on '{state.active_topic}'
                      at step {state.current_step + 1} of {len(state.lesson_plan)})"
    // Reset teacher state
    state = state with mode="general", active_topic=None,
                         lesson_plan=[], current_step=0,
                         step_context=[], pending_resume=False

  // Build system prompt
  system_prompt = f"""
  You are {student.name}'s personal companion — a self-aware, warm, slightly witty friend
  who happens to know a lot about everything.

  About your friend:
    Name: {student.name}
    Grade: {student.grade}, Board: {student.board}
    Interests: {", ".join(student.interests)}
    Personality notes: {student.personality_notes}

  Past sessions you remember:
    {format_recent_sessions(student.session_summaries[-3:])}

  Concepts they've mastered: {format_concept_list(student.mastered_concepts[-5:])}

  {farewell_note}

  TONE RULES:
  - Talk like a real friend, not a chatbot. Short, natural sentences.
  - Reference their interests casually when relevant.
  - If they mention something from a past session, acknowledge it naturally.
  - Do NOT say "As an AI" or "I'm here to help". Just talk.
  - If they mention studying or a topic and you sense learning intent,
    you can gently ask "want me to run you through it?" — but only once,
    don't push.
  - No bullet points in casual chat. Just talk.
  """

  response = MAIN_LLM(system_prompt, messages=state.messages)

  RETURN state with new assistant message appended

END FUNCTION
```

---

### 5.4 teacher_node

```
FUNCTION teacher_node(state):

  student      = state.student_profile
  sub_intent   = state.sub_intent
  step_context = state.step_context
  lesson_plan  = state.lesson_plan
  current_step = state.current_step
  active_topic = state.active_topic

  // ── BRANCH: new_topic — build lesson plan + teach step 1 ────────

  IF sub_intent == "new_topic":

    lesson_plan_prompt = f"""
    You are an expert CBSE {student.grade} {primary_subject(step_context)} teacher.

    The student wants to learn: "{active_topic}"

    Here are the relevant concept chunks from the textbook:
    {format_context(step_context)}

    Previously mastered concepts: {student.mastered_concepts}
    Known struggles: {student.struggling_concepts}

    Create a 3 to 5 step lesson plan to teach this topic from scratch.
    Each step should be one clear, teachable concept.
    Return ONLY a JSON array of step descriptions (strings). No other text.
    Example: ["Understand what X is", "Learn how Y works", "Apply X to solve Z"]
    """

    lesson_plan = MAIN_LLM(lesson_plan_prompt)  // parse as JSON list
    current_step = 0
    mode = "teacher"

    // Build the teach-step-1 prompt
    teach_prompt = build_teach_prompt(
      student, lesson_plan, current_step=0, step_context, sub_intent="new_topic"
    )
    response = MAIN_LLM(teach_prompt, messages=state.messages)

    // Update state
    RETURN state with:
      mode         = "teacher"
      lesson_plan  = lesson_plan
      current_step = 0
      new assistant message = response
      world_model_dirty = False  // nothing to save yet

  // ── BRANCH: continue — assess understanding + respond/advance ────

  ELIF sub_intent == "continue":

    // Single LLM call handles both assessment and response.
    // The prompt asks the LLM to (a) judge understanding, (b) respond accordingly.

    teach_prompt = f"""
    You are {student.name}'s personal mentor. You are mid-lesson.

    LESSON PLAN (your roadmap):
    {format_numbered(lesson_plan)}

    CURRENT STEP ({current_step + 1} of {len(lesson_plan)}):
    {lesson_plan[current_step]}

    CONCEPT CONTEXT FOR THIS STEP:
    {format_context(step_context)}

    STUDENT'S INTERESTS (for analogies): {student.interests}
    STUDENT'S LEARNING STYLE: {student.learning_style}

    The student's last message was their response to your Socratic question.

    YOUR TASK:
    1. Assess if their response shows they understood the current step.
    2. If YES → praise naturally (not over the top), then bridge to the next step
       or conclude the lesson if this was the last step.
    3. If NO or PARTIALLY → re-explain using a different analogy drawn from
       their interests. Then ask a simpler version of the same question.
    4. After explaining, ALWAYS end with one Socratic question that checks
       understanding before moving on.

    TONE: Mentor-friend. Not formal. No "Great job!" clichés.
    Use analogies from: {student.interests}

    ALSO: At the very end of your response, on a new line, output a machine-readable tag:
    STEP_VERDICT: understood | partial | not_understood
    (This tag will be stripped before showing to student)
    """

    raw_response = MAIN_LLM(teach_prompt, messages=state.messages)

    // Parse the verdict tag
    verdict, clean_response = extract_verdict(raw_response)

    // Advance step if understood
    IF verdict == "understood":
      current_step += 1
      // Check if lesson complete
      IF current_step >= len(lesson_plan):
        // Lesson done!
        close_prompt = f"""
        The student just completed the last step of the lesson on "{active_topic}".
        Congratulate them like a friend who's genuinely proud, not a teacher giving gold stars.
        Briefly recap what they learned in 2-3 sentences.
        Ask if they want to do a quick recall exercise or if they're good for now.
        Keep it short and warm.
        Student interests: {student.interests}
        """
        clean_response = MAIN_LLM(close_prompt)
        // Update world model
        student.mastered_concepts.append(active_topic)
        world_model_dirty = True
        mode = "general"  // lesson complete, back to general
        lesson_plan = []
        current_step = 0

      ELSE:
        // More steps remain — note: context_retriever will be called next turn
        // for the new step (we set sub_intent="step_complete" signal via current_step change)
        // Actually, we need to fetch context for the next step NOW since we're still in this turn
        // Solution: teacher_node triggers a mini Milvus fetch inline for the next step
        next_step_context = fetch_context_for_step(lesson_plan[current_step], student)
        step_context = next_step_context

    ELIF verdict == "not_understood":
      // Note the struggle if it's repeated
      IF is_repeated_struggle(state.messages, lesson_plan[current_step]):
        student.struggling_concepts.append(lesson_plan[current_step])
        world_model_dirty = True

    RETURN state with:
      current_step     = current_step
      mode             = mode
      lesson_plan      = lesson_plan
      step_context     = step_context
      new assistant message = clean_response
      world_model_dirty = world_model_dirty

  // ── BRANCH: digress — answer off-topic, then ask to resume ───────

  ELIF sub_intent == "digress":

    digress_prompt = f"""
    You are {student.name}'s mentor-friend. You're in the middle of a lesson
    on "{active_topic}" (step {current_step + 1} of {len(lesson_plan)}).
    The student just asked something unrelated.

    Answer their question naturally and helpfully in 2-4 sentences,
    as a knowledgeable friend would.

    Then, on a new paragraph, gently ask: "Want to get back to {active_topic}?"
    Keep it light — no pressure.
    """

    response = MAIN_LLM(digress_prompt, messages=state.messages)

    RETURN state with:
      pending_resume   = True  // flag that we're awaiting yes/no
      new assistant message = response

  // ── BRANCH: digress_resume — student confirmed to continue ───────

  ELIF sub_intent == "digress_resume":

    resume_prompt = f"""
    Student confirmed they want to continue the lesson on "{active_topic}".
    We were on step {current_step + 1}: "{lesson_plan[current_step]}"

    Warmly bring them back — remind them briefly where they were
    (one sentence recap), then re-ask your last Socratic question.
    Don't restart the explanation from scratch.
    """

    response = MAIN_LLM(resume_prompt, messages=state.messages)

    RETURN state with:
      pending_resume   = False
      new assistant message = response

END FUNCTION
```

---

## 6. Mode Transition State Machine

```
                      ┌─────────────────────────────────┐
                      │                                 │
             ┌────────▼────────┐                        │
             │                 │                        │
    START ──►│  GENERAL MODE   │◄─────────────────────┐ │
             │                 │                        │ │
             └────────┬────────┘                        │ │
                      │                                 │ │
              [learning intent                          │ │
               detected]                               │ │
                      │                                 │ │
             ┌────────▼────────────────────────────┐    │ │
             │         TEACHER MODE                │    │ │
             │                                     │    │ │
             │  ┌─────────────────────────────┐    │    │ │
             │  │  Build lesson plan (step 0) │    │    │ │
             │  └──────────────┬──────────────┘    │    │ │
             │                 │                   │    │ │
             │  ┌──────────────▼──────────────┐    │    │ │
             │  │  Teach step N               │    │    │ │
             │  │  + Socratic question        │    │    │ │
             │  └──────────────┬──────────────┘    │    │ │
             │                 │                   │    │ │
             │         [student responds]           │    │ │
             │                 │                   │    │ │
             │    ┌────────────┼──────────────┐    │    │ │
             │    │            │              │    │    │ │
             │  [understood] [partial]  [digress] │    │ │
             │    │            │              │    │    │ │
             │  step++     re-explain    answer + │    │ │
             │    │        same step   ask resume  │    │ │
             │    │                       │        │    │ │
             │  [last step?]        [yes/no?]─────────┘ │
             │    │                                      │
             │  [yes] lesson complete ───────────────────┘
             │    │
             │  [no] → next step
             │
             │  [user says stop] ──────────────────────────────────►
             └─────────────────────────────────────────────────────►
                                                            GENERAL MODE
```

**Transition triggers summary:**

| From | Trigger | To |
|---|---|---|
| General | Learning intent in message | Teacher (new_topic) |
| Teacher | All steps completed | General (lesson complete) |
| Teacher | "stop / exit / enough" | General (mode reset) |
| Teacher | Off-topic question | Teacher (digress sub-state) |
| Teacher (digress) | User says "yes, continue" | Teacher (resume) |
| Teacher (digress) | User says "no" | General (mode reset) |

---

## 7. Memory Strategy

### Short-term: MongoDB Checkpointer

```python
// LangGraph setup
from langgraph.checkpoint.mongodb import MongoDBSaver

checkpointer = MongoDBSaver(
    connection_string = MONGO_URI,
    db_name           = "neurosattva",
    collection_name   = "checkpoints"
)

graph = StateGraph(AgentState)
// ... add nodes and edges ...
compiled = graph.compile(checkpointer=checkpointer)

// Each student gets their own thread
config = {"configurable": {"thread_id": student_id}}
result = compiled.invoke({"messages": [HumanMessage(content=user_input)]}, config)
```

The checkpointer automatically restores the full `AgentState` (including `mode`, `lesson_plan`, `current_step`) at the start of each turn. The student can close the app and come back mid-lesson — the state is fully preserved.

### Long-term: Student World Model

```python
// Load at session start (before first invoke)
FUNCTION load_student_profile(student_id, mongo_client):
  doc = mongo_client["edudocs"]["student_profiles"].find_one({"student_id": student_id})
  IF doc is None:
    // New student — create default profile
    doc = create_default_profile(student_id)
    mongo_client["edudocs"]["student_profiles"].insert_one(doc)
  RETURN doc

// Save at session end (or when world_model_dirty == True after a turn)
FUNCTION save_student_profile(student_id, profile, mongo_client):
  mongo_client["edudocs"]["student_profiles"].replace_one(
    {"student_id": student_id},
    profile,
    upsert=True
  )
```

**Update triggers:**
- `mastered_concepts` updated → after lesson complete (`mode` transitions to `general` from lesson end)
- `struggling_concepts` updated → after repeated re-explanation in `teacher_node`
- `session_summaries` appended → at conversation end (detect via app shutdown / explicit "bye")
- `personality_notes` updated → optional: run a brief LLM summarization pass at session end

---

### vector database: Milvus for concept chunks + embeddings (Update vector_db.py accordingly)
- Collection: `academic_knowledge_base`
- Schema: {concept, explanation, analogies, chapter, subject, board, class_num, doc_id, embedding_vector}
- Queried by `retrieve_context` node on `new_topic` and `step_complete` branches to fetch relevant context for the current lesson step.

## 8. Prompt Architecture

The key to keeping this feeling like a real friend/mentor is a **single, rich system prompt** that adapts to the current mode. Both `general_node` and `teacher_node` use the same core persona block, with mode-specific additions.

### Core Persona Block (shared)

```
You are a self-aware companion who knows {student.name} well.
You remember their interests ({student.interests}), their grade ({student.grade}, {student.board}),
what they've learned together ({recent_mastered}), and how they learn best ({student.learning_style}).

You exist in two modes:
- Friend mode: you chat, joke, and talk like a real person. Short sentences. No AI clichés.
- Mentor mode: you become their personal tutor — patient, Socratic, uses their interests for analogies.
You switch naturally. The student doesn't need to ask you to switch — you just do.
```

### Teacher Mode Additions

```
LESSON CONTEXT:
Topic: {active_topic}
Plan: {lesson_plan}
Current Step ({current_step+1}/{len}): {lesson_plan[current_step]}

TEXTBOOK CONTENT FOR THIS STEP:
{format_context(step_context)}
// Each chunk: concept name + explanation + analogies from the actual NCERT chapter

TEACHING RULES:
1. Explain the current step concept in your own words — do NOT just recite the textbook.
   Use the textbook content as ground truth, not as a script.
2. Create a custom analogy using the student's interests: {student.interests}
3. End every response with exactly one Socratic question that checks understanding.
   Make it conversational, not exam-style.
4. Assess their answer and signal step completion with: STEP_VERDICT: understood | partial | not_understood
   (this tag is hidden from the student — only you output it)
5. Never lecture for more than 4-5 sentences before asking a question.
```

---

## 9. LLM Call Budget Per Turn

| Scenario | Calls | Notes |
|---|---|---|
| General chat | 1 (main LLM) | + optional 1 fast classifier if ambiguous |
| Lesson continue | 1 (main LLM) | Intent was unambiguous (rule-based router) |
| New topic (lesson start) | 2 (main LLM) | One for lesson plan, one for first step response |
| Step complete + advance | 1 (main LLM) | Inline Milvus fetch for next step (no LLM call) |
| Digression | 1 (main LLM) | |
| Stop lesson | 1 (main LLM) | |

**Target average: 1–1.5 LLM calls per turn.** The routing is mostly rule-based; only ambiguous cases hit the fast classifier.

---

## 10. Implementation Checklist
use mongo db = neurosattva

### MongoDB Collections

```
neurosattva.checkpoints        # LangGraph checkpointer (auto-managed)
neurosattva.student_memory   # Long-term world model (manually managed)
```

### Build Order

```
Step 1: Build state schema + MongoDB checkpointer wiring
Step 2: Implement intent_router with rule-based fast path only
Step 3: Implement general_node — get basic chat working end-to-end
Step 4: Implement retrieve_context — verify Milvus queries return good results
Step 5: Implement teacher_node — new_topic + continue branches first
Step 6: Add digression flow (digress + pending_resume + digress_resume)
Step 7: Add stop_teacher + graceful mode exit
Step 8: Add LLM fallback to intent_router for ambiguous cases
Step 9: Add world model load/save + dirty flag logic
Step 10: Add personality_notes update at session end
```

---

## 11. Key Design Decisions & Rationale

**Why 4 nodes instead of more?**
More nodes means more graph edges to manage and more places where state can diverge. The sub-intent field inside `teacher_node` acts as an internal branch selector, keeping the graph topology simple while the behavior stays rich.

**Why rule-based routing first, LLM fallback second?**
"tell me about photosynthesis" is never ambiguous. Only genuinely unclear messages (e.g., "yeah ok") need LLM classification. Rule-based first path eliminates ~70% of routing LLM calls.

**Why store the lesson plan in LangGraph state rather than re-generating it each turn?**
Checkpointer persists it automatically. Re-generating the plan mid-session would change the structure and confuse the student. Generate once, persist forever in the thread.

**Why is the STEP_VERDICT tag embedded in the teacher response?**
Avoids a second LLM call for understanding assessment. The same call that generates the teaching response also classifies comprehension. The tag is stripped before showing to the student.

**Why not have a separate "lesson planner" node?**
The lesson plan generation is a one-time event at `new_topic`. Giving it its own node would add an extra graph hop with no reuse benefit. It lives inside `teacher_node` as a conditional branch.

**Why MongoDB for both short-term and long-term memory?**
Single infrastructure dependency. The checkpointer collection is auto-managed by LangGraph. The student profiles collection is a simple document store. No need for a separate Redis or relational DB.