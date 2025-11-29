# using milvus vector db
import os
from pymilvus import MilvusClient
from google import genai
from google.genai import types

embedding_client = genai.Client()

MILVUS_URI = os.getenv('MILVUS_URI')
MILVUS_TOKEN = os.getenv('MILVUS_TOKEN')
COLLECTION_NAME = os.getenv('MILVUS_COLLECTION_NAME')
VECTOR_DIMENSION = int(os.getenv('MILVUS_VECTOR_DIMENSION', 768))

# metadata_fields = ["board", "grade", "subject", "chapter", "heading", "subheading", "content"]

class VectorDB:
    
    def __init__(self):
        self.client = MilvusClient(uri=MILVUS_URI, token=MILVUS_TOKEN)
        self.similarity_score_threshold = 0.6  # Example threshold for similarity score

    def get_similar_documents(self, text, top_k=3, board=None, grade=None, subject=None, chapter=None):
        """
        Retrieves similar documents from the Milvus vector database.
        """
        try:
            query_embedding = generate_embedding(text, vector_dimension=VECTOR_DIMENSION)
            # Build filter expression if any filter is provided
            filter_clauses = []
            if board:
                filter_clauses.append(f"metadata_json['board'] == '{board}'")
            if grade:
                filter_clauses.append(f"metadata_json['grade'] == '{grade}'")
            if subject:
                filter_clauses.append(f"metadata_json['subject'] == '{subject}'")
            if chapter:
                filter_clauses.append(f"metadata_json['chapter'] == '{chapter}'")
            filter_expression = " and ".join(filter_clauses) if filter_clauses else None

            search_kwargs = {
                "collection_name": COLLECTION_NAME,
                "anns_field": "embedding",
                "data": [query_embedding],
                "search_params": {
                    "metric_type": "COSINE"
                },
                "limit": top_k,
                "output_fields": ["metadata_json"]
            }
            if filter_expression:
                search_kwargs["filter"] = filter_expression

            results = self.client.search(**search_kwargs)
            context_for_llm = {
                    "content": [],
                    "source": []
                }
            for result in results[0]:
                metadata = result["entity"].get("metadata_json", {})
                if metadata and result["distance"] >= self.similarity_score_threshold:
                    context_for_llm["content"].append(metadata.get("content", ""))
                    context_for_llm["source"].append(f"{metadata.get('board')} - {metadata.get('grade')} - {metadata.get('subject')} - {metadata.get('chapter')} - {metadata.get('subheading')}")
            return "\n".join(context_for_llm["content"]), context_for_llm["source"]
        except Exception as e:
            raise Exception(f"Error retrieving similar documents: {str(e)}")
        
    def get_documents(self, board=None, grade=None, subject=None, chapter=None, limit=100):
        """
        Fetches all documents from the Milvus vector database that match the provided filters.
        No text similarity search is performed, only filtering by metadata.
        """
        try:
            filter_clauses = []
            if board:
                filter_clauses.append(f"metadata_json['board'] == '{board}'")
            if grade:
                filter_clauses.append(f"metadata_json['grade'] == '{grade}'")
            if subject:
                filter_clauses.append(f"metadata_json['subject'] == '{subject}'")
            if chapter:
                filter_clauses.append(f"metadata_json['chapter'] == '{chapter}'")
            filter_expression = " and ".join(filter_clauses) if filter_clauses else None

            search_kwargs = {
                "collection_name": COLLECTION_NAME,
                "output_fields": ["metadata_json"],
                "limit": limit
            }
            if filter_expression:
                search_kwargs["filter"] = filter_expression

            results = self.client.query(**search_kwargs)
            documents = []
            for result in results:
                metadata = result.get("metadata_json", {})
                if metadata:
                    documents.append(metadata)
            return documents
        except Exception as e:
            raise Exception(f"Error retrieving documents: {str(e)}")




def generate_embedding(text, vector_dimension=768):
    """
    Generates an embedding for the given text using Google GenAI.
    """
    try:
        response = embedding_client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=vector_dimension,
                task_type="RETRIEVAL_DOCUMENT"
            )
        )
        return response.embeddings[0].values
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None