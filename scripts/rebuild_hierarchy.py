from __future__ import annotations

import json
from pathlib import Path

try:
    from _bootstrap import PROJECT_ROOT  # type: ignore
except ModuleNotFoundError:
    from scripts._bootstrap import PROJECT_ROOT  # type: ignore
from src.expert_system.hierarchy import build_hierarchy
from src.expert_system.knowledge_base import extract_rules, load_json

STAGING = PROJECT_ROOT / "data" / "staging"
OUTPUT = STAGING / "expert_tree.json"


def main() -> None:
    hierarchy = build_hierarchy(
        ontology=load_json(STAGING / "ontology.json"),
        symptom_aliases=load_json(STAGING / "symptom_aliases.json"),
        rules=extract_rules(load_json(STAGING / "kg_rules_from_dataset.json")),
        procedure_trees=load_json(STAGING / "procedure_trees.json"),
    )
    OUTPUT.write_text(json.dumps(hierarchy, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
