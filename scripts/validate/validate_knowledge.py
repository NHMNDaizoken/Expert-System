from __future__ import annotations

import argparse
from pathlib import Path

try:
    import _bootstrap  # type: ignore # noqa: F401
except ModuleNotFoundError:
    from scripts import _bootstrap  # type: ignore # noqa: F401

from src.expert_system.knowledge.loader import KnowledgeBase
from src.expert_system.knowledge.schema import ExpertSystemValidator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_PATH = PROJECT_ROOT / "data" / "staging" / "ontology.json"
SYMPTOM_ALIASES_PATH = PROJECT_ROOT / "data" / "staging" / "symptom_aliases.json"
RULES_PATH = PROJECT_ROOT / "data" / "staging" / "kg_rules_from_dataset.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate knowledge artifacts.")
    parser.add_argument("--ontology", type=Path, default=ONTOLOGY_PATH)
    parser.add_argument("--symptom-aliases", type=Path, default=SYMPTOM_ALIASES_PATH)
    parser.add_argument("--rules", type=Path, default=RULES_PATH)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        report = ExpertSystemValidator(KnowledgeBase.from_staging()).validate()
        if not report.ok:
            print("Validation failed")
            for error in report.errors:
                print(f"- {error}")
            return 1
    except Exception as error:
        print("Validation failed")
        print(f"- {error}")
        return 1

    print("Validation passed: 0 errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
