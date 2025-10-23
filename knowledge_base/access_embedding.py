import sys
import os
from pprint import pprint

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from knowledge_base.vector_db_manager import VectorDBManager
import knowledge_base.config as config
import weaviate.classes.query as wvc_query

# Initialize DB and get collection
db = VectorDBManager(config.WEAVIATE_URL, config.WEAVIATE_COLLECTION_NAME, config.WEAVIATE_API_KEY, model_name=None)
collection = db.get_collection()

# === Hybrid Search ===
print("\n=== Weaviate Hybrid Search ===")
query_hybrid = "functions that call dictionary_has_tag"
n_results_hybrid = 10
alpha_hybrid = 0.7  # 0.7 means 70% vector, 30% BM25F

try:
    response_hybrid = collection.query.hybrid(
        query=query_hybrid,
        alpha=alpha_hybrid,
        limit=n_results_hybrid,
        return_properties=["text", "type", "file", "name", "lineno", "snippet_id"],
        return_metadata=wvc_query.MetadataQuery(score=True, explain_score=True)
    )

    print("\nTop Matches for Hybrid Search (combining semantic and keyword):")
    for o in response_hybrid.objects:
        if o.properties.get("type") in ["usage_context", "function_code"]:
            print(f"\nFile: {o.properties.get('file')}")
            print(f"Function/Type: {o.properties.get('name')} ({o.properties.get('type')})")
            print(f"Text: {o.properties.get('text')}")
            print(f"Score: {o.metadata.score:.4f}")

except Exception as e:
    print(f"Error during hybrid search: {e}")

finally:
    if db:
        db.close()