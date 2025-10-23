import sys 
import os
from pprint import pprint

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from knowledge_base.graph_db_manager import GraphDBManager
from knowledge_base.vector_db_manager import VectorDBManager
import knowledge_base.config as config
import weaviate.classes.query as wvc_query

from query_kb.query_analyser import get_vector_and_cypher_queries



def run_weaviate_hybrid_query(query_text: str):
    # Initialize DB and get collection
    print("Running Weaviate Hybrid Search...")
    db = VectorDBManager(config.WEAVIATE_URL, config.WEAVIATE_COLLECTION_NAME, 
                         config.WEAVIATE_API_KEY, 
                         model_name=config.EMBEDDING_MODEL_NAME
                         )
    collection = db.get_collection()
    n_results_hybrid = 10
    alpha_hybrid = 0.7  # 0.7 means 70% vector, 30% BM25F
    weaviate_results = [] # Initialize an empty list to store results
    try:
        query_vector = None
        if db.embedding_model:
            query_vector = db.embedding_model.encode(query_text).tolist()

        response_hybrid = collection.query.hybrid(
            query=query_text,
            vector=query_vector,
            alpha=alpha_hybrid,
            limit=n_results_hybrid,
            return_properties=["text", "type", "file", "name", "lineno", "snippet_id"],
            return_metadata=wvc_query.MetadataQuery(score=True, explain_score=True)
        )

        # print("\nTop Matches for Hybrid Search (combining semantic and keyword):")
        for o in response_hybrid.objects:
            # Filter for usage context or function code as per your original request
            if o.properties.get("type") in ["usage_context", "function_code"]:
                result_data = {
                    "file": o.properties.get('file'),
                    "function_type": o.properties.get('name'),
                    "type": o.properties.get('type'),
                    "text": o.properties.get('text'),
                    "score": o.metadata.score,
                }
                weaviate_results.append(result_data)

        print("Weaviate Hybrid Search completed !")
    except Exception as e:
        print(f"Error during hybrid search: {e}")
    finally:
        if db:
            db.close()
    return weaviate_results

def run_neo4j_cypher_query(cypher_query: str):
    """
    Run a Cypher query against the Neo4j database.
    """
    print("Running Neo4j Cypher Query...")
    graph_db = GraphDBManager(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
    neo4j_results = [] # Initialize an empty list for Neo4j results
    driver = graph_db.get_driver()
    try:
        records, summary, keys = driver.execute_query(
        cypher_query,
        parameters_={"limit": 10},
        database_="neo4j", 
        routing_="r" 
    )
        for record in records:
            neo4j_results.append(record)
        print("Neo4j Cypher Query completed !")
    
    except Exception as e:
        print(f"Error running Cypher query: {e}")
    finally:
        if graph_db:
            graph_db.close()
    return neo4j_results

# Wrapper functions for easier external calls
def run_vector_query(query_text: str):
    return run_weaviate_hybrid_query(query_text)

def run_cypher_query(cypher_query: str):
    return run_neo4j_cypher_query(cypher_query)