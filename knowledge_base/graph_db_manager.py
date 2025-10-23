"""
GraphDBManager: Manages a Neo4j-based Graph Database for representing software artifacts,
like source code symbols (files, classes, functions) and commit history (commits, diffs).

Dependencies:
- neo4j
- tqdm
- os

Usage:
-------
# Initialize
graph_db = GraphDBManager(uri="bolt://localhost:7687", user="neo4j", password="password")

# Load code symbols
graph_db.populate_graph_from_code_data(code_graph_data)

# Load commits
graph_db.populate_graph_from_commits(commits_data)

# Close connection
graph_db.close()
"""

from neo4j import GraphDatabase
from tqdm import tqdm
import os

class GraphDBManager:
    """
    Neo4j client for ingesting source code symbol graphs and Git commit graphs.
    """
    def __init__(self, uri: str, user: str, password: str):
        """
        Connects to Neo4j database.

        Args:
            uri (str): Bolt URI of Neo4j instance (e.g., bolt://localhost:7687).
            user (str): Neo4j username.
            password (str): Neo4j password.
        """
        self._driver = None
        try:
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
            self._driver.verify_connectivity()
            print("Successfully connected to Neo4j.")
        except Exception as e:
            print(f"Failed to connect to Neo4j at {uri}: {e}")
            raise

    def close(self):
        """Closes the Neo4j driver connection."""
        if self._driver:
            self._driver.close()
            print("Neo4j connection closed.")

    def _execute_query(self, query: str, parameters: dict = None):
        """
        Executes a Cypher query with optional parameters.

        Args:
            query (str): The Cypher query string.
            parameters (dict): Parameters for the Cypher query.
        """
        with self._driver.session() as session:
            return session.run(query, parameters)
    
    def get_driver(self):
        """
        Returns the Neo4j driver instance.
        """
        return self._driver

    def merge_node(self, label: str, properties: dict, unique_key: str):
        """
        Creates or updates a node with a unique identifier.

        Args:
            label (str): Node label (e.g., 'Function', 'Class').
            properties (dict): All properties to set/update on the node.
            unique_key (str): Property used to uniquely identify the node.
        """
        query = (
            f"MERGE (n:{label} {{{unique_key}: $unique_val}}) "
            f"ON CREATE SET n = $props "
            f"ON MATCH SET n += $props " # Update existing properties on match
            f"RETURN n"
        )
        parameters = {
        "props": properties,
        "unique_val": properties[unique_key]
    }
        self._execute_query(query, parameters)

    def merge_relationship(self, node1_label: str, node1_unique_key: str, node1_unique_val,
                           rel_type: str,
                           node2_label: str, node2_unique_key: str, node2_unique_val,
                           rel_properties: dict = {}):
        """
        Creates or updates a relationship between two nodes.

        Args:
            node1_label (str): Label of start node.
            node1_unique_key (str): Unique property of start node.
            node1_unique_val (str): Value of unique property.
            rel_type (str): Relationship type (e.g., 'CONTAINS_CLASS').
            node2_label (str): Label of end node.
            node2_unique_key (str): Unique property of end node.
            node2_unique_val (str): Value of unique property.
            rel_properties (dict): Optional properties for the relationship.
        """
        query = (
            f"MATCH (a:{node1_label} {{{node1_unique_key}: $val1}}), "
            f"(b:{node2_label} {{{node2_unique_key}: $val2}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"ON CREATE SET r = $rel_props "
            f"ON MATCH SET r += $rel_props " # Update relationship properties on match
            f"RETURN r"
        )
        # self._execute_query(query, val1=node1_unique_val, val2=node2_unique_val, rel_props=rel_properties)
        parameters = {
        "val1": node1_unique_val,
        "val2": node2_unique_val,
        "rel_props": rel_properties
    }
        self._execute_query(query, parameters)

    def populate_graph_from_code_data(self, code_graph_data: dict, symbol_table: dict):
        print("Populating Neo4j with Code Symbol Graph data...")

        for filepath, symbols in tqdm(code_graph_data.items(), desc="Adding Code Nodes"):
            self.merge_node("File", {"path": filepath, "name": os.path.basename(filepath)}, "path")

            for func in symbols.get("functions", []):
                func_id = f"{filepath}::{func['name']}"
                self.merge_node("Function", {
                    "id": func_id,
                    "name": func["name"],
                    "lineno": func["lineno"],
                    "end_lineno": func["end_lineno"],
                    "file_path": filepath,
                    "code_snippet": func["code_snippet"],
                    "is_static": func.get("is_static", False),
                }, "id")
                self.merge_relationship("File", "path", filepath, "CONTAINS_FUNCTION", "Function", "id", func_id)

            for cls in symbols.get("classes", []):
                cls_id = f"{filepath}::{cls['name']}"
                self.merge_node("Class", {
                    "id": cls_id,
                    "name": cls["name"],
                    "lineno": cls["lineno"],
                    "end_lineno": cls["end_lineno"],
                    "file_path": filepath,
                    "code_snippet": cls["code_snippet"]
                }, "id")
                self.merge_relationship("File", "path", filepath, "CONTAINS_CLASS", "Class", "id", cls_id)

                # Class Attributes
                for attr in cls.get("attributes", []):
                    attr_id = f"{cls_id}::{attr}"
                    self.merge_node("Attribute", {
                        "id": attr_id,
                        "name": attr,
                        "class_id": cls_id,
                        "file_path": filepath,
                    }, "id")
                    self.merge_relationship("Class", "id", cls_id, "HAS_ATTRIBUTE", "Attribute", "id", attr_id)

                # INHERITS + OVERRIDES
                for base in cls.get("bases", []):
                    base_id = symbol_table.get(base)
                    if base_id:
                        self.merge_relationship("Class", "id", cls_id, "INHERITS", "Class", "id", base_id)

                        for func in symbols.get("functions", []):
                            if "." in func["name"] and func["name"].startswith(cls["name"] + "."):
                                method_name = func["name"].split(".")[1]
                                target_symbol = f"{base}.{method_name}"
                                overridden_id = symbol_table.get(target_symbol)
                                if overridden_id:
                                    self.merge_relationship("Function", "id", f"{filepath}::{func['name']}",
                                                            "OVERRIDES", "Function", "id", overridden_id)

            for pkg in symbols.get("imports", []):
                self.merge_node("Package", {"name": pkg}, "name")
                self.merge_relationship("File", "path", filepath, "IMPORTS", "Package", "name", pkg)

            for caller, callees in symbols.get("calls", {}).items():
                caller_id = f"{filepath}::{caller}"
                for callee in callees:
                    callee_id = symbol_table.get(callee)

                    # Try resolving dotted calls like module.func or Class.method
                    if not callee_id and "." in callee:
                        base, member = callee.split(".", 1)
                        alias = symbols.get("aliases", {}).get(base, base)
                        full_name = f"{alias}.{member}"
                        callee_id = symbol_table.get(full_name)

                    if callee_id:
                        self.merge_relationship("Function", "id", caller_id, "CALLS", "Function", "id", callee_id)
    

    # for design patterns detection
    def populate_design_patterns(self, all_patterns: dict, symbol_table: dict):
        """
        Adds detected design pattern nodes and their participants to the graph.
        """
        print("Populating Neo4j with Design Pattern data...")

        for filepath, patterns in all_patterns.items():
            for entry in patterns:
                pattern = entry["pattern"]
                self.merge_node("DesignPattern", {"name": pattern}, "name")

                if "class" in entry:
                    cls_id = f"{filepath}::{entry['class']}"
                    self.merge_relationship("Class", "id", cls_id,
                                            "PARTICIPATES_IN", "DesignPattern", "name",
                                            pattern, {"role": entry.get("role", "Participant")})

                elif "function" in entry:
                    func_id = f"{filepath}::{entry['function']}"
                    self.merge_relationship("Function", "id", func_id,
                                            "PARTICIPATES_IN", "DesignPattern", "name",
                                            pattern, {"role": entry.get("role", "Participant")})
    
    def delete_graph(self):
        """
        Deletes all nodes and relationships in the Neo4j database.
        Use with caution!
        """
        print("Deleting all nodes and relationships in the Neo4j database...")
        query = "MATCH (n) DETACH DELETE n"
        self._execute_query(query)
        print("All data deleted from Neo4j.")


    def populate_graph_from_commits(self, commits_data: list):
        """
        Adds commit history and file modifications to the graph.

        Args:
            commits_data (list): List of dicts:
            {
                "hexsha": str,
                "author": str,
                "message": str,
                "committed_date": datetime,
                "parents": [str],
                "diffs": [
                    {
                        "a_path": str,
                        "b_path": str,
                        "change_type": "A" | "M" | "D",
                        "diff_text": str
                    }
                ]
            }
        """
        print("Populating Neo4j with Commit Graph data...")
        for commit in tqdm(commits_data, desc="Adding Commit Nodes and Relationships"):
            # Create or update Commit node
            self.merge_node("Commit", {
                "hexsha": commit["hexsha"],
                "author": commit["author"],
                "message": commit["message"],
                "timestamp": commit["committed_date"].isoformat()
            }, "hexsha")

            # Link to parent commits
            for parent_sha in commit["parents"]:
                self.merge_node("Commit", {"hexsha": parent_sha}, "hexsha") # Ensure parent node exists
                self.merge_relationship("Commit", "hexsha", commit["hexsha"], "PARENT_OF", "Commit", "hexsha", parent_sha)

            # Link commit to modified/added/deleted files
            for diff in commit["diffs"]:
                if diff["b_path"]: # File was modified or added
                    self.merge_node("File", {"path": diff["b_path"], "name": os.path.basename(diff["b_path"])}, "path")
                    self.merge_relationship(
                        "Commit", "hexsha", commit["hexsha"],
                        "MODIFIES",
                        "File", "path", diff["b_path"],
                        {"change_type": diff["change_type"], "diff_text": diff["diff_text"]}
                    )
                elif diff["a_path"] and diff["change_type"] == 'D': # File was deleted
                    self.merge_node("File", {"path": diff["a_path"], "name": os.path.basename(diff["a_path"])}, "path")
                    self.merge_relationship(
                        "Commit", "hexsha", commit["hexsha"],
                        "DELETES", # Specific relationship for deletion, or just MODIFIES
                        "File", "path", diff["a_path"],
                        {"change_type": diff["change_type"], "diff_text": diff["diff_text"]}
                    )
        print(f"Processed {len(commits_data)} commits for graph.")