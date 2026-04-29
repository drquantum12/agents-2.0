# from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI


class LLM:

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=1,
            max_output_tokens=4096,
            timeout=30,
            max_retries=2,
        )
        # self.llm = ChatOllama(base_url="http://localhost:11434",
        #           model="llama3.2:latest",
        #           temperature=0)

    def get_llm(self):
        return self.llm


# ---------------------------------------------------------------------------
# Module-level singletons — import these directly in node files:
#   from app.agents.llm import llm, fast_llm
#
# Swap fast_llm here if you later want a lighter model for the classifier.
# ---------------------------------------------------------------------------
llm = LLM().get_llm()
fast_llm = llm