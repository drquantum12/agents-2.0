# from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI


class LLM:

    def __init__(self):
        self.classifier_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=0,
            max_output_tokens=4096,
            timeout=30,
            max_retries=2,
        )

        self.main_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.3,  # lower = more deterministic tool-calling; 0.7 caused random skips
            max_output_tokens=4096,
            timeout=60,
            max_retries=2,
            # Disable the thinking budget: gemini-2.5-flash is a thinking model and sometimes
            # generates only an internal thinking block with empty final content + no tool_calls.
            # Setting thinking_budget=0 forces it to behave like a standard non-thinking model,
            # making tool-calling reliable.
            thinking_budget=0,
        )
        # self.llm = ChatOllama(base_url="http://localhost:11434",
        #           model="llama3.2:latest",
        #           temperature=0)

    def get_llm(self):
        return self.main_llm

    def get_classifier_llm(self):
        return self.classifier_llm


# ---------------------------------------------------------------------------
# Module-level singletons — import these directly in node files:
#   from app.agents.llm import llm, classifier_llm
#
# Swap classifier_llm here if you later want a lighter model for the classifier.
# ---------------------------------------------------------------------------
llm = LLM().get_llm()
classifier_llm = LLM().get_classifier_llm()