from vector_db import VectorDB

def test_vector_db():
    vector_db = VectorDB()
    query = "What is photosynthesis?"
    results = vector_db.get_similar_documents(query, top_k=5)
    print(results)




if __name__ == "__main__":
    test_vector_db()