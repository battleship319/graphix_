import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import knowledge_base.config as config
from knowledge_base.repo_parser import clone_or_pull_repo
from knowledge_base.code_parser import build_code_symbol_graph_data
from knowledge_base.vector_db_manager import VectorDBManager
from knowledge_base.graph_db_manager import GraphDBManager

def extract_docstring(code_snippet: str) -> str:
    """
    Extracts the top-level docstring (if any) from a code snippet.
    Assumes triple-quoted docstring comes immediately after def/class.
    """
    import ast
    try:
        tree = ast.parse(code_snippet)
        docstring = ast.get_docstring(tree)
        return docstring or ""
    except Exception:
        return ""

def extract_inline_comments(code_snippet: str) -> list:
    """
    Extracts # comments from the code (line-based heuristic).
    """
    comments = []
    for line in code_snippet.splitlines():
        line = line.strip()
        if "#" in line:
            idx = line.index("#")
            comment = line[idx:]
            if len(comment) > 2:
                comments.append(comment)
    return comments
 
def run_ingestion(repo_url, local_repo_path, base_commit_hash):
    print(f"Starting ingestion for repo: {repo_url}")

    vector_db_manager = None
    graph_db_manager = None
    try:
        vector_db_manager = VectorDBManager(
            config.WEAVIATE_URL,
            config.WEAVIATE_COLLECTION_NAME,
            config.WEAVIATE_API_KEY,
            model_name="/models/codebert-base"
        )
        graph_db_manager = GraphDBManager(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)

        # 1. Clone or Pull Repository
        clone_or_pull_repo(repo_url, local_repo_path)

        # 2. Extract code symbols (functions, classes, calls, imports, etc.)
        code_graph_data, symbol_table, pattern_data = build_code_symbol_graph_data(local_repo_path, base_commit_hash)

        weaviate_data_points = []

        # 3. Prepare code/function/class snippets and metadata
        for filepath, symbols in code_graph_data.items():

            # For function snippets
            for func in symbols.get("functions", []):
                func_id = f"{filepath}::func::{func['name']}"
                code = func['code_snippet']
                if not code:
                    continue

                # Extract docstring + comments
                doc = extract_docstring(code)
                comments = extract_inline_comments(code)

                # Add function usage context
                calls = symbols["calls"].get(func["name"]) or symbols["calls"].get(func["name"].split(".")[-1]) or []
                context_text = ""
                if calls:
                    context_text = f"{func['name']} calls: " + ", ".join(calls)

                weaviate_data_points.append({
                    "text": code,
                    "metadata": {
                        "type": "function_code",
                        "file": filepath,
                        "name": func['name'],
                        "lineno": func['lineno'],
                        "snippet_id": func_id
                    }
                })

                # Add docstring if exists
                if doc:
                    weaviate_data_points.append({
                        "text": doc,
                        "metadata": {
                            "type": "docstring",
                            "file": filepath,
                            "name": func['name'],
                            "snippet_id": f"{func_id}::docstring"
                        }
                    })

                # Add inline comments if any
                for i, comment in enumerate(comments):
                    weaviate_data_points.append({
                        "text": comment,
                        "metadata": {
                            "type": "comment",
                            "file": filepath,
                            "name": func['name'],
                            "snippet_id": f"{func_id}::comment::{i}"
                        }
                    })

                # Add function usage context
                if context_text:
                    weaviate_data_points.append({
                        "text": context_text,
                        "metadata": {
                            "type": "usage_context",
                            "file": filepath,
                            "name": func['name'],
                            "snippet_id": f"{func_id}::usage"
                        }
                    })

            # Same for classes
            for cls in symbols.get("classes", []):
                cls_id = f"{filepath}::class::{cls['name']}"
                code = cls['code_snippet']
                if not code:
                    continue

                doc = extract_docstring(code)
                comments = extract_inline_comments(code)

                weaviate_data_points.append({
                    "text": code,
                    "metadata": {
                        "type": "class_code",
                        "file": filepath,
                        "name": cls['name'],
                        "lineno": cls['lineno'],
                        "snippet_id": cls_id
                    }
                })

                if doc:
                    weaviate_data_points.append({
                        "text": doc,
                        "metadata": {
                            "type": "docstring",
                            "file": filepath,
                            "name": cls['name'],
                            "snippet_id": f"{cls_id}::docstring"
                        }
                    })

                for i, comment in enumerate(comments):
                    weaviate_data_points.append({
                        "text": comment,
                        "metadata": {
                            "type": "comment",
                            "file": filepath,
                            "name": cls['name'],
                            "snippet_id": f"{cls_id}::comment::{i}"
                        }
                    })

        # 4. Ingest into Weaviate
        vector_db_manager.ingest_data(weaviate_data_points, config.BATCH_SIZE)

        # 5. Ingest into Neo4j
        graph_db_manager.populate_graph_from_code_data(code_graph_data, symbol_table)

        # For design patterns
        if pattern_data:
            graph_db_manager.populate_design_patterns(pattern_data, symbol_table)

        print("\nData ingestion complete!")
        print(f"Weaviate data available at: {config.WEAVIATE_URL}")
        print(f"Neo4j Browser at: http://localhost:7474 (user: {config.NEO4J_USER}, pass: {config.NEO4J_PASSWORD})")

    except Exception as e:
        print(f"\nAn error occurred during ingestion: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if graph_db_manager:
            graph_db_manager.close()
        if vector_db_manager:
            vector_db_manager.close()
        print("Cleanup complete.")

def clear_dbs():
    """
    Delete collections/graphs to avoid cross contamination.
    """
    try:
        vdb = VectorDBManager(config.WEAVIATE_URL, config.WEAVIATE_COLLECTION_NAME, config.WEAVIATE_API_KEY)
        vdb.delete_collection()
        vdb.close()

        gdb = GraphDBManager(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
        gdb.delete_graph()
        gdb.close()

        print("Cleared Vector + Graph DBs.")
    except Exception as e:
        print(f"Error clearing DBs: {e}")

# keeping the main function for easier testing with fixed repos/commits
def main():
    run_ingestion(config.REPO_URL, config.LOCAL_REPO_PATH, config.BASE_COMMIT_HASH)

if __name__ == "__main__":
    main()