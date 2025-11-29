from google.cloud.firestore import Client
from typing_extensions import TypedDict

firestore_client = Client()

class StudentBasicMetrics(TypedDict):
    overall_accuracy: float
    average_accuracy: float
    average_score: float
    subject_wise_accuracy: dict[str, float]
    subject_wise_average_score: dict[str, float]
    quizzes_taken_count: int
    subject_wise_quizzes_taken_count: dict[str, int]
    difficulty_wise_accuracy: dict[str, float]
    difficulty_wise_average_score: dict[str, float]
    difficulty_wise_quizzes_taken_count: dict[str, int]


class FirestoreDB:
    def __init__(self, collection_name: str):
        self.collection = firestore_client.collection(collection_name)

    def add_or_update_document(self, doc_id: str, data: dict):
        """
        Add or update a document in the Firestore collection.
        
        :param doc_id: The ID of the document to add or update.
        :param data: A dictionary containing the data to be stored.
        """
        try:
            doc_ref = self.collection.document(doc_id)
            doc_ref.set(data, merge=True)
        except Exception as e:
            raise ValueError(f"Failed to add or update document: {e}")
    
    def get_document(self, doc_id: str) -> dict:
        """
        Retrieve a document from the Firestore collection.
        
        :param doc_id: The ID of the document to retrieve.
        :return: A dictionary containing the document data.
        """
        doc_ref = self.collection.document(doc_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            raise ValueError(f"Document with ID {doc_id} does not exist.")
        
    def delete_document(self, doc_id: str):
        """
        Delete a document from the Firestore collection.
        
        :param doc_id: The ID of the document to delete.
        """
        doc_ref = self.collection.document(doc_id)
        doc_ref.delete()
    
student_metrics_collection = FirestoreDB("student_metrics")