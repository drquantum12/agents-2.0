from db_utility.vector_db import VectorDB

vector_db = VectorDB()

if __name__ == "__main__":
    sample_query = "Folklore story from nagaland"
    context, _ = vector_db.get_similar_documents(sample_query, top_k=3)
    print(f"context: {context} ")