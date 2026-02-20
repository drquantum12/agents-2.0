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
    LESSON_PLANNER_PROMPT, 
    TUTOR_EXPLANATION_PROMPT, 
    EVALUATOR_PROMPT,
    REFLECTION_PROMPT,
    TOPIC_ANALYSIS_PROMPT
)
import logging
import operator
from app.agents.schemas import LessonPlanSchema, EvaluationSchema, TopicAnalysisSchema
import json


logger = logging.getLogger(__name__)

llm = LLM().get_llm()
llm_with_lesson_tool = llm.bind_tools(tools=[LessonPlanSchema])
llm_with_eval_tool = llm.bind_tools(tools=[EvaluationSchema])
llm_with_topic_analysis_tool = llm.bind_tools(tools=[TopicAnalysisSchema])

MAX_STEPS = 5

class AgentState(TypedDict):
    """The state of the guided learning agent."""
    query: str  # the user's question or topic of interest
    user: dict  # user information (e.g., {'id': 'user123', 'name': 'Alice'})
    messages: Annotated[list[BaseMessage], operator.add]
    topic: str  # the main topic of the lesson (e.g., "Photosynthesis")
    lesson_plan: list[str]  # List of lesson steps
    lesson_step: int  # current step number in the lesson (e.g., 1, 2, 3...)
    quiz_mode: bool  # flag to indicate if the agent is in quiz mode
    knowledge_gaps: list[str]  # Topics the user struggled with
    last_action: str  # Last action taken by evaluator: 'proceed', 're-explain', or 'initial'
    session_id: str  # Session ID for tracking
    context_switch: bool  # Flag indicating if user wants to switch topics
    pending_topic: str  # New topic user wants to learn (if switching)
    feedback: str  # Feedback from the evaluator (e.g., "Great job!")

# Setup MongoDB checkpointer (for persistence/short-term memory)
checkpointer = MongoDBSaver(
    client=MongoClient(os.getenv("MONGODB_CONNECTION_STRING")),
    db_name="neurosattva"
)


def plan_lesson(state: AgentState) -> dict:
    """
    Planning and Initialization Node.
    Generates a structured lesson plan using Gemini with LessonPlanSchema tool.
    Handles both initial queries and topic switches.
    """
    # Check if this is a topic switch
    context_switch = state.get('context_switch', False)
    pending_topic = state.get('pending_topic', '')
    
    # Use pending_topic if switching, otherwise use query
    topic_to_plan = pending_topic if context_switch and pending_topic else state.get('query', 'Unknown')
    
    logger.info(f"Planning lesson for topic: {topic_to_plan}" + (" (topic switch)" if context_switch else ""))
    
    try:
        # Use the lesson planner prompt
        prompt = LESSON_PLANNER_PROMPT.format(
            topic=topic_to_plan,
            max_steps=MAX_STEPS
        )
        
        # Call Gemini with tool binding
        response = llm_with_lesson_tool.invoke(prompt)
        
        # Extract lesson plan from tool call
        if response.tool_calls and len(response.tool_calls) > 0:
            lesson_plan_data = response.tool_calls[0]['args']
            topic = lesson_plan_data.get('topic', state['query'])
            steps = lesson_plan_data.get('steps', [])
            
            logger.info(f"Generated lesson plan with {len(steps)} steps for topic: {topic}")
            
            # Add a system message about the plan
            plan_message = AIMessage(
                content=f"I've created a lesson plan for '{topic}' with {len(steps)} steps. Let's begin!"
            )
            
            return {
                "topic": topic,
                "lesson_plan": steps,
                "lesson_step": 1,
                "last_action": "planned",
                "messages": [plan_message],
                "context_switch": False,
                "pending_topic": ""
            }
        else:
            # Fallback if no tool call
            logger.warning("No tool call in lesson planning response, using fallback")
            return {
                "topic": state['query'],
                "lesson_plan": [f"Introduction to {state['query']}", 
                               f"Key concepts of {state['query']}",
                               f"Practical applications"],
                "lesson_step": 1,
                "last_action": "planned",
                "messages": [AIMessage(content=f"Let's explore {state['query']} together!")],
                "context_switch": False,
                "pending_topic": ""
            }
            
    except Exception as e:
        logger.error(f"Error in plan_lesson: {e}")
        # Fallback plan
        return {
            "topic": state['query'],
            "lesson_plan": [f"Understanding {state['query']}"],
            "lesson_step": 1,
            "last_action": "planned",
            "messages": [AIMessage(content=f"Let's learn about {state['query']}!")]
        }


def generate_explanation(state: AgentState) -> dict:
    """
    Lesson Generation Node.
    Generates an explanation for the current lesson step and asks a probing question.
    """
    current_step = state.get('lesson_step', 1)
    lesson_plan = state.get('lesson_plan', [])
    topic = state.get('topic', state.get('query', 'the topic'))
    user_name = state.get('user', {}).get('name', 'there')
    
    logger.info(f"Generating explanation for step {current_step} of {len(lesson_plan)}")
    
    try:
        # Get the current step content
        if lesson_plan and current_step <= len(lesson_plan):
            step_content = lesson_plan[current_step - 1]
        else:
            step_content = f"Step {current_step} of {topic}"
        
        # Use the tutor explanation prompt
        prompt = TUTOR_EXPLANATION_PROMPT.format(
            topic=topic,
            lesson_step=current_step,
            step_content=step_content,
            total_steps=len(lesson_plan)
        )
        
        # Call Gemini for explanation
        response = llm.invoke(prompt)
        
        # Prepare the final content
        final_content = response.content
        
        # Check if there's feedback from the previous evaluation
        previous_feedback = state.get('feedback', '')
        if previous_feedback:
            # Prepend feedback to the explanation
            final_content = f"{previous_feedback}\n\n{final_content}"
            logger.info("Prepended feedback to explanation")
        
        explanation_message = AIMessage(content=final_content)
        
        logger.info(f"Generated explanation for step {current_step}")
        
        return {
            "messages": [explanation_message],
            "last_action": "explained",
            "feedback": ""  # Clear feedback after using it
        }
        
    except Exception as e:
        logger.error(f"Error in generate_explanation: {e}")
        fallback_message = AIMessage(
            content=f"Let me explain step {current_step}: {step_content}. What are your thoughts on this?"
        )
        return {
            "messages": [fallback_message],
            "last_action": "explained"
        }


def evaluate_response(state: AgentState) -> dict:
    """
    Evaluation and Progression Node.
    Evaluates the user's response and decides whether to proceed or re-explain.
    """
    messages = state.get('messages', [])
    
    # Get the last user message and the question before it
    user_messages = [m for m in messages if isinstance(m, HumanMessage)]
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    
    if not user_messages:
        logger.warning("No user messages to evaluate")
        return {"last_action": "proceed"}
    
    latest_user_message = user_messages[-1].content
    last_agent_question = ai_messages[-1].content if ai_messages else "the previous question"
    
    logger.info(f"Evaluating user response: {latest_user_message[:50]}...")
    
    try:
        # Use the evaluator prompt
        prompt = EVALUATOR_PROMPT.format(
            user_response=latest_user_message,
            agent_question=last_agent_question,
            topic=state.get('topic', 'the topic')
        )
        
        # Call Gemini with evaluation tool
        response = llm_with_eval_tool.invoke(prompt)
        
        # Extract evaluation from tool call
        if response.tool_calls and len(response.tool_calls) > 0:
            eval_data = response.tool_calls[0]['args']
            action = eval_data.get('action', 'proceed')
            feedback = eval_data.get('feedback', '')
            
            logger.info(f"Evaluation result: {action}")
            
            # If re-explain, add feedback message
            if action == 're-explain':
                feedback_message = AIMessage(content=feedback)
                return {
                    "messages": [feedback_message],
                    "last_action": "re-explain"
                }
            else:
                # Proceed to next step
                current_step = state.get('lesson_step', 1)
                return {
                    "lesson_step": current_step + 1,
                    "last_action": "proceed",
                    "feedback": feedback  # Save feedback for the next explanation
                }
        else:
            # Default to proceed if no tool call
            logger.warning("No tool call in evaluation, defaulting to proceed")
            current_step = state.get('lesson_step', 1)
            return {
                "lesson_step": current_step + 1,
                "last_action": "proceed"
            }
            
    except Exception as e:
        logger.error(f"Error in evaluate_response: {e}")
        # Default to proceed on error
        current_step = state.get('lesson_step', 1)
        return {
            "lesson_step": current_step + 1,
            "last_action": "proceed"
        }


def analyze_topic_context(state: AgentState) -> dict:
    """
    Topic Analysis Node.
    Analyzes if user's query is related to current lesson or represents a topic change.
    This handles edge cases like mid-lesson topic switches and off-topic questions.
    
    IMPORTANT: Only analyzes if user has responded AFTER the last explanation.
    """
    messages = state.get('messages', [])
    topic = state.get('topic', '')
    lesson_step = state.get('lesson_step', 1)
    lesson_plan = state.get('lesson_plan', [])
    
    # Get the latest user and AI messages
    user_messages = [m for m in messages if isinstance(m, HumanMessage)]
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    
    if not user_messages or not topic:
        # No context to analyze, proceed normally
        return {"last_action": "context_analyzed"}
    
    # CRITICAL FIX: Check if the LAST message is from the user
    # If the last message is from AI (explanation), user hasn't responded yet
    if not messages:
        return {"last_action": "waiting_for_response"}
        
    last_message = messages[-1]
    
    if isinstance(last_message, AIMessage):
        logger.info("Last message was from AI, waiting for user response")
        return {"last_action": "waiting_for_response"}
        
    # If we got here, the last message is from the user (HumanMessage)
    # Proceed with analysis
    logger.info("New user message detected, proceeding with analysis")
    
    latest_user_query = user_messages[-1].content
    last_agent_message = ai_messages[-1].content if ai_messages else ""
    
    # Get current step content
    step_content = ""
    if lesson_plan and lesson_step <= len(lesson_plan):
        step_content = lesson_plan[lesson_step - 1]
    
    logger.info(f"Analyzing topic context for query: {latest_user_query[:50]}...")
    
    try:
        # Use the topic analysis prompt
        prompt = TOPIC_ANALYSIS_PROMPT.format(
            current_topic=topic,
            current_step=lesson_step,
            total_steps=len(lesson_plan),
            step_content=step_content,
            last_agent_message=last_agent_message[:200],  # Truncate for context
            user_query=latest_user_query
        )
        
        # Call Gemini with topic analysis tool
        response = llm_with_topic_analysis_tool.invoke(prompt)
        
        # Extract analysis from tool call
        if response.tool_calls and len(response.tool_calls) > 0:
            analysis = response.tool_calls[0]['args']
            is_related = analysis.get('is_related', True)
            intent = analysis.get('intent', 'answer')
            suggested_action = analysis.get('suggested_action', 'continue_lesson')
            confidence = analysis.get('confidence', 0.8)
            
            logger.info(f"Topic analysis: intent={intent}, action={suggested_action}, confidence={confidence}")
            
            # Handle different scenarios
            if suggested_action == 'switch_topic':
                # User wants to switch to a completely new topic
                logger.info(f"User wants to switch from '{topic}' to a new topic")
                
                # Save current progress message
                progress_msg = AIMessage(
                    content=f"I see you'd like to learn about something else. We've completed {lesson_step - 1} out of {len(lesson_plan)} steps on '{topic}'. Let's start your new lesson!"
                )
                
                return {
                    "messages": [progress_msg],
                    "context_switch": True,
                    "pending_topic": latest_user_query,
                    "last_action": "topic_switch"
                }
            
            elif suggested_action == 'answer_and_continue':
                # User has a related question, answer it briefly then continue
                logger.info("User has a related question, will answer and continue")
                
                # Generate a brief answer
                answer_prompt = f"Briefly answer this question about {topic}: {latest_user_query}\nKeep it to 2-3 sentences, then remind them we'll continue with step {lesson_step}."
                answer_response = llm.invoke(answer_prompt)
                
                answer_msg = AIMessage(content=answer_response.content)
                
                return {
                    "messages": [answer_msg],
                    "last_action": "answered_question"
                }
            
            elif suggested_action == 'politely_redirect':
                # Off-topic question, politely redirect to current lesson
                logger.info("Off-topic question detected, redirecting to lesson")
                
                redirect_msg = AIMessage(
                    content=f"That's an interesting question! However, let's focus on completing our lesson on '{topic}' first. We're on step {lesson_step} of {len(lesson_plan)}. Once we finish, I'd be happy to help with other topics!"
                )
                
                return {
                    "messages": [redirect_msg],
                    "last_action": "redirected"
                }
            
            else:  # continue_lesson
                # User is answering the lesson question, proceed to evaluation
                logger.info("User is answering lesson question, proceeding to evaluation")
                return {
                    "last_action": "context_analyzed"
                }
        
        else:
            # No tool call, default to continuing lesson
            logger.warning("No tool call in topic analysis, defaulting to continue lesson")
            return {"last_action": "context_analyzed"}
            
    except Exception as e:
        logger.error(f"Error in analyze_topic_context: {e}")
        # On error, assume user is continuing the lesson
        return {"last_action": "context_analyzed"}


def reflect_on_knowledge_gaps(state: AgentState) -> dict:
    """
    Reflection Node (Optional).
    Reviews the conversation and identifies knowledge gaps.
    """
    messages = state.get('messages', [])
    knowledge_gaps = state.get('knowledge_gaps', [])
    topic = state.get('topic', 'the topic')
    
    logger.info("Reflecting on knowledge gaps")
    
    try:
        # Create a summary of the conversation
        conversation_summary = "\n".join([
            f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content[:100]}..."
            for m in messages[-10:]  # Last 10 messages
        ])
        
        prompt = REFLECTION_PROMPT.format(
            topic=topic,
            conversation_summary=conversation_summary,
            current_gaps=", ".join(knowledge_gaps) if knowledge_gaps else "None identified yet"
        )
        
        response = llm.invoke(prompt)
        
        # Parse the response to extract new gaps
        # This is simplified - in production, you'd use structured output
        new_gaps = []
        if "struggled with" in response.content.lower():
            # Simple extraction logic
            new_gaps = knowledge_gaps + [topic]  # Placeholder
        
        logger.info(f"Identified {len(new_gaps)} knowledge gaps")
        
        # Prepare completion message
        completion_msg = (
            f"Congratulations! You've completed the lesson on {topic}. "
            "You did a great job! Feel free to ask any other questions or suggest a new topic you'd like to learn about."
        )
        
        return {
            "knowledge_gaps": new_gaps,
            "messages": [AIMessage(content=completion_msg)],
            "topic": "",  # Clear topic to allow new lessons
            "lesson_plan": [], # Clear plan
            "lesson_step": 0   # Reset step
        }
        
    except Exception as e:
        logger.error(f"Error in reflect_on_knowledge_gaps: {e}")
        return {
             "messages": [AIMessage(content="Great work! You've completed the lesson. What would you like to learn next?")],
             "topic": "",
             "lesson_plan": [],
             "lesson_step": 0
        }


def should_continue(state: AgentState) -> Literal["generate_explanation", "evaluate_response", "reflect", "end"]:
    """
    Conditional routing function.
    Decides which node to call next based on the current state.
    """
    last_action = state.get('last_action', 'initial')
    lesson_step = state.get('lesson_step', 1)
    lesson_plan = state.get('lesson_plan', [])
    messages = state.get('messages', [])
    
    logger.info(f"Routing decision - Last action: {last_action}, Step: {lesson_step}/{len(lesson_plan)}")
    
    # If we just planned, generate first explanation
    if last_action == 'planned':
        return "generate_explanation"
    
    # If we just explained, wait for user response (analyze topic next)
    if last_action == 'explained':
        # Check if there's a new user message
        user_messages = [m for m in messages if isinstance(m, HumanMessage)]
        if user_messages:
            return "analyze_topic"  # User responded, analyze context
        else:
            # No user response yet, end this turn
            return "end"
    
    # If we evaluated and need to re-explain
    if last_action == 're-explain':
        return "generate_explanation"
    
    # If we evaluated and should proceed
    if last_action == 'proceed':
        # Check if we've completed all steps
        if lesson_step > len(lesson_plan):
            return "reflect"
        else:
            return "generate_explanation"
    
    # If we answered a question, continue with current step
    if last_action == 'answered_question':
        return "generate_explanation"
    
    # If we redirected user, end turn and wait for response
    if last_action == 'redirected':
        return "end"
    
    # If context was analyzed, proceed to evaluation
    if last_action == 'context_analyzed':
        return "evaluate_response"
    
    # If waiting for user response, end turn
    if last_action == 'waiting_for_response':
        return "end"
    
    # If user wants to switch topics, start new lesson
    if last_action == 'topic_switch':
        return "plan_lesson"
    
    # Default: end
    return "end"


def should_analyze_topic(state: AgentState) -> Literal["analyze_topic", "evaluate_response"]:
    """
    Decides whether to analyze topic context before evaluating.
    Only analyze if we're in the middle of a lesson.
    """
    topic = state.get('topic', '')
    lesson_step = state.get('lesson_step', 0)
    
    # If we have an active lesson, analyze the context
    if topic and lesson_step > 0:
        return "analyze_topic"
    else:
        # No active lesson, proceed to evaluation
        return "evaluate_response"


def route_start(state: AgentState) -> Literal["plan_lesson", "analyze_topic"]:
    """
    Determine the entry point based on the current state.
    If a lesson is active, analyze the user's new input.
    If no lesson is active, start planning.
    """
    topic = state.get("topic")
    lesson_plan = state.get("lesson_plan")
    
    # Check if we have an active lesson
    if topic and lesson_plan and len(lesson_plan) > 0:
        logger.info(f"Resuming active lesson: '{topic}' -> Analyzing context")
        return "analyze_topic"
        
    logger.info("No active lesson found -> Starting planning")
    return "plan_lesson"


def build_agent():
    """
    Build and compile the LangGraph workflow with topic analysis.
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("plan_lesson", plan_lesson)
    workflow.add_node("generate_explanation", generate_explanation)
    workflow.add_node("analyze_topic", analyze_topic_context)
    workflow.add_node("evaluate_response", evaluate_response)
    workflow.add_node("reflect", reflect_on_knowledge_gaps)
    
    # Set conditional entry point
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "plan_lesson": "plan_lesson",
            "analyze_topic": "analyze_topic"
        }
    )
    
    # After planning, go to explanation
    workflow.add_edge("plan_lesson", "generate_explanation")
    
    # After explanation, conditional routing (check for user response)
    workflow.add_conditional_edges(
        "generate_explanation",
        should_continue,
        {
            "analyze_topic": "analyze_topic",  # User responded, analyze context
            "end": END
        }
    )
    
    # After topic analysis, conditional routing
    workflow.add_conditional_edges(
        "analyze_topic",
        should_continue,
        {
            "evaluate_response": "evaluate_response",  # Continue with evaluation
            "generate_explanation": "generate_explanation",  # Answer question or re-explain
            "plan_lesson": "plan_lesson",  # Switch to new topic
            "end": END  # Redirected, wait for user
        }
    )
    
    # After evaluation, conditional routing
    workflow.add_conditional_edges(
        "evaluate_response",
        should_continue,
        {
            "generate_explanation": "generate_explanation",
            "reflect": "reflect",
            "end": END
        }
    )
    
    # After reflection, end
    workflow.add_edge("reflect", END)
    
    # Compile with checkpointer
    app = workflow.compile(checkpointer=checkpointer)
    
    logger.info("Agent workflow compiled successfully with topic analysis")
    
    return app


def run_agent(user: dict, query: str, session_id: str):
    """
    Run the guided learning agent with proper state persistence.
    """
    try:
        logger.info(f"Running agent for user {user.get('_id')} with query: {query}")
        
        # Configuration for checkpointing
        config = {
            "configurable": {
                "thread_id": session_id
            }
        }
        
        # Build agent
        agent = build_agent()
        
        # Check if we have an existing session
        current_state = agent.get_state(config)
        
        if current_state.values and current_state.values.get("topic"):
            logger.info(f"Resuming existing session for topic: {current_state.values.get('topic')}")
            # Existing session: ONLY pass the new info (messages, query)
            # Do NOT pass defaults like topic="" because that overwrites the saved state!
            input_state = {
                "messages": [HumanMessage(content=query)],
                "query": query,
                # Update user info if needed, or rely on state
                "user": user 
            }
        else:
            logger.info("Starting new session (no existing state found)")
            # New session: Pass all defaults to initialize the TypedDict correctly
            input_state = {
                "messages": [HumanMessage(content=query)],
                "query": query,
                "user": user,
                "session_id": session_id,
                "topic": "",
                "lesson_plan": [],
                "lesson_step": 0,
                "quiz_mode": False,
                "knowledge_gaps": [],
                "last_action": "initial",
                "context_switch": False,
                "pending_topic": ""
            }
        
        # Invoke agent
        result_state = agent.invoke(input_state, config=config)
        
        # Extract the response from messages
        ai_messages = [m for m in result_state.get('messages', []) if isinstance(m, AIMessage)]
        response = ai_messages[-1].content if ai_messages else "I'm here to help you learn!"
        
        logger.info(f"Agent completed successfully")
        
        return response
        
    except Exception as e:
        logger.error(f"Error running agent: {e}", exc_info=True)
        raise


    

