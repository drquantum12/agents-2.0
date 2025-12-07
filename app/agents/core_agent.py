from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from typing import TypedDict
from app.agents.llm import LLM
import os
from app.agents.agent_memory_controller import get_chat_history
from langchain_core.runnables import RunnableConfig
from app.agents.prompts import AI_TUTOR_PROMPT
import logging

logger = logging.getLogger(__name__)

llm = LLM().get_llm()

class AgentState(TypedDict, total=False):
    user: dict
    query: str
    history: list[BaseMessage]
    response: str


def dialog_manager_agent(state: AgentState, config: RunnableConfig):
    print("--- Dialog Manager Agent ---")
    
    prompt = AI_TUTOR_PROMPT.invoke({
        "user_name": state["user"]["name"],
        "query": state["query"],
        "chat_history": state["history"]
    })
    resp = llm.invoke(prompt).content.strip()
    state["response"] = resp
    return state

def build_agent():
    agent_graph = StateGraph(AgentState)

    agent_graph.add_node("dialog_manager_agent", dialog_manager_agent)

    agent_graph.add_edge(START, "dialog_manager_agent")
    agent_graph.add_edge("dialog_manager_agent", END)
    
    return agent_graph.compile()


def run_agent(user: dict, query: str, session_id: str):
    try:
        chat_history = get_chat_history(session_id)
        state = AgentState(
            user=user,
            query=query,
            history=chat_history.messages,
            response=""
        )

        config = {"configurable": {"session_id": session_id}}

        agent = build_agent()
        
        result_state = agent.invoke(state, config=config)
        resp = result_state["response"]
        
        chat_history.add_user_message(query)
        chat_history.add_ai_message(resp)
        return resp
    except Exception as e:
        logger.error(f"Error running agent: {e}")
        raise


    

