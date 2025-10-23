import os
import pandas as pd
import shutil
import time
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from knowledge_base import knowledge_base as kb
from query_kb.query_analyser import get_vector_and_cypher_queries
from query_kb.dual_search import run_vector_query, run_cypher_query
from patch_generation.generate_patch import generate_patch
from patch_generation.patch_scorar import score_patches

DATASET_PATH = "dataset/swe-bench-lite-test.xlsx"
OUTPUT_PATH = "llm_response/patch_results.xlsx"
df = pd.read_excel(DATASET_PATH)
print(f"Dataset loaded with {len(df)} entries.")

# example model provider
MODEL_PROVIDER = "openai"

# Load old results if exists
if os.path.exists(OUTPUT_PATH):
    old_df = pd.read_excel(OUTPUT_PATH)
    results = old_df.to_dict('records')  # Convert to list of dicts
else:
    results = []

start_idx = 11
end_idx = 20 

for idx, row in df.iterrows():
    # if idx == 1:
    #     break
    if idx < start_idx:
        continue  
    if idx > end_idx:
        break


    print(f"\n--- Processing entry {idx+1}/{len(df)} ---")
    start_time = time.time()

    # Clear DBs (avoid cross contamination)
    kb.clear_dbs()
    print(f"Cleared databases for next iteration.")
    ### Step 1: Build Knowledge Base ###
    repo_path = row['repo']
    
    # Construct full GitHub URL
    REPO_URL = f"https://github.com/{repo_path}.git"
    # print(f"Repo URL from dataset: {REPO_URL}")
    BASE_COMMIT_HASH = row['base_commit']
    
    repo_name = repo_path.split('/')[-1]
    LOCAL_REPO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "repos", repo_name)

    print(f"Processing repo: {repo_name}")
    print(f"  REPO_URL: {REPO_URL}")
    print(f"  BASE_COMMIT_HASH: {BASE_COMMIT_HASH}")
    print(f"  LOCAL_REPO_PATH: {LOCAL_REPO_PATH}")

    # Run the ingestion for each repo
    kb.run_ingestion(REPO_URL, LOCAL_REPO_PATH, BASE_COMMIT_HASH)

    ## Step 2: Vector and Graph DB Search
    original_issue = row['problem_statement']

    analysis_result, vector_query, cypher_query = get_vector_and_cypher_queries(original_issue, model_provider=MODEL_PROVIDER)
    vector_results = run_vector_query(vector_query)
    graph_results = run_cypher_query(cypher_query)

    ## Step 3: Patch Generation
    patch_text = generate_patch(original_issue, vector_results, graph_results, model_provider=MODEL_PROVIDER)

    ## Step 4: Patch Scoring
    all_patches_in_list, file_name, func_name, patch_scores, best_patch = score_patches(str(patch_text), original_issue, model_provider=MODEL_PROVIDER)

    ## Step 5: Save results to DataFrame
    results.append({
        'serial_no': idx + 1,
        'repo': repo_path,
        'base_commit': BASE_COMMIT_HASH,
        'issue': original_issue,
        'vector_query': vector_query,
        'cypher_query': cypher_query,
        'analysis_result': analysis_result,
        'generated_patch': patch_text,
        'all_patches': all_patches_in_list,
        'patch_scores': patch_scores,
        'best_patch_dict': best_patch,
        'best_patch_score': best_patch["total"] if best_patch else None,
        'best_patch_code': best_patch["func"] if best_patch else None,
        'file_name': file_name,
        'function_name': func_name,
        'model_provider': MODEL_PROVIDER
    })

    # Save results to Excel
    output_df = pd.DataFrame(results)
    output_df.to_excel(OUTPUT_PATH, index=False)
    print(f"Results saved to {OUTPUT_PATH}")

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Time taken to process issue {idx+1}: {elapsed_time/60:.3f} minutes")
    