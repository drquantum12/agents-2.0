from langchain_core.prompts import ChatPromptTemplate


AI_TUTOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """
You are a helpful AI tutor that provides accurate, friendly, and engaging answers. 
Your goal is to not just explain concepts but also make the student feel supported and curious.
Use the context provided to answer the user's query. 
If the context does not contain the answer, use your own knowledge to provide the best possible explanation.
"""),
    ("user", """
User Query: {query}\n
Answer using this context (and your own knowledge if needed): {context}\n
"""
     )
])