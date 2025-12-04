from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from pymongo import MongoClient
from datetime import datetime

class CustomMongoDBChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, session_id: str, connection_string: str, database_name: str, collection_name: str, max_recent_messages: int = 100):
        self.session_id = session_id
        self.client = MongoClient(connection_string)
        self.collection = self.client[database_name][collection_name]
        self.max_recent_messages = max_recent_messages

        # Initialize if doesn't exist
        existing = self.collection.find_one({"_id": session_id})
        if not existing:
            self.collection.insert_one({"_id": session_id, "messages": []})

    @property
    def messages(self) -> list[BaseMessage]:
        doc = self.collection.find_one({"_id": self.session_id}, {"messages": {"$slice": -self.max_recent_messages}})
        messages = doc.get("messages", [])
        
        # Optional: sort messages by timestamp
        messages.sort(key=lambda x: x.get("timestamp", ""))
        
        return [self._dict_to_message(msg) for msg in messages]

    def add_user_message(self, message: str) -> None:
        self._append_message(HumanMessage(content=message))

    def add_ai_message(self, message: str, sources: list[str]=None, image_links: list[dict]=None) -> None:
        self._append_message(AIMessage(content=message), sources=sources, image_links=image_links)

    def _append_message(self, message: BaseMessage, sources: list[str] = None, image_links: list[dict] = None) -> None:
        if message.type == "ai":
            self.collection.update_one(
                {"_id": self.session_id},
                {"$push": {"messages": self._message_to_dict(message, sources=sources, image_links=image_links)}}
            )
        else:
            self.collection.update_one(
                {"_id": self.session_id},
                {"$push": {"messages": self._message_to_dict(message)}}
            )

    def clear(self) -> None:
        self.collection.update_one({"_id": self.session_id}, {"$set": {"messages": []}})


    def _message_to_dict(self, message: BaseMessage, sources: list[str] = None, image_links: list[dict] = None) -> dict:
        if isinstance(message, HumanMessage):
            return {
                "type": "human",
                "data": {
                    "content": message.content
                },
                "timestamp": datetime.now()
            }

        elif isinstance(message, AIMessage):
            return {
                "type": "ai",
                "data": {
                    "content": message.content,
                    "sources": sources if sources else [],
                    "image_links": image_links if image_links else []
                },
                "timestamp": datetime.now()
            }

        else:
            raise ValueError(f"Unsupported message type: {type(message)}")

    def _dict_to_message(self, data: dict) -> BaseMessage:
        msg_type = data["type"]
        content = data["data"]["content"]
        sources = data["data"].get("sources", [])
        image_links = data["data"].get("image_links", [])

        if msg_type == "human":
            return HumanMessage(content=content)
        elif msg_type == "ai":
            return AIMessage(content=content, additional_kwargs={
                "sources": sources,
                "image_links": image_links
            })
        else:
            raise ValueError(f"Unsupported message type: {msg_type}")


