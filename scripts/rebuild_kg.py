from __future__ import annotations

import argparse
from datetime import datetime, timezone

import _bootstrap  # noqa: F401

from dataset_rebuild_utils import (
    ALIASES_PATH,
    CF_PATH,
    KG_PATH,
    PROCEDURE_PATH,
    RAW_PATH,
    extract_step_results,
    extract_step_text,
    fault_display_for,
    fault_id_for,
    fault_name_for,
    load_json,
    load_records,
    normalize_category,
    save_json,
    slugify,
    symptom_id_for,
)


def build_resolution(record, fault_id: str, fault_display: str):
    steps = []
    for raw_step in record.get("diagnosis_steps") or []:
        text = extract_step_text(raw_step)
        if text:
            steps.append(text)
        for result in extract_step_results(raw_step):
            steps.append(f"Possible result: {result}")

    procedure = ". ".join(steps) if steps else f"Inspect and repair {fault_display}."
    return {
        "parts": record.get("parts") or [fault_display],
        "tools": record.get("tools") or ["OBD scanner", "Multimeter"],
        "procedure": procedure,
        "difficulty": record.get("difficulty") or "intermediate",
        "labor_hours": record.get("labor_hours") or max(1, min(8, len(steps) or 1)),
        "repair_id": f"REP_{fault_id.split('_')[-1]}",
        "repair_name": f"diagnose_{fault_name_for(record)}",
        "steps": steps or [procedure],
    }


def build_aliases(records):
    aliases = {}
    for record in records:
        for symptom_text in record.get("symptoms", []):
            symptom_text = str(symptom_text).strip()
            if not symptom_text:
                continue
            symptom_id = symptom_id_for(symptom_text)
            aliases.setdefault(
                symptom_id,
                {
                    "name": slugify(symptom_text),
                    "display_name": symptom_text,
                    "label_vi": symptom_text,
                    "aliases": [symptom_text],
                },
            )
    return dict(sorted(aliases.items()))


def build_primary_candidate_sets(records):
    category_faults = {}
    symptom_faults = {}
    record_fault_ids = []

    for index, record in enumerate(records, start=1):
        fault_id = fault_id_for(index)
        record_fault_ids.append(fault_id)
        category = str(record.get("category") or "").strip().lower()
        if category:
            category_faults.setdefault(category, []).append(fault_id)
        for symptom_text in record.get("symptoms", []):
            symptom_faults.setdefault(symptom_id_for(symptom_text), []).append(fault_id)

    candidate_sets = {}
    for index, record in enumerate(records, start=1):
        symptoms = record.get("symptoms") or []
        if not symptoms:
            continue
        fault_id = fault_id_for(index)
        primary_symptom = symptom_id_for(symptoms[0])
        category = str(record.get("category") or "").strip().lower()
        candidates = list(dict.fromkeys(
            (symptom_faults.get(primary_symptom) or [])
            + (category_faults.get(category) or [])
            + [fault_id]
        ))
        candidate_sets[fault_id] = candidates
    return candidate_sets


def rebuild(records, cf_data, procedure_trees):
    cf_map = cf_data.get("symptoms", cf_data) if isinstance(cf_data, dict) else {}
    candidate_sets = build_primary_candidate_sets(records)
    rules = []

    for index, record in enumerate(records, start=1):
        fault_name = fault_name_for(record)
        if not fault_name:
            continue
        fault_id = fault_id_for(index)
        display = fault_display_for(record)
        ontology = normalize_category(record.get("category", ""))
        symptom_refs = []

        for priority, symptom_text in enumerate(record.get("symptoms", []), start=1):
            symptom_id = symptom_id_for(symptom_text)
            cf = float(cf_map.get(symptom_id, {}).get(fault_id, 0.5))
            symptom_refs.append(
                {
                    "symptom_id": symptom_id,
                    "cf": round(cf, 4),
                    "priority": priority,
                }
            )

        if not symptom_refs:
            continue

        resolution = build_resolution(record, fault_id, display)
        procedure = procedure_trees.get(fault_id) or {
            "entry_step": None,
            "steps": {},
        }

        rule = {
            "fault_id": fault_id,
            "fault_name": fault_name,
            "fault": fault_name,
            "display_name": display,
            "label_vi": display,
            "system": ontology["system_id"],
            "system_id": ontology["system_id"],
            "subsystem": ontology["subsystem_id"],
            "subsystem_id": ontology["subsystem_id"],
            "affected_components": ontology["affected_components"],
            "symptom": symptom_refs[0]["symptom_id"],
            "primary_symptom": symptom_refs[0]["symptom_id"],
            "candidate_fault_ids": candidate_sets.get(fault_id, [fault_id]),
            "cf": symptom_refs[0]["cf"],
            "symptoms": symptom_refs,
            "procedure": {
                "entry_step": procedure.get("entry_step"),
                "steps": procedure.get("steps", {}),
            },
            "resolution": {
                "parts": resolution["parts"],
                "tools": resolution["tools"],
                "procedure": resolution["procedure"],
                "difficulty": resolution["difficulty"],
                "labor_hours": resolution["labor_hours"],
            },
            "repairs": [
                {
                    "repair_id": resolution["repair_id"],
                    "repair_name": resolution["repair_name"],
                    "display_name": f"Diagnosis for {display}",
                    "label_vi": f"Diagnosis for {display}",
                    "steps": resolution["steps"],
                }
            ],
            "status": "approved",
        }
        rules.append(rule)

    return {
        "meta": {
            "version": "3.0",
            "domain": "car_diagnostic",
            "source": "automotive_faults_dataset",
            "total_rules": len(rules),
            "graph_type": "ontology_driven",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild KG rules from dynamic CF and procedure trees.")
    parser.add_argument("--input", default=RAW_PATH)
    parser.add_argument("--cf", default=CF_PATH)
    parser.add_argument("--procedures", default=PROCEDURE_PATH)
    parser.add_argument("--output", default=KG_PATH)
    parser.add_argument("--symptom-aliases", default=ALIASES_PATH)
    args = parser.parse_args()

    records = load_records(args.input)
    cf_data = load_json(args.cf)
    procedures = load_json(args.procedures)
    save_json(args.output, rebuild(records, cf_data, procedures))
    save_json(args.symptom_aliases, build_aliases(records))
    print(f"Rebuilt KG rules for {len(records)} records -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
