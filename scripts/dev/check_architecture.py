import os
import sys
import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def check_no_legacy_imports():
    errors = []
    src_dir = PROJECT_ROOT / "src" / "expert_system"
    legacy_modules = [
        "src.expert_system.engine",
        "src.expert_system.matcher",
        "src.expert_system.procedure",
        "src.expert_system.policy",
        "src.expert_system.knowledge_base",
        "src.expert_system.schemas",
        "src.expert_system.hierarchy",
    ]
    for root, dirs, files in os.walk(src_dir):
        if "expert_system" in Path(root).parts and Path(root).name in ["inference", "runtime", "knowledge"]:
            for f in files:
                if f.endswith(".py"):
                    filepath = Path(root) / f
                    with open(filepath, "r", encoding="utf-8") as file:
                        try:
                            tree = ast.parse(file.read(), filename=filepath)
                            for node in ast.walk(tree):
                                if isinstance(node, ast.Import):
                                    for alias in node.names:
                                        if any(alias.name == lm for lm in legacy_modules):
                                            errors.append(f"{filepath}: Imports legacy wrapper {alias.name}")
                                elif isinstance(node, ast.ImportFrom):
                                    if node.module and any(node.module == lm for lm in legacy_modules):
                                        errors.append(f"{filepath}: Imports legacy wrapper {node.module}")
                        except Exception as e:
                            errors.append(f"Failed to parse {filepath}: {e}")
    return errors

def check_backend_imports():
    errors = []
    backend_dir = PROJECT_ROOT / "backend"
    inference_internals = [
        "src.expert_system.inference.fuzzy",
        "src.expert_system.inference.procedure",
        "src.expert_system.inference.certainty",
        "src.expert_system.inference.question",
        "src.expert_system.inference.policy",
    ]
    for root, dirs, files in os.walk(backend_dir):
        for f in files:
            if f.endswith(".py"):
                filepath = Path(root) / f
                with open(filepath, "r", encoding="utf-8") as file:
                    try:
                        tree = ast.parse(file.read(), filename=filepath)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    if any(alias.name.startswith(inf) for inf in inference_internals):
                                        errors.append(f"{filepath}: Imports inference internal {alias.name}")
                            elif isinstance(node, ast.ImportFrom):
                                if node.module and any(node.module.startswith(inf) for inf in inference_internals):
                                    errors.append(f"{filepath}: Imports inference internal {node.module}")
                    except Exception as e:
                        errors.append(f"Failed to parse {filepath}: {e}")
    return errors

def main():
    errors = []
    print("Checking legacy imports in runtime code...")
    legacy_errs = check_no_legacy_imports()
    if legacy_errs:
        errors.extend(legacy_errs)
    else:
        print("OK: No legacy imports found in runtime code.")

    print("Checking backend imports for inference internals...")
    backend_errs = check_backend_imports()
    if backend_errs:
        errors.extend(backend_errs)
    else:
        print("OK: No inference internals imported from backend.")
        
    if errors:
        print("\nARCHITECTURE VIOLATIONS FOUND:")
        for err in errors:
            print(f" - {err}")
        sys.exit(1)
    
    print("\nAll architecture boundary checks passed.")

if __name__ == "__main__":
    main()
