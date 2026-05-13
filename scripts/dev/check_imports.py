"""
check_imports — Verify that old import paths still work through compatibility wrappers.

Run from project root:
    python scripts/dev/check_imports.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_import(module_path: str, names: list[str]) -> bool:
    """Try importing specific names from a module path."""
    try:
        mod = __import__(module_path, fromlist=names)
        for name in names:
            obj = getattr(mod, name, None)
            if obj is None:
                print(f"  FAIL: {module_path}.{name} is None")
                return False
        print(f"  OK:   from {module_path} import {', '.join(names)}")
        return True
    except Exception as exc:
        print(f"  FAIL: from {module_path} import {', '.join(names)} -> {exc}")
        return False


def main() -> int:
    print("Checking compatibility imports...\n")
    all_ok = True

    # --- Old top-level paths (used by backend and tests) ---
    checks = [
        ("src.expert_system.engine", ["ExpertSystemEngine", "WorkingMemory", "load_cf_map", "rank_faults"]),
        ("src.expert_system.matcher", ["SymptomMatcher"]),
        ("src.expert_system.knowledge_base", ["KnowledgeBase", "load_json", "extract_rules"]),
        ("src.expert_system.procedure", ["ProcedureRunner", "ProcedureReasoner", "get_next_from_tree"]),
        ("src.expert_system.policy", ["apply_response_policy"]),
        ("src.expert_system.schemas", ["DiagnosisResponse", "ExpertSystemValidator", "ValidationReport"]),
        ("src.expert_system.llm_fallback", ["diagnose_with_llm"]),
    ]

    # --- New modular paths ---
    new_checks = [
        ("src.expert_system.inference.engine", ["ExpertSystemEngine", "InferenceEngine"]),
        ("src.expert_system.inference.fuzzy", ["SymptomMatcher"]),
        ("src.expert_system.inference.certainty", ["rank_faults", "load_cf_map"]),
        ("src.expert_system.inference.question", ["select_by_information_gain"]),
        ("src.expert_system.inference.procedure", ["ProcedureRunner"]),
        ("src.expert_system.inference.policy", ["apply_response_policy"]),
        ("src.expert_system.knowledge.loader", ["KnowledgeBase", "load_json", "extract_rules"]),
        ("src.expert_system.knowledge.schema", ["ExpertSystemValidator", "ValidationReport"]),
        ("src.expert_system.runtime.state", ["WorkingMemory"]),
        ("src.expert_system.runtime.result", ["DiagnosisResponse", "DiagnosisCandidate"]),
        ("src.expert_system.runtime.trace", ["ExplanationBuilder"]),
        ("src.expert_system.utils.text", ["slugify"]),
        ("src.expert_system.utils.scoring", ["combine_cf", "confidence_label"]),
    ]

    # --- Package-level imports ---
    package_checks = [
        ("src.expert_system", ["ExpertSystemEngine", "KnowledgeBase", "WorkingMemory", "SymptomMatcher", "ProcedureRunner", "apply_response_policy"]),
    ]

    print("=== Old (compatibility) import paths ===")
    for module_path, names in checks:
        if not check_import(module_path, names):
            all_ok = False

    print("\n=== New modular import paths ===")
    for module_path, names in new_checks:
        if not check_import(module_path, names):
            all_ok = False

    print("\n=== Package-level imports ===")
    for module_path, names in package_checks:
        if not check_import(module_path, names):
            all_ok = False

    print()
    if all_ok:
        print("ALL IMPORT CHECKS PASSED")
        return 0
    else:
        print("SOME IMPORT CHECKS FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
