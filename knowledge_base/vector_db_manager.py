import weaviate
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.collections import Collection
from weaviate.classes.config import Property, DataType, Configure
from weaviate.classes.init import AdditionalConfig, Timeout
from tqdm import tqdm
import shutil

import weaviate
import weaviate.classes.config as wc_config
import weaviate.classes.query as wvc_query
import weaviate.classes.data as wvc_data
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import os
import torch

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class VectorDBManager:
    """
    Manages a Weaviate vector database for storing and querying
    embeddings of text/code snippets along with metadata.
    """

    def __init__(self, weaviate_url: str, collection_name: str, api_key: str = None, model_name: str = "/models/codebert-base"):
        """
        Initializes the Weaviate client and embedding model (if not using Weaviate's built-in).

        Args:
            weaviate_url (str): URL of the Weaviate instance.
            collection_name (str): Name of the Weaviate collection.
            api_key (str, optional): Weaviate Cloud Services API Key. Defaults to None.
            model_name (str, optional): HuggingFace model name for sentence embeddings .
        """
        self.weaviate_url = weaviate_url
        self.collection_name = collection_name
        self.api_key = api_key

        try:
            # Connect to Weaviate
            if self.api_key:
                auth_config = weaviate.Auth.api_key(api_key)
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=self.weaviate_url,
                    auth_credentials=auth_config
                )
            else:
                self.client = weaviate.connect_to_local(
                    host="localhost",
                    port=8080,
                    grpc_port=50051 # For gRPC, which Weaviate v4 client uses
                )

            # Check if Weaviate is ready
            if not self.client.is_ready():
                raise ConnectionError("Weaviate instance is not ready.")

            # Get or create the collection
            # Define properties for the schema
            properties = [
                wc_config.Property(name="text", data_type=wc_config.DataType.TEXT, description="The code/text snippet"),
                wc_config.Property(name="type", data_type=wc_config.DataType.TEXT, description="Type of snippet (e.g., function_code, docstring)"),
                wc_config.Property(name="file", data_type=wc_config.DataType.TEXT, description="File path of the snippet"),
                wc_config.Property(name="name", data_type=wc_config.DataType.TEXT, description="Name of the function/class"),
                wc_config.Property(name="lineno", data_type=wc_config.DataType.INT, description="Line number", skip_vectorization=True, skip_indexing=True), # Line number likely not useful for vector search, skip vectorization
                wc_config.Property(name="snippet_id", data_type=wc_config.DataType.TEXT, description="Unique ID for the snippet", skip_vectorization=True),
            ]

            vector_config = wc_config.Configure.Vectors.self_provided()

            if self.client.collections.exists(self.collection_name):
                print(f"Connected to existing Weaviate collection '{self.collection_name}'.")
                self.collection = self.client.collections.get(self.collection_name)
            else:
                print(f"Collection '{self.collection_name}' not found. Creating it...")
                self.collection = self.client.collections.create(
                    name=self.collection_name,
                    properties=properties,
                    vector_config=vector_config, # Pass the vectorizer config here
                )
                print(f"Collection '{self.collection_name}' created successfully.")

            # Initialize local SentenceTransformer if not using Weaviate's built-in vectorizer
            self.embedding_model = None
            if model_name:
                self.embedding_model = SentenceTransformer(model_name, device='cuda' if torch.cuda.is_available() else 'cpu')
                print(f"Using local embedding model: {model_name}")
            else:
                print("Using Weaviate's built-in vectorizer (text2vec-transformers).")

        except Exception as e:
            print(f"Error initializing Weaviate: {e}")
            raise

    def ingest_data(self, data_points: list, batch_size: int = 128):
        """
        Generates embeddings (if using local model) and ingests data into Weaviate.

        Args:
            data_points (list of dicts): Each dict must have 'text' and 'metadata' keys.
            batch_size (int): Number of items to embed and insert per batch.
        """
        print(f"Ingesting {len(data_points)} data points into Weaviate...")

        if not data_points:
            print("No data points to ingest into Weaviate.")
            return

        # Prepare data for Weaviate
        weaviate_objects = []
        for i, dp in enumerate(data_points):
            item_id = dp['metadata'].get('snippet_id')
            if item_id is None:
                pass

            # Prepare properties for Weaviate object
            properties = {
                "text": dp["text"],
                "type": dp["metadata"].get("type"),
                "file": dp["metadata"].get("file"),
                "name": dp["metadata"].get("name"),
                "lineno": dp["metadata"].get("lineno"),
                "snippet_id": dp["metadata"].get("snippet_id") # Store the original ID as a property
            }
            weaviate_objects.append(properties)

        # Ingest into Weaviate using batching
        total_objects_added = 0
        with self.collection.batch.dynamic() as batch:
            for i in tqdm(range(0, len(weaviate_objects), batch_size), desc="Adding to Weaviate"):
                batch_data = weaviate_objects[i:i + batch_size]
                if self.embedding_model: # If using a local embedding model
                    batch_docs = [obj["text"] for obj in batch_data]
                    
                    batch_embeddings = self.embedding_model.encode(batch_docs, batch_size=8, show_progress_bar=False).tolist()
                    for j, obj_properties in enumerate(batch_data):
                        batch.add_object(
                            properties=obj_properties,
                            vector=batch_embeddings[j]
                        )
                else: 
                    for obj_properties in batch_data:
                        batch.add_object(
                            properties=obj_properties
                        )
                total_objects_added += len(batch_data)

            # Check for errors after batching (Weaviate's batching handles errors internally)
            if batch.number_errors > 0:
                print(f"Weaviate batching finished with {batch.number_errors} errors.")
                for err in batch.failed_objects:
                    print(f"Failed object: {err.object_}")
                    print(f"Error message: {err.message}")

        print(f"Finished ingesting into Weaviate. Total items now: {self.collection.aggregate.over_all(total_count=True).total_count}")


    def get_collection(self):
        """
        Returns the Weaviate collection object for custom querying.

        Returns:
            weaviate.collections.Collection: The underlying Weaviate collection.
        """
        return self.client.collections.get(self.collection_name)

    def delete_collection(self):
        try:
            if self.client.collections.exists(self.collection_name):
                self.client.collections.delete(self.collection_name)
                print(f"Collection '{self.collection_name}' deleted.")
            else:
                print(f"Collection '{self.collection_name}' does not exist.")

            # Delete local disk data if running in local mode
        except Exception as e:
            print(f"Error deleting collection '{self.collection_name}': {e}")

    def close(self):
        """Closes the Weaviate client connection."""
        if self.client:
            self.client.close()
            print("Weaviate client connection closed.")

