# from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI

class LLM:

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=1,
            max_output_tokens=8192,
            timeout=30,
            max_retries=2,)
        # self.llm = ChatOllama(base_url="http://localhost:11434",
        #           model="llama3.2:latest",
        #           temperature=0)

    def get_llm(self):
        return self.llm