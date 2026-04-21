import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

MILVUS_URI = os.getenv("MILVUS_URI")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN")
CACHE_COLLECTION = "semantic_cache"
CACHE_THRESHOLD = 0.92


class SemanticCache:
    """Milvus-backed semantic cache. Returns cached responses for near-identical queries."""

    def lookup(self, query: str, threshold: float = CACHE_THRESHOLD) -> Optional[dict]:
        """Return {'response': str, 'mode': str} if a cached hit exists, else None."""
        try:
            from pymilvus import MilvusClient
            from app.db_utility.vector_db import generate_embedding

            client = MilvusClient(uri=MILVUS_URI, token=MILVUS_TOKEN)
            if not client.has_collection(CACHE_COLLECTION):
                return None

            embedding = generate_embedding(query)
            results = client.search(
                collection_name=CACHE_COLLECTION,
                data=[embedding],
                anns_field="embedding",
                search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
                limit=1,
                output_fields=["response", "teaching_mode"],
            )
            if results and results[0]:
                hit = results[0][0]
                score = hit.get("distance", 0.0)
                if score >= threshold:
                    logger.info(f"Semantic cache hit (score={score:.3f})")
                    return {
                        "response": hit["entity"]["response"],
                        "mode": hit["entity"]["teaching_mode"],
                    }
        except Exception as e:
            logger.warning(f"Semantic cache lookup failed: {e}")
        return None

    def store(self, query: str, response: str, mode: str) -> None:
        """Store a query–response pair in the semantic cache."""
        try:
            from pymilvus import MilvusClient, DataType, FieldSchema, CollectionSchema
            from app.db_utility.vector_db import generate_embedding

            client = MilvusClient(uri=MILVUS_URI, token=MILVUS_TOKEN)
            if not client.has_collection(CACHE_COLLECTION):
                self._create_collection(client)

            embedding = generate_embedding(query)
            client.insert(
                collection_name=CACHE_COLLECTION,
                data=[{
                    "query_hash": str(hash(query)),
                    "response": response[:4096],
                    "teaching_mode": mode,
                    "embedding": embedding,
                }],
            )
        except Exception as e:
            logger.warning(f"Semantic cache store failed: {e}")

    def _create_collection(self, client) -> None:
        from pymilvus import DataType, FieldSchema, CollectionSchema

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="query_hash", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="response", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="teaching_mode", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768),
        ]
        schema = CollectionSchema(fields=fields, description="Semantic cache for vijayebhav")
        client.create_collection(collection_name=CACHE_COLLECTION, schema=schema)
        client.create_index(
            collection_name=CACHE_COLLECTION,
            index_params=[{
                "field_name": "embedding",
                "index_type": "IVF_FLAT",
                "metric_type": "COSINE",
                "params": {"nlist": 128},
            }],
        )
        logger.info(f"Created Milvus collection: {CACHE_COLLECTION}")
