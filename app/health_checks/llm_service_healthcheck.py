from langchain_google_genai import ChatGoogleGenerativeAI


class LLMServiceHealthCheck:

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=1,
            max_output_tokens=8192,
            timeout=30,
            max_retries=2,)

    def check_health(self):
        try:
            response = self.llm.invoke("Hello, how are you?")
            if response and response.content:
                print(f"LLM Service Health Check Successful: Received response - {response.content}")
                return True
            else:
                return False
        except Exception as e:
            print(f"LLM Service Health Check Failed: {e}")
            return False
        

if __name__ == "__main__":
    health_check = LLMServiceHealthCheck()
    is_healthy = health_check.check_health()
    print(f"LLM Service Healthy: {is_healthy}")