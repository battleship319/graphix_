import ast
import difflib
import re
import subprocess
from typing import List, Tuple, Dict
import sys
import os
from google import genai
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from util.find_dir import get_root_directory
from query_kb.dual_search import original_issue

# example usage of OpenAI and Gemini clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
genai_client = genai.Client()

class PatchScorer:
    def __init__(self, full_function_code: str, diff_patch: str, issue_description: str = ""):
        self.full_code = full_function_code
        self.diff = diff_patch
        self.issue = issue_description

    def score_patch_size(self, max_threshold: int = 30) -> float:
        added_lines = [line for line in self.diff.splitlines() if line.startswith('+') and not line.startswith('+++')]
        removed_lines = [line for line in self.diff.splitlines() if line.startswith('-') and not line.startswith('---')]
        total = len(added_lines) + len(removed_lines)
        return 1.0 - min(total / max_threshold, 1.0)

    def score_syntax_correctness(self) -> float:
        try:
            ast.parse(self.full_code)
            return 1.0
        except SyntaxError:
            return 0.0

    def score_style_consistency(self) -> float:
        try:
            proc = subprocess.run(['flake8', '--stdin-display-name', 'patch.py', '-'], input=self.full_code.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            num_issues = len(proc.stdout.decode().splitlines())
            return 1.0 - min(num_issues / 10, 1.0)
        except FileNotFoundError:
            return 0.8  # Default fallback if flake8 not available

    def score_exception_safety(self) -> float:
        if re.search(r'except\s*:', self.full_code):
            return 0.3
        elif re.search(r'except\s+Exception', self.full_code):
            return 0.6
        else:
            return 1.0

    def score_docstring_penalty(self) -> float:
        docstrings = re.findall(r'""".*?"""|\'\'\'.*?\'\'\'', self.full_code, re.DOTALL)
        return 0.0 if docstrings else 1.0

    def score_variable_reuse(self) -> float:
        assignments = re.findall(r'(\w+)\s*=.*', self.full_code)
        return 1.0 if len(set(assignments)) <= 5 else 0.6

    def score_pattern_match(self) -> float:
        # Look for a safe try/except/fallback structure
        if 'try:' in self.full_code and 'except' in self.full_code and 'continue' in self.full_code:
            return 1.0
        return 0.5
    
    def score_llm_semantic(self, model_provider="gemini") -> float:
        prompt = f"""
        You are an expert Python code reviewer.You specialize in evaluaing patches solving software bugs in project repositories.
        
        ## Task
        Given the issue description and the patch below, rate the patch from 0 to 1 based on the following criteria:

        ### Criteria:
        - How well it addresses the issue described
        - Whether it is syntactically correct
        - Whether it likely fixes the bug described
        - Whether it avoids unintended side effects
        - Whether it follows clean coding practices

        ### Scoring:
        - 0.0: Patch does not address the issue at all
        - 0.2: Patch attempts to address the issue but has major flaws
        - 0.4: Patch partially addresses the issue but has significant flaws
        - 0.5: Patch addresses the issue but has significant flaws
        - 0.6: Patch addresses the issue but has minor flaws
        - 0.8: Patch addresses the issue well but has some minor issues
        - 0.9: Patch addresses the issue very well with only minor improvements needed
        - 1.0: Patch perfectly addresses the issue

        ## Context
        ### Issue Description:
        {self.issue}

        ### Patch:
        {self.full_code}

        Reply ONLY with a float value between 0 and 1. Do not include any other text.
        """
        try:
            if model_provider == "openai":
                response = openai_client.responses.create(
                    model="gpt-5",
                    input=prompt
                )
                score_text = response.output_text.strip()
            else:
                client = genai.Client()
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt
                )
                score_text = response.text.strip()

            # score_text = response.text.strip()
            score = float(re.findall(r"\d*\.?\d+", score_text)[0])
            return max(0.0, min(score, 1.0))
        except Exception as e:
            print(f"[LLM SCORING ERROR]: {e}")
            return 0.5

    def compute_total_score(self, weights: dict = None, model_provider="gemini") -> Tuple[float, dict]:
        if weights is None:
            weights = {
                'patch_size': 0.15,
                'syntax': 0.15,
                'style': 0.10,
                'exception': 0.10,
                'docstring': 0.10,
                'variable': 0.10,
                'pattern': 0.10,
                'llm': 0.20
            }

        scores = {
            'patch_size': self.score_patch_size(),
            'syntax': self.score_syntax_correctness(),
            'style': self.score_style_consistency(),
            'exception': self.score_exception_safety(),
            'docstring': self.score_docstring_penalty(),
            'variable': self.score_variable_reuse(),
            'pattern': self.score_pattern_match(),
            'llm': self.score_llm_semantic(model_provider=model_provider)
        }

        total = sum(scores[k] * weights.get(k, 0) for k in scores)
        return round(total, 4), scores

# Extract patches from a file
def extract_patches_from_txt(file_path: str) -> List[Tuple[str, str]]:
    with open(file_path, 'r') as f:
        content = f.read()

    pattern = r"#### Candidate Patch \(Full Function\)\n# Candidate Patch (\d+)[\s\S]*?# File: .*?\n\n(.*?)\n+#### Candidate Patch \(Unified Diff\)\n# Candidate Patch \1 \(Unified Diff\)\n\n(---.*?)\n(?=####|$)"
    matches = re.findall(pattern, content, re.DOTALL)

    patches = []
    for _, function_code, diff_code in matches:
        patches.append((function_code.strip(), diff_code.strip()))
    return patches

def extract_patches_from_string(content: str) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    """
    Extracts Step 1 metadata and Step 2 candidate patches from the given string.

    Args:
        content (str): The input text containing Step 1 and Step 2 sections.

    Returns:
        Tuple[Dict[str, str], List[Tuple[str, str]]]:
            - Step 1 dictionary with keys "File" and "Function" (if found).
            - List of tuples for Step 2, where each tuple = (full_function_code, unified_diff_code).
    """

    # Split at Step 2
    if "### Step 2:" not in content:
        print("[ERROR] '### Step 2:' not found in generated patch.")
        return {}, []
    step1_text, step2_text = content.split("### Step 2:", 1)

    # --- Process Step 1 ---
    # Extract relevant file and function name from Step 1
    step1_dict: Dict[str, str] = {}
    lines = step1_text.strip().split("\n")
    for line in lines:
        if "File:" in line:
            step1_dict["File"] = line.split("File:")[1].strip()
        elif "Function:" in line:
            step1_dict["Function"] = line.split("Function:")[1].strip()

    # --- Process Step 2 ---
    # Split into candidate patches
    pattern = r"(#### Candidate Patch \(Full Function\)[\s\S]*?)(?=#### Candidate Patch \(Full Function\)|$)"
    matches = re.findall(pattern, step2_text)
    print(f"[DEBUG] Matches found with regex: {len(matches)}")

    result_list: List[Tuple[str, str]] = []
    # for candidate_block in candidates[1:]:
    for candidate_block in matches:
        full_function_match = re.search(
            r"#### Candidate Patch \(Full Function\)(.*?)(?=#### Candidate Patch \(Unified Diff\))",
            candidate_block,
            re.DOTALL,
        )
        unified_diff_match = re.search(
            r"#### Candidate Patch \(Unified Diff\)(.*)", candidate_block, re.DOTALL
        )

        full_function_code = full_function_match.group(1).strip() if full_function_match else ""
        unified_diff_code = unified_diff_match.group(1).strip() if unified_diff_match else ""

        result_list.append((full_function_code, unified_diff_code))
        print(f"[DEBUG] Extracted candidate patch with function length {len(full_function_code)} and diff length {len(unified_diff_code)}.")
    
    print(f"[INFO] Extracted {len(result_list)} candidate patches from LLM output.")

    return step1_dict, result_list

def score_patches(patch_string:str, original_issue:str, model_provider:str="gemini"):
    # Extract patches from the string
    print("Scoring the generated patches...")
    file_func_name, all_patches = extract_patches_from_string(str(patch_string))
    file_name = file_func_name['File'] if 'File' in file_func_name else 'unknown_file.py'
    func_name = file_func_name['Function'] if 'Function' in file_func_name else 'unknown_function'
    
    # Debug logging
    print(f"[DEBUG] all_patches length in score_patches: {len(all_patches)}")
    if not all_patches:
        print("[WARNING] No candidate patches extracted from LLM output.")
        print(f"  File: {file_name}, Function: {func_name}")
        print(f"  Patch string (truncated to 400 chars):\n{patch_string[:400]}...\n")

    # Score each patch
    results = []
    # best_patch = None
    
    for i, (func, diff) in enumerate(all_patches):
        try:
            scorer = PatchScorer(func, diff, original_issue)
            total, breakdown = scorer.compute_total_score(model_provider=model_provider)

            results.append({
                "patch_id": i + 1,
                "total": total,
                "breakdown": breakdown,
                "func": func,
                # "diff": diff
            })
        except Exception as e:
            print(f"[ERROR SCORING PATCH {i+1}]: {e}")
            continue

    # debug logging
    print(f"[DEBUG] Scored {len(results)} patches.")

    # best patch
    best_patch = max(results, key=lambda x: x["total"], default=None) if results else None
    if best_patch:
        print(f"[INFO] Best patch selected with score {best_patch['total']:.3f}")
        # print(f"  File: {file_name}, Function: {func_name}, Patch ID: {best_patch['patch_id']}, Patch Score: {best_patch['total']:.3f}...")
    else:
        print("[INFO] No best patch could be selected.")
    return all_patches, file_name, func_name, results, best_patch


if __name__ == "__main__":
    # input_txt = "generated_patch.txt"  # update this to your file path
    input_txt = os.path.join(get_root_directory(), 'llm_response', 'generated_patch.txt')
    all_patches = extract_patches_from_txt(input_txt)

    print("\n===== PATCH SCORING RESULTS =====\n")
    for i, (func, diff) in enumerate(all_patches):
        scorer = PatchScorer(func, diff, original_issue)
        total, breakdown = scorer.compute_total_score()
        print(f"Patch {i+1}: Total Score = {total:.3f}")
        for k, v in breakdown.items():
            print(f"  {k:18}: {v:.2f}")
        print("-----------------------------")
