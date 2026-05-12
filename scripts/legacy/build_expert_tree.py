from __future__ import annotations

import argparse

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402
from dataset_rebuild_utils import RAW_PATH, load_records, save_json, symptom_id_for, fault_id_for
from rebuild_kg import build_primary_candidate_sets


def build_expert_tree(records):
    candidate_sets = build_primary_candidate_sets(records)
    symptoms = {}
    for index, record in enumerate(records, start=1):
        raw_symptoms = record.get("symptoms") or []
        if not raw_symptoms:
            continue
        fault_id = fault_id_for(index)
        primary_symptom_id = symptom_id_for(raw_symptoms[0])
        symptoms.setdefault(
            primary_symptom_id,
            {
                "symptom_id": primary_symptom_id,
                "type": "primary",
                "candidate_fault_ids": [],
                "deterministic": bool(record.get("deterministic")),
            },
        )
        for candidate_id in candidate_sets.get(fault_id, [fault_id]):
            if candidate_id not in symptoms[primary_symptom_id]["candidate_fault_ids"]:
                symptoms[primary_symptom_id]["candidate_fault_ids"].append(candidate_id)

    return {
        "meta": {
            "purpose": "Primary symptoms identify systems and candidate fault sets; only deterministic symptoms may directly diagnose.",
        },
        "primary_symptoms": symptoms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ambiguity-aware primary symptom expert tree.")
    parser.add_argument("--input", default=RAW_PATH)
    parser.add_argument("--output", default="data/staging/expert_tree.json")
    args = parser.parse_args()

    records = load_records(args.input)
    save_json(args.output, build_expert_tree(records))
    print(f"Built expert tree for {len(records)} records -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
