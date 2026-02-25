from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from typing import TypedDict, Annotated, Literal
from app.agents.llm import LLM
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient
import os
from app.agents.agent_memory_controller import get_chat_history
from langchain_core.runnables import RunnableConfig
from app.agents.prompts import (
    QUERY_CLASSIFIER_PROMPT,
    GENERAL_ANSWER_PROMPT,
    BRIEF_ANSWER_PROMPT,
    LESSON_PLANNER_PROMPT,
    TUTOR_EXPLANATION_PROMPT,
    EVALUATOR_PROMPT,
    TOPIC_ANALYSIS_PROMPT,
    LESSON_COMPLETE_PROMPT,
    SMALL_TALK_PROMPT,
)
import logging
import operator
import re
import random
from app.agents.schemas import (
    QueryClassificationSchema,
    LessonPlanSchema,
    EvaluationSchema,
    TopicAnalysisSchema,
)
import json


logger = logging.getLogger(__name__)

llm = LLM().get_llm()
llm_with_classifier_tool = llm.bind_tools(tools=[QueryClassificationSchema])
llm_with_lesson_tool = llm.bind_tools(tools=[LessonPlanSchema])
llm_with_eval_tool = llm.bind_tools(tools=[EvaluationSchema])
llm_with_topic_analysis_tool = llm.bind_tools(tools=[TopicAnalysisSchema])

MAX_STEPS = 5

# ========================================
# SMALL TALK FAST PATH (Zero-overhead detection)
# ========================================

SMALL_TALK_PATTERNS = [
    r'^(hi|hello|hey|howdy|sup|yo)\b',
    r'^(good\s+)?(morning|afternoon|evening|night)',
    r"how\s+are\s+you",
    r"how'?s?\s+it\s+going",
    r"what'?s?\s+up",
    r"tell\s+me\s+a\s+joke",
    r'^(bye|goodbye|see\s+you|later|take\s+care)',
    r'^(thanks|thank\s+you)',
    r"^i'?m\s+(bored|tired|happy|sad|excited|good|fine|great|ok(?:ay)?)",
    r'^(haha|lol|lmao)',
    r'^who\s+are\s+you',
    r"^what('?s|\s+is)\s+your\s+name",
    r'^(nice|cool|awesome|great|wow)$',
    r"^you'?re?\s+(funny|cool|nice|great|awesome)",
]

# Patterns for detecting repeat/replay requests - fast path before LLM call
REPEAT_REQUEST_PATTERNS = [
    r"(couldn'?t|can'?t|could\s+not|did\s+not|didn'?t)\s+(hear|understand|catch|get)",
    r"(repeat|say\s+(that|it|this)\s+again)",
    r"(come\s+again|pardon|once\s+more|one\s+more\s+time)",
    r"what\s+(did|was)\s+you\s+(say|ask)",
    r"(say|tell|ask)\s+(that|it|me)\s+again",
    r"(again\s+please|please\s+again|please\s+repeat)",
    r"^again$",
    r"(can|could)\s+you\s+(repeat|say\s+(that|it)\s+again)",
    r"i\s+missed\s+(that|it|what\s+you\s+said)",
    r"what\s+(question|did\s+you\s+ask)",
    r"(speak|talk)\s+(louder|up)",
]

# Patterns for detecting confirmation (yes/no) for lesson offer
YES_PATTERNS = [
    r"^(yes|yeah|yep|yup|sure|ok(?:ay)?|absolutely|definitely|please|go\s+ahead|let'?s?\s+do\s+it|let'?s?\s+go|sounds?\s+good|why\s+not|of\s+course|i'?d?\s+(?:like|love)\s+(?:that|to))[\s!.]*$",
    r"^(break\s+it\s+down|explain\s+(?:it|in\s+detail)|teach\s+me|tell\s+me\s+more|go\s+ahead|i\s+want\s+to\s+learn)",
]

NO_PATTERNS = [
    r"^(no|nah|nope|not?\s+(?:really|now|thanks)|i'?m?\s+good|skip|never\s*mind|that'?s?\s+(?:enough|fine|okay|ok))[\s!.]*$",
    r"^(i\s+don'?t\s+(?:want|need)|no\s+thanks?|that'?s?\s+all)[\s!.]*$",
]


def is_small_talk(query: str) -> bool:
    """Fast rule-based detection of small talk queries. Zero LLM cost."""
    query_lower = query.strip().lower()
    # Small talk is typically short
    if len(query_lower.split()) <= 10:
        for pattern in SMALL_TALK_PATTERNS:
            if re.search(pattern, query_lower):
                return True
    return False


def is_repeat_request(query: str) -> bool:
    """Fast rule-based detection of repeat/replay requests. Zero LLM cost."""
    query_lower = query.strip().lower()
    if len(query_lower.split()) <= 15:
        for pattern in REPEAT_REQUEST_PATTERNS:
            if re.search(pattern, query_lower):
                return True
    return False


def is_yes(query: str) -> bool:
    """Fast detection of affirmative responses."""
    query_lower = query.strip().lower()
    for pattern in YES_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    return False


def is_no(query: str) -> bool:
    """Fast detection of negative responses."""
    query_lower = query.strip().lower()
    for pattern in NO_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    return False


def pick_filler_phrase(query: str) -> str:
    """Pick a short contextual filler phrase based on query type. Zero LLM cost."""
    if is_repeat_request(query):
        return random.choice([
            "Sure, one moment.",
            "Of course, let me repeat.",
            "No problem, here it is again.",
        ])
    if is_small_talk(query):
        return random.choice([
            "Hey!",
            "Hmm, let me think.",
        ])
    # Check if it looks like an answer (short, declarative)
    word_count = len(query.strip().split())
    if word_count <= 6:
        return random.choice([
            "Hmm, let me check.",
            "Okay, let me think about that.",
            "Alright, give me a moment.",
        ])
    # Longer input — likely a question or new topic
    return random.choice([
        "Interesting, let me think.",
        "Good question, give me a second.",
        "Let me think about that.",
        "Hmm, one moment.",
    ])


def handle_small_talk(query: str) -> str:
    """Handle casual conversation with a single fast LLM call. Bypasses entire graph."""
    prompt = SMALL_TALK_PROMPT.format(query=query)
    response = llm.invoke(prompt)
    return response.content

class AgentState(TypedDict):
    """The state of the guided learning agent."""
    query: str                    # the user's current query
    user: dict                    # user info
    messages: Annotated[list[BaseMessage], operator.add]
    mode: str                     # "general" or "explanation"
    topic: str                    # active lesson topic (empty in general mode)
    lesson_plan: list[str]        # list of subtopic steps
    lesson_step: int              # current step (1-indexed)
    last_action: str              # tracks what just happened for routing
    session_id: str
    awaiting_lesson_confirmation: bool  # True after brief_answer, waiting for yes/no
    pending_topic: str            # topic saved from classification, used if user says yes
    feedback: str                 # evaluator feedback to prepend to next explanation
    last_explanation: str         # last real lesson explanation (for repeat requests)

# Setup MongoDB checkpointer (for persistence/short-term memory)
checkpointer = MongoDBSaver(
    client=MongoClient(os.getenv("MONGODB_CONNECTION_STRING")),
    db_name="neurosattva"
)


# ========================================
# GRAPH NODES
# ========================================

def classify_query(state: AgentState) -> dict:
    """
    Entry node for general mode. Classifies query as 'general' or 'explanation'.
    Uses LLM with QueryClassificationSchema tool.
    """
    query = state.get('query', '')
    logger.info(f"Classifying query: {query[:60]}...")

    try:
        prompt = QUERY_CLASSIFIER_PROMPT.format(query=query)
        response = llm_with_classifier_tool.invoke(prompt)

        if response.tool_calls and len(response.tool_calls) > 0:
            data = response.tool_calls[0]['args']
            query_type = data.get('query_type', 'general')
            topic = data.get('topic', query)
            logger.info(f"Classification: type={query_type}, topic={topic}")

            return {
                "last_action": f"classified_{query_type}",
                "pending_topic": topic,
            }

        # Fallback: treat as general
        logger.warning("No tool call in classification, defaulting to general")
        return {"last_action": "classified_general", "pending_topic": query}

    except Exception as e:
        logger.error(f"Error in classify_query: {e}")
        return {"last_action": "classified_general", "pending_topic": query}


def general_answer(state: AgentState) -> dict:
    """
    Answers a general question directly. Single LLM call, no lesson mode.
    """
    query = state.get('query', '')
    logger.info(f"Generating general answer for: {query[:60]}...")

    try:
        prompt = GENERAL_ANSWER_PROMPT.format(query=query)
        response = llm.invoke(prompt)

        return {
            "messages": [AIMessage(content=response.content)],
            "last_action": "general_answered",
            "mode": "general",
        }
    except Exception as e:
        logger.error(f"Error in general_answer: {e}")
        return {
            "messages": [AIMessage(content="That's a great question! Let me know if you'd like me to explain further.")],
            "last_action": "general_answered",
            "mode": "general",
        }


def brief_answer_and_offer(state: AgentState) -> dict:
    """
    Gives a brief answer to an explanation-type query, then asks if user
    wants a detailed lesson breakdown.
    """
    query = state.get('query', '')
    topic = state.get('pending_topic', query)
    logger.info(f"Brief answer + offering lesson for: {topic[:60]}...")

    try:
        prompt = BRIEF_ANSWER_PROMPT.format(query=query, topic=topic)
        response = llm.invoke(prompt)

        return {
            "messages": [AIMessage(content=response.content)],
            "last_action": "offered_lesson",
            "awaiting_lesson_confirmation": True,
            "pending_topic": topic,
            "mode": "general",
        }
    except Exception as e:
        logger.error(f"Error in brief_answer_and_offer: {e}")
        return {
            "messages": [AIMessage(content="That's an interesting topic! Would you like me to break it down step by step?")],
            "last_action": "offered_lesson",
            "awaiting_lesson_confirmation": True,
            "pending_topic": topic,
            "mode": "general",
        }


def handle_lesson_confirmation(state: AgentState) -> dict:
    """
    Handles user's yes/no response to the lesson offer.
    Uses regex fast-path, no LLM call needed.
    """
    query = state.get('query', '')
    logger.info(f"Handling lesson confirmation: {query}")

    if is_yes(query):
        logger.info("User confirmed lesson -> entering explanation mode")
        return {
            "last_action": "confirmed_lesson",
            "awaiting_lesson_confirmation": False,
            "mode": "explanation",
        }
    elif is_no(query):
        logger.info("User declined lesson -> staying in general mode")
        msg = AIMessage(content="No problem at all! Feel free to ask me anything else whenever you are ready.")
        return {
            "messages": [msg],
            "last_action": "declined_lesson",
            "awaiting_lesson_confirmation": False,
            "pending_topic": "",
            "mode": "general",
        }
    else:
        # Ambiguous -- treat as a new query in general mode
        logger.info("Ambiguous confirmation response, treating as new query")
        return {
            "last_action": "ambiguous_confirmation",
            "awaiting_lesson_confirmation": False,
            "pending_topic": "",
            "mode": "general",
        }


def plan_lesson(state: AgentState) -> dict:
    """
    Generates a structured lesson plan with 3-5 subtopics.
    """
    topic = state.get('pending_topic', state.get('query', 'Unknown'))
    logger.info(f"Planning lesson for topic: {topic}")

    try:
        prompt = LESSON_PLANNER_PROMPT.format(topic=topic, max_steps=MAX_STEPS)
        response = llm_with_lesson_tool.invoke(prompt)

        if response.tool_calls and len(response.tool_calls) > 0:
            data = response.tool_calls[0]['args']
            refined_topic = data.get('topic', topic)
            steps = data.get('steps', [])

            # Ensure 3-5 steps
            if len(steps) < 3:
                steps = steps + [f"Additional aspect of {refined_topic}"] * (3 - len(steps))
            steps = steps[:MAX_STEPS]

            logger.info(f"Lesson plan: {len(steps)} subtopics for '{refined_topic}'")

            plan_msg = AIMessage(
                content=f"Great, I have planned a lesson on {refined_topic} with {len(steps)} sub-topics. Let us dive in!"
            )

            return {
                "topic": refined_topic,
                "lesson_plan": steps,
                "lesson_step": 1,
                "last_action": "planned",
                "messages": [plan_msg],
                "mode": "explanation",
                "pending_topic": "",
            }

        # Fallback
        logger.warning("No tool call in lesson planning, using fallback")
        return {
            "topic": topic,
            "lesson_plan": [
                f"Introduction to {topic}",
                f"Key concepts of {topic}",
                f"Practical applications of {topic}",
            ],
            "lesson_step": 1,
            "last_action": "planned",
            "messages": [AIMessage(content=f"Let us explore {topic} together!")],
            "mode": "explanation",
            "pending_topic": "",
        }

    except Exception as e:
        logger.error(f"Error in plan_lesson: {e}")
        return {
            "topic": topic,
            "lesson_plan": [f"Understanding {topic}"],
            "lesson_step": 1,
            "last_action": "planned",
            "messages": [AIMessage(content=f"Let us learn about {topic}!")],
            "mode": "explanation",
        }


def generate_explanation(state: AgentState) -> dict:
    """
    Explains the current subtopic and asks a follow-up question.
    """
    current_step = state.get('lesson_step', 1)
    lesson_plan = state.get('lesson_plan', [])
    topic = state.get('topic', 'the topic')

    logger.info(f"Generating explanation for subtopic {current_step}/{len(lesson_plan)}")

    try:
        step_content = lesson_plan[current_step - 1] if lesson_plan and current_step <= len(lesson_plan) else f"Step {current_step}"

        prompt = TUTOR_EXPLANATION_PROMPT.format(
            topic=topic,
            lesson_step=current_step,
            step_content=step_content,
            total_steps=len(lesson_plan),
        )

        response = llm.invoke(prompt)
        final_content = response.content

        # Prepend evaluator feedback from previous round if it exists
        previous_feedback = state.get('feedback', '')
        if previous_feedback:
            final_content = f"{previous_feedback}\n\n{final_content}"
            logger.info("Prepended feedback to explanation")

        return {
            "messages": [AIMessage(content=final_content)],
            "last_action": "explained",
            "feedback": "",
            "last_explanation": final_content,
        }

    except Exception as e:
        logger.error(f"Error in generate_explanation: {e}")
        return {
            "messages": [AIMessage(content=f"Let me tell you about this part of {topic}. What do you think?")],
            "last_action": "explained",
        }


def evaluate_response(state: AgentState) -> dict:
    """
    Evaluates the user's answer to the follow-up question.
    - Correct -> praise + move to next subtopic
    - Incorrect -> appreciate + explain correct answer + move to next subtopic
    NEVER loops/re-explains. Always advances.
    """
    messages = state.get('messages', [])
    user_messages = [m for m in messages if isinstance(m, HumanMessage)]

    if not user_messages:
        logger.warning("No user messages to evaluate")
        return {"last_action": "proceed"}

    latest_user_message = user_messages[-1].content
    last_agent_question = state.get('last_explanation', '') or "the previous question"

    logger.info(f"Evaluating: {latest_user_message[:50]}...")

    try:
        prompt = EVALUATOR_PROMPT.format(
            user_response=latest_user_message,
            agent_question=last_agent_question,
            topic=state.get('topic', 'the topic'),
        )

        response = llm_with_eval_tool.invoke(prompt)

        if response.tool_calls and len(response.tool_calls) > 0:
            data = response.tool_calls[0]['args']
            is_correct = data.get('is_correct', True)
            feedback = data.get('feedback', '')

            logger.info(f"Evaluation: is_correct={is_correct}")

            # ALWAYS proceed to next step
            current_step = state.get('lesson_step', 1)
            return {
                "lesson_step": current_step + 1,
                "last_action": "proceed",
                "feedback": feedback,
            }

        # Fallback: proceed
        logger.warning("No tool call in evaluation, defaulting to proceed")
        current_step = state.get('lesson_step', 1)
        return {
            "lesson_step": current_step + 1,
            "last_action": "proceed",
        }

    except Exception as e:
        logger.error(f"Error in evaluate_response: {e}")
        current_step = state.get('lesson_step', 1)
        return {
            "lesson_step": current_step + 1,
            "last_action": "proceed",
        }


def analyze_topic_context(state: AgentState) -> dict:
    """
    During explanation mode, analyzes user's message intent.
    Handles: answer, clarification, new_topic exit, small_talk, repeat.
    """
    messages = state.get('messages', [])
    topic = state.get('topic', '')
    lesson_step = state.get('lesson_step', 1)
    lesson_plan = state.get('lesson_plan', [])

    user_messages = [m for m in messages if isinstance(m, HumanMessage)]
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]

    if not user_messages or not topic:
        return {"last_action": "context_analyzed"}

    # Check if the last message is from the user
    last_message = messages[-1] if messages else None
    if isinstance(last_message, AIMessage):
        logger.info("Last message from AI, waiting for user response")
        return {"last_action": "waiting_for_response"}

    latest_user_query = user_messages[-1].content
    last_agent_message = state.get('last_explanation', '') or (ai_messages[-1].content if ai_messages else "")

    # FAST PATH: repeat requests
    if is_repeat_request(latest_user_query):
        logger.info("Repeat request detected (fast path)")
        if last_agent_message:
            prefix = random.choice([
                "Sure, let me repeat that. ",
                "No problem, here it is again. ",
                "Of course, I will say it again. ",
            ])
            return {
                "messages": [AIMessage(content=prefix + last_agent_message)],
                "last_action": "repeated",
            }
        return {
            "messages": [AIMessage(content="I do not have anything to repeat yet. Let us continue!")],
            "last_action": "repeated",
        }

    step_content = lesson_plan[lesson_step - 1] if lesson_plan and lesson_step <= len(lesson_plan) else ""

    logger.info(f"Analyzing topic context: {latest_user_query[:50]}...")

    try:
        prompt = TOPIC_ANALYSIS_PROMPT.format(
            current_topic=topic,
            current_step=lesson_step,
            total_steps=len(lesson_plan),
            step_content=step_content,
            last_agent_message=last_agent_message[:200],
            user_query=latest_user_query,
        )

        response = llm_with_topic_analysis_tool.invoke(prompt)

        if response.tool_calls and len(response.tool_calls) > 0:
            analysis = response.tool_calls[0]['args']
            intent = analysis.get('intent', 'answer')
            suggested_action = analysis.get('suggested_action', 'continue_lesson')

            logger.info(f"Topic analysis: intent={intent}, action={suggested_action}")

            if suggested_action == 'switch_topic':
                # User wants to exit lesson -> reset to general mode
                logger.info(f"User wants to exit lesson on '{topic}'")
                progress_msg = AIMessage(
                    content=f"Sure thing! We covered {lesson_step - 1} out of {len(lesson_plan)} sub-topics on {topic}. What would you like to know about?"
                )
                return {
                    "messages": [progress_msg],
                    "last_action": "exited_lesson",
                    "mode": "general",
                    "topic": "",
                    "lesson_plan": [],
                    "lesson_step": 0,
                    "last_explanation": "",
                    "feedback": "",
                }

            elif suggested_action == 'answer_and_continue':
                # Clarification question -- answer briefly and re-ask
                logger.info("Clarification question, answering and continuing")
                answer_prompt = f"""The student asked a clarification during a lesson on '{topic}'.
Answer briefly (1-2 sentences), then naturally re-ask the question you previously asked.

Clarification: {latest_user_query}
Your previous message: {last_agent_message[:300]}

Keep under 60 words. No special symbols. Plain text only."""
                answer_response = llm.invoke(answer_prompt)
                return {
                    "messages": [AIMessage(content=answer_response.content)],
                    "last_action": "answered_question",
                }

            elif suggested_action == 'politely_redirect':
                logger.info("Off-topic, redirecting to lesson")
                redirect_msg = AIMessage(
                    content=f"Interesting question! Let us finish our lesson on {topic} first though. We are on sub-topic {lesson_step} of {len(lesson_plan)}. Once done, I can help with anything else!"
                )
                return {
                    "messages": [redirect_msg],
                    "last_action": "redirected",
                }

            elif suggested_action == 'handle_small_talk':
                logger.info("Small talk during lesson")
                small_talk_response = handle_small_talk(latest_user_query)
                reminder = f" Anyway, we are on sub-topic {lesson_step} of {len(lesson_plan)} in our {topic} lesson. Ready to continue?"
                return {
                    "messages": [AIMessage(content=small_talk_response + reminder)],
                    "last_action": "small_talk_responded",
                }

            elif suggested_action == 'repeat_last_message':
                logger.info("Repeat request (LLM detected)")
                if last_agent_message:
                    prefix = random.choice(["Sure, let me repeat. ", "No problem. ", "Of course. "])
                    return {
                        "messages": [AIMessage(content=prefix + last_agent_message)],
                        "last_action": "repeated",
                    }
                return {
                    "messages": [AIMessage(content="Let us continue with our lesson!")],
                    "last_action": "repeated",
                }

            else:  # continue_lesson
                logger.info("User answering lesson question -> evaluate")
                return {"last_action": "context_analyzed"}

        logger.warning("No tool call in topic analysis, defaulting to continue")
        return {"last_action": "context_analyzed"}

    except Exception as e:
        logger.error(f"Error in analyze_topic_context: {e}")
        return {"last_action": "context_analyzed"}


def complete_lesson(state: AgentState) -> dict:
    """
    Called when all subtopics are covered. Resets to general mode.
    """
    topic = state.get('topic', 'this topic')
    lesson_plan = state.get('lesson_plan', [])
    total_steps = len(lesson_plan)
    feedback = state.get('feedback', '')

    logger.info(f"Completing lesson on '{topic}'")

    try:
        prompt = LESSON_COMPLETE_PROMPT.format(topic=topic, total_steps=total_steps)
        response = llm.invoke(prompt)
        completion_content = response.content

        # Prepend final evaluation feedback if present
        if feedback:
            completion_content = f"{feedback}\n\n{completion_content}"

        return {
            "messages": [AIMessage(content=completion_content)],
            "last_action": "lesson_completed",
            "mode": "general",
            "topic": "",
            "lesson_plan": [],
            "lesson_step": 0,
            "last_explanation": "",
            "feedback": "",
            "pending_topic": "",
        }

    except Exception as e:
        logger.error(f"Error in complete_lesson: {e}")
        return {
            "messages": [AIMessage(content=f"Great work completing the lesson on {topic}! Feel free to ask me anything.")],
            "last_action": "lesson_completed",
            "mode": "general",
            "topic": "",
            "lesson_plan": [],
            "lesson_step": 0,
        }


# ========================================
# ROUTING FUNCTIONS
# ========================================

def route_start(state: AgentState) -> Literal["handle_lesson_confirmation", "analyze_topic", "classify_query"]:
    """
    Entry router. Decides the first node based on current state.
    """
    # If awaiting yes/no for lesson offer
    if state.get('awaiting_lesson_confirmation'):
        logger.info("Awaiting lesson confirmation -> handle_lesson_confirmation")
        return "handle_lesson_confirmation"

    # If in active explanation mode (has topic + lesson plan)
    topic = state.get('topic', '')
    lesson_plan = state.get('lesson_plan', [])
    mode = state.get('mode', 'general')

    if mode == 'explanation' and topic and lesson_plan:
        logger.info(f"Active lesson on '{topic}' -> analyze_topic")
        return "analyze_topic"

    # General mode -- classify the query
    logger.info("General mode -> classify_query")
    return "classify_query"


def route_after_classification(state: AgentState) -> Literal["general_answer", "brief_answer_and_offer"]:
    """Routes after classify_query based on the classification result."""
    last_action = state.get('last_action', '')

    if last_action == 'classified_explanation':
        return "brief_answer_and_offer"

    return "general_answer"


def route_after_confirmation(state: AgentState) -> Literal["plan_lesson", "classify_query", "end"]:
    """Routes after user responds to lesson offer."""
    last_action = state.get('last_action', '')

    if last_action == 'confirmed_lesson':
        return "plan_lesson"

    if last_action == 'ambiguous_confirmation':
        # Treat their response as a new query -- reclassify
        return "classify_query"

    # declined_lesson -> message already added, end turn
    return "end"


def route_after_topic_analysis(state: AgentState) -> Literal["evaluate_response", "plan_lesson", "classify_query", "end"]:
    """Routes after analyze_topic in explanation mode."""
    last_action = state.get('last_action', '')

    if last_action == 'context_analyzed':
        return "evaluate_response"

    if last_action == 'exited_lesson':
        # User exited lesson, reclassify their query as a new general query
        return "classify_query"

    # All other cases (repeated, redirected, small_talk, answered_question, waiting) -> end turn
    return "end"


def route_after_evaluation(state: AgentState) -> Literal["generate_explanation", "complete_lesson"]:
    """Routes after evaluate_response. Always proceeds -- check if lesson is done."""
    lesson_step = state.get('lesson_step', 1)
    lesson_plan = state.get('lesson_plan', [])

    if lesson_step > len(lesson_plan):
        return "complete_lesson"

    return "generate_explanation"


def build_agent():
    """Build and compile the LangGraph workflow."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("classify_query", classify_query)
    workflow.add_node("general_answer", general_answer)
    workflow.add_node("brief_answer_and_offer", brief_answer_and_offer)
    workflow.add_node("handle_lesson_confirmation", handle_lesson_confirmation)
    workflow.add_node("plan_lesson", plan_lesson)
    workflow.add_node("generate_explanation", generate_explanation)
    workflow.add_node("analyze_topic", analyze_topic_context)
    workflow.add_node("evaluate_response", evaluate_response)
    workflow.add_node("complete_lesson", complete_lesson)

    # START -> route based on current state
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "handle_lesson_confirmation": "handle_lesson_confirmation",
            "analyze_topic": "analyze_topic",
            "classify_query": "classify_query",
        }
    )

    # classify_query -> general_answer OR brief_answer_and_offer
    workflow.add_conditional_edges(
        "classify_query",
        route_after_classification,
        {
            "general_answer": "general_answer",
            "brief_answer_and_offer": "brief_answer_and_offer",
        }
    )

    # general_answer -> END
    workflow.add_edge("general_answer", END)

    # brief_answer_and_offer -> END (wait for user yes/no)
    workflow.add_edge("brief_answer_and_offer", END)

    # handle_lesson_confirmation -> plan_lesson OR classify_query OR END
    workflow.add_conditional_edges(
        "handle_lesson_confirmation",
        route_after_confirmation,
        {
            "plan_lesson": "plan_lesson",
            "classify_query": "classify_query",
            "end": END,
        }
    )

    # plan_lesson -> generate_explanation
    workflow.add_edge("plan_lesson", "generate_explanation")

    # generate_explanation -> END (wait for user answer)
    workflow.add_edge("generate_explanation", END)

    # analyze_topic -> evaluate_response OR plan_lesson OR classify_query OR END
    workflow.add_conditional_edges(
        "analyze_topic",
        route_after_topic_analysis,
        {
            "evaluate_response": "evaluate_response",
            "plan_lesson": "plan_lesson",
            "classify_query": "classify_query",
            "end": END,
        }
    )

    # evaluate_response -> generate_explanation OR complete_lesson
    workflow.add_conditional_edges(
        "evaluate_response",
        route_after_evaluation,
        {
            "generate_explanation": "generate_explanation",
            "complete_lesson": "complete_lesson",
        }
    )

    # complete_lesson -> END
    workflow.add_edge("complete_lesson", END)

    # Compile with checkpointer
    app = workflow.compile(checkpointer=checkpointer)

    logger.info("Agent workflow compiled successfully (v2)")

    return app


# ========================================
# CACHED AGENT SINGLETON
# ========================================

_cached_agent = None


def get_agent():
    """Return a cached agent instance. The graph is built once and reused across all requests."""
    global _cached_agent
    if _cached_agent is None:
        _cached_agent = build_agent()
        logger.info("Agent graph built and cached")
    return _cached_agent


def run_agent(user: dict, query: str, session_id: str):
    """
    Run the guided learning agent with proper state persistence.
    """
    try:
        logger.info(f"Running agent for user {user.get('_id')} with query: {query}")

        config = {
            "configurable": {
                "thread_id": session_id
            }
        }

        agent = get_agent()

        # Check existing session state
        current_state = agent.get_state(config)
        has_state = bool(current_state.values)
        has_active_lesson = has_state and bool(current_state.values.get("topic"))
        is_awaiting = has_state and current_state.values.get("awaiting_lesson_confirmation", False)

        # FAST PATH: small talk with no active lesson and no pending confirmation
        if not has_active_lesson and not is_awaiting and is_small_talk(query):
            logger.info("Small talk (no lesson) -> fast path (1 LLM call)")
            return handle_small_talk(query)

        if has_state and (has_active_lesson or is_awaiting):
            logger.info(f"Resuming session -- topic='{current_state.values.get('topic', '')}', awaiting={is_awaiting}")
            input_state = {
                "messages": [HumanMessage(content=query)],
                "query": query,
                "user": user,
            }
        else:
            logger.info("New session -- initializing state")
            input_state = {
                "messages": [HumanMessage(content=query)],
                "query": query,
                "user": user,
                "session_id": session_id,
                "mode": "general",
                "topic": "",
                "lesson_plan": [],
                "lesson_step": 0,
                "last_action": "initial",
                "awaiting_lesson_confirmation": False,
                "pending_topic": "",
                "feedback": "",
                "last_explanation": "",
            }

        result_state = agent.invoke(input_state, config=config)

        ai_messages = [m for m in result_state.get('messages', []) if isinstance(m, AIMessage)]
        response = ai_messages[-1].content if ai_messages else "I'm here to help you learn!"

        logger.info("Agent completed successfully")
        return response

    except Exception as e:
        logger.error(f"Error running agent: {e}", exc_info=True)
        raise