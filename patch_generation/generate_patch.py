import sys
import os
from dotenv import load_dotenv
from google import genai
from openai import OpenAI
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Load environment variables from .env file
load_dotenv()

from query_kb.dual_search import run_weaviate_hybrid_query, run_neo4j_cypher_query, original_issue, vector_query, cypher_query
from query_kb.query_analyser import get_vector_and_cypher_queries
from util.find_dir import get_root_directory

# example usage of OpenAI and Gemini clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
genai_client = genai.Client()

# ========= BUILD PROMPT =========
def build_patch_generation_prompt(issue: str, weaviate_results: list, neo4j_results: list):
    """
    Build a prompt for the LLM to generate a patch based on the issue description.
    """
    return f"""
    You are an expert software engineer and bug-fixer assistant.
    ## Issue Description
    The following issue has been reported:
    {issue}

    ## Contextual Code Search Results

    ### Vector DB (Weaviate) Results:
    - These contain semantically relevant code snippets or usages based on the issue description.
    - Review each result and determine its relevance to the issue.
    - Weaviate Results: 
    {weaviate_results}
    
    ### Graph DB (Neo4j) Results:
    - These include symbols (functions/classes etc.) and their relationships (calls, inherits, overrides etc.) from a code graph.
    - Assess how these code entities are connected to the issue and which ones are likely involved.
    - Neo4j Results:
    {neo4j_results}


    ## Tasks

    1. **Relevance Assessment**:
    - Identify which results from both Weaviate and Neo4j are truly relevant to the issue.
    - Justify briefly (internally) why you consider them relevant.

    2. **Fault Localization**:
    - From the relevant entities, determine specific files, classes, or functions where code changes should be made.
    - Focus only on project files (ignore external packages).

    3. **Patch Generation**:
    - Propose **five alternative patch candidates** that address the core issue.
    - Focus on the functions or classes where faults were detected.
    - Each patch must:
        - Address the core problem clearly.
        - Be minimal and safe (avoid side effects).
        - Be syntactically correct and ready for integration.
    - Be provided in **both formats**:
        - A) The full updated function(s)
        - B) A unified diff format compatible with `git apply`

    ## Output Format

    ### Step 1: Localized Faulty Components
    List the files, classes, or functions where changes are to be made. Example:
    ```
    - File: project/module.py
    - Class: MyClass
    - Function: my_function
    ```

    ### Step 2: Candidate Patch 1 to 5
    Respond with **five** separate patch blocks. For each candidate, provide both:

    ```
    #### Candidate Patch (Full Function)
    # Candidate Patch X
    # File: pydicom/dataset.py

    def to_json_dict(...):
        # Your patch here
    ...
    (Continue with Candidate Patch 1, 2 3, 4, 5)
    ...

    #### Candidate Patch (Unified Diff)
    # Candidate Patch X (Unified Diff)

    diff --git a/pydicom/dataset.py b/pydicom/dataset.py
    --- a/pydicom/dataset.py
    +++ b/pydicom/dataset.py
    @@ def my_function(...):
    -    # original faulty line
    +    # new fixed line

    ...
    (Continue with Candidate Patch 1, 2 3, 4, 5)

    ```
    ## Notes
    - Do NOT include explanations outside the code blocks.
    - Keep patches minimal — avoid unnecessary changes.
    - If multiple files or functions are involved, include all necessary edits in both formats.
    - Only include docstrings if they are crucial to explain new logic. Otherwise omit them.
    - If you must include docstrings, include them only in the full function, not in the unified diff.
    - The unified diff must be valid for `git apply`.
    """

def generate_patch(issue: str, weaviate_results: str, neo4j_results: str, model_provider="gemini"):
    patch_prompt = build_patch_generation_prompt(issue, weaviate_results, neo4j_results)

    # example usage of LLM to generate patch
    print("Patch Generation by LLM...")    
    if model_provider == "gemini":
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash", contents=patch_prompt
        )
        patch_text = response.text.strip()
        print("Patch Generation completed !")
        return patch_text
    elif model_provider == "openai":
        response = openai_client.responses.create(
            model="gpt-5",
            input=patch_prompt
        )
        patch_text = response.output_text.strip()
        print("Patch Generation completed !")
        return patch_text
    else:
        raise ValueError("Invalid model provider.")
        
# main function to run the patch generation
if __name__ == "__main__":
    generate_patch()