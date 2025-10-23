from dotenv import load_dotenv
from google import genai
from openai import OpenAI
import os
# Load environment variables from .env file
load_dotenv()

# example usage of OpenAI and Gemini clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
genai_client = genai.Client()

def build_analysis_prompt(query: str) -> str:
    """
    Build a prompt for the LLM to analyze the query.
    """
    return f"""
You are an expert software analysis agent. Your task is to analyze the following issue.
Issue: {query}

Instructions:
1. Identify the main problem described in the issue.
2. Identify all relevant Files, Classes, and Functions/Methods involved.
3. After analysis, extract ALL referenced **code entities** (especially files, classes, and functions).
4. Then extract 5 relevant **keywords or concepts** from the issue that help in searching or contextualizing it. 
5. Focus only on code inside the project (e.g., `project/module.py`). Do not extract paths inside libraries like `/usr/lib/...`.
6. For code entities, include only clear identifiers like `project/dataset.py`, `Class Dataset`, or `def to_json_dict`.
7. Use concise and meaningful **keywords** that represent the topic (e.g., `invalid tag`, `serialization`, `data element parsing`).
8. Avoid vague or generic keywords like `error occurred`, `something wrong`, or `TypeError`.
9. Do **not** include explanations, line numbers, or extraneous info in code/entity extraction sections.

Use the exact format below for your response:
### Analysis Result
**Main Problem:** [Describe the main problem]
**Relevant Files:** [List of files, e.g., `file1.py`, `file2.py`]
**Relevant Classes:** [List of classes, e.g., `ClassName1`, `ClassName2`]
**Relevant Functions/Methods:** [List of functions/methods, e.g., `function_name1`, `method_name2`]
**Keywords/Concepts:** [List of keywords, e.g., `keyword1`, `keyword2`]
###

    """

# def analyze_query(query: str) -> str:
def analyze_query(query: str , model_provider="gemini") -> str:
    """
    Analyze the query using the LLM and return the structured analysis.
    """

    # Build the analysis prompt
    prompt = build_analysis_prompt(query)

    # example usage of OpenAI and Gemini clients
    if model_provider == "gemini":
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        response_text = response.text.strip()
        return response_text
    
    elif model_provider == "openai":
        response = openai_client.responses.create(
            model="gpt-5",
            input=prompt
        )
        response_text = response.output_text.strip()
        return response_text
    else:
        raise ValueError("Unsupported model provider")

def build_decipher_prompt(analysis_result: str):
    """
    Build a prompt for the LLM to decipher the analysis result.
    """
    return f"""
    You are a smart query generator for a hybrid code search system that supports:

    - Vector DB (semantic search)
    - Graph DB (Neo4j, Cypher language)

    ### Graph Schema
    You must generate Cypher queries using only the following node and relationship types and their properties.
    Assume that all nodes have a 'name' property (string) for identification, and 'File' nodes also have a 'path' property (string). 'Function' and 'Class' nodes also have 'id', 'lineno', 'end_lineno', 'file_path', and 'code_snippet' properties.

    The knowledge graph uses the following node types:
    - :File {{path: string, name: string}}
    - :Class {{id: string, name: string, lineno: int, end_lineno: int, file_path: string, code_snippet: string}}
    - :Function {{id: string, name: string, lineno: int, end_lineno: int, file_path: string, code_snippet: string}}
    - :Package {{name: string}}

    The graph uses the following relationships:
    - :CONTAINS_FUNCTION # File -> Function
    - :CONTAINS_CLASS    # File -> Class
    - :CALLS             # Function -> Function
    - :INHERITS          # Class -> Class
    - :OVERRIDES         # Function -> Function
    - :IMPORTS           # File -> Package

    ---

    You have the following structured analysis of a bug or issue report:
    {analysis_result}

    ---

    ## Task
    Given the structured analysis of a bug or issue report, generate the following two distinct outputs:

    ---

    1. **Vector Search Query (Natural Language)**
    - A natural language query for semantic search using concepts, keywords, and function names.
    - Focus on conveying the core bug scenario and terms like method names, error types, parameters, and expected behavior.

    2. **Graph Search Query (Cypher)**
    - Construct a precise Cypher query that adheres strictly to the provided Graph Schema.
    - **Begin by identifying the most relevant Function or Class nodes mentioned in the analysis_result using their 'name' property.** If multiple such nodes exist, match them all within a single `MATCH` clause using an `IN` operator.
    - **Use `OPTIONAL MATCH` to find related nodes** such as:
        - The `File` that `CONTAINS_FUNCTION` or `CONTAINS_CLASS` the matched node.
        - The `Class` that `CONTAINS_FUNCTION` the matched function.
        - Other `Function` nodes that the matched function `CALLS`.
    - **To handle multiple primary matches and avoid nested aggregations, use a `WITH` clause to group by the primary matched node (e.g., `f` for Function), and apply `COLLECT(DISTINCT ...)` for related items per primary node.** For example: `WITH f, COLLECT(DISTINCT file.path) AS files, COLLECT(DISTINCT c.name) AS classes, COLLECT(DISTINCT calledF.name) AS calledFunctions`.
    - **In the `RETURN` clause, use `COLLECT` to aggregate results into a list of maps**, each representing a primary node and its collected relations (e.g., `RETURN COLLECT({{name: f.name, files: files, classes: classes, called: calledFunctions}}) AS results).
    - You can filter nodes based on their 'name' or 'path' properties in `WHERE` clauses where necessary.
    - Do not invent new labels, relationship types, or properties not explicitly listed in the schema.
    - Prioritize queries that explore the immediate structural neighborhood of the key affected entities.
    - Ensure no aggregate functions are used inside other aggregate functions to prevent syntax errors.

    ---

    ### Output Format

    Respond in this format only:
    vector_query: |
    <your vector search query here>

    cypher_query: |
    <your Cypher query here>

    """

def decipher_analysis(analysis_result: str, model_provider="gemini") -> str:
    """
    Decipher the analysis result to generate vector and Cypher queries.
    """
    # example usage of OpenAI and Gemini clients
    prompt = build_decipher_prompt(analysis_result)
    if model_provider == "gemini":
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        response_text = response.text.strip()
        return response_text
    
    elif model_provider == "openai":
        response = openai_client.responses.create(
            model="gpt-5",
            input=prompt
        )
        response_text = response.output_text.strip()
        return response_text
    else:
        raise ValueError("Unsupported model provider")
    

def get_vector_and_cypher_queries(original_query: str, model_provider="gemini"):
    print("Analyzing the original issue by LLM...")
    analysis_result = analyze_query(original_query, model_provider=model_provider)
    print("Analysis completed !")
    
    print("Generating Vector and Cypher queries by LLM...")
    queries = decipher_analysis(analysis_result, model_provider=model_provider)

    # Extract from YAML-style block
    import re
    match_vec = re.search(r'vector_query:\s*\|\s*(.*?)\n(?:cypher_query:|$)', queries, re.DOTALL)
    match_cyp = re.search(r'cypher_query:\s*\|\s*(.*)', queries, re.DOTALL)

    vector_query = match_vec.group(1).strip() if match_vec else ""
    cypher_query = match_cyp.group(1).strip() if match_cyp else ""
    print("Query Generation Completed !")

    return analysis_result, vector_query, cypher_query
