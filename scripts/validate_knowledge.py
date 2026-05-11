from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401

from src.legacy.kg_validator import KGValidationError, validate_all


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
        validate_all(str(args.ontology), str(args.symptom_aliases), str(args.rules))
    except KGValidationError as error:
        print("Validation failed")
        print(f"- {error}")
        return 1

    print("Validation passed: 0 errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
