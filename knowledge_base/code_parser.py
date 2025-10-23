import os
from tqdm import tqdm
from tree_sitter import Parser, Language
import tree_sitter_python as tspython
import git

PYTHON_LANGUAGE = Language(tspython.language())
parser = Parser(PYTHON_LANGUAGE)

def get_node_text(code_bytes, node):
    return code_bytes[node.start_byte:node.end_byte].decode('utf-8')

def extract_symbols_from_code(code: str):
    code_bytes = code.encode("utf8")
    tree = parser.parse(code_bytes)
    root_node = tree.root_node

    file_symbols = {
        "functions": [],
        "classes": [],
        "imports": [],
        "calls": {},
        "aliases": {},  # alias → module
    }

    current_class = None

    def get_node_text(node):
        return code_bytes[node.start_byte:node.end_byte].decode('utf-8')

    def get_node_text_safe(node):
        return get_node_text(node) if node else None

    def find_calls(node, call_list, current_class=None):
        if node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                func_text = get_node_text(func_node)
                if func_text.startswith("self.") and current_class:
                    method_name = func_text.split(".", 1)[1]
                    func_text = f"{current_class}.{method_name}"
                call_list.append(func_text)
        for child in node.children:
            find_calls(child, call_list, current_class=current_class)

    def traverse(node):
        nonlocal current_class

        if node.type == "import_statement":
            for child in node.named_children:
                if child.type == "aliased_import":
                    mod = get_node_text_safe(child.child_by_field_name("name"))
                    alias = get_node_text_safe(child.child_by_field_name("alias"))
                    file_symbols["aliases"][alias] = mod
                    file_symbols["imports"].append(mod)
                elif child.type == "dotted_name":
                    file_symbols["imports"].append(get_node_text_safe(child))

        elif node.type == "import_from_statement":
            module_node = node.child_by_field_name("module")
            alias_node = node.child_by_field_name("alias")
            if module_node:
                mod = get_node_text_safe(module_node)
                file_symbols["imports"].append(mod)
                if alias_node:
                    file_symbols["aliases"][get_node_text_safe(alias_node)] = mod

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            class_name = get_node_text_safe(name_node)
            current_class = class_name
            bases = []
            attrs = []

            for child in node.named_children:
                if child.type == "argument_list":
                    for arg in child.named_children:
                        if arg.type in {"identifier", "dotted_name"}:
                            bases.append(get_node_text_safe(arg))
                if child.type == "expression_statement" and child.children:
                    assignment = child.children[0]
                    if assignment.type == "assignment":
                        left = assignment.child_by_field_name("left")
                        if left:
                            attr_name = get_node_text_safe(left)
                            attrs.append(attr_name)

            file_symbols["classes"].append({
                "name": class_name,
                "lineno": node.start_point[0] + 1,
                "col_offset": node.start_point[1],
                "end_lineno": node.end_point[0] + 1,
                "end_col_offset": node.end_point[1],
                "code_snippet": get_node_text_safe(node),
                "bases": bases,
                "attributes": attrs,
            })

        elif node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            func_name = get_node_text_safe(name_node)
            qualified_name = f"{current_class}.{func_name}" if current_class else func_name

            is_static = False
            for dec in node.children:
                if dec.type == "decorator":
                    dec_text = get_node_text_safe(dec)
                    if "staticmethod" in dec_text:
                        is_static = True

            call_list = []
            find_calls(node, call_list, current_class)

            file_symbols["functions"].append({
                "name": qualified_name,
                "lineno": node.start_point[0] + 1,
                "col_offset": node.start_point[1],
                "end_lineno": node.end_point[0] + 1,
                "end_col_offset": node.end_point[1],
                "code_snippet": get_node_text_safe(node),
                "is_static": is_static,
            })

            file_symbols["calls"][qualified_name] = call_list

        for child in node.children:
            traverse(child)

        if node.type == "class_definition":
            current_class = None

    traverse(root_node)
    return file_symbols


def get_repo_structure_at_commit(repo_path: str, commit_hash: str, extension_filter=".py"):
    repo = git.Repo(repo_path)
    file_contents = []

    try:
        commit = repo.commit(commit_hash)
        tree = commit.tree

        def walk_tree(tree_obj, prefix=""):
            for item in tree_obj:
                current_path = os.path.join(prefix, item.name)
                if item.type == "tree":
                    walk_tree(item, prefix=current_path)
                elif item.type == "blob":
                    if extension_filter is None or item.name.endswith(extension_filter):
                        try:
                            content = item.data_stream.read().decode('utf-8', errors='replace')
                            file_contents.append((os.path.normpath(current_path), content, item.hexsha))
                        except Exception as e:
                            print(f"Error decoding {current_path}: {e}")

        walk_tree(tree)
        return file_contents

    except Exception as e:
        print(f"Error retrieving structure at commit {commit_hash}: {e}")
        return []



def detect_design_patterns(filepath: str, code_symbols: dict) -> list:
    patterns = []

    # --- Singleton ---
    for cls in code_symbols.get("classes", []):
        cls_code = cls.get("code_snippet", "")
        if "__new__" in cls_code and "cls._instance" in cls_code:
            patterns.append({
                "pattern": "Singleton",
                "class": cls["name"],
                "role": "Singleton"
            })
    
    return patterns



def build_code_symbol_graph_data(repo_path: str, commit_hash: str = None):
    code_graph_data = {}
    symbol_table = {}

    # for design patterns detection
    all_patterns = {}
    #####################################


    python_files = get_repo_structure_at_commit(repo_path, commit_hash) if commit_hash else []

    print(f"Parsing {len(python_files)} Python files using Tree-sitter...")
    for relative_filepath, file_content, _ in tqdm(python_files, desc="Parsing Python Files"):
        try:
            symbols = extract_symbols_from_code(file_content)

            # for design patterns detection ######
            patterns = detect_design_patterns(relative_filepath, symbols)
            # if patterns:
            all_patterns[relative_filepath] = patterns
            #####################################

            code_graph_data[relative_filepath] = symbols

            for func in symbols.get("functions", []):
                symbol_table[func['name']] = f"{relative_filepath}::{func['name']}"
            for cls in symbols.get("classes", []):
                symbol_table[cls['name']] = f"{relative_filepath}::{cls['name']}"
        except Exception as e:
            print(f"Error parsing {relative_filepath}: {e}")
    return code_graph_data, symbol_table , all_patterns



