from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "automotive_faults.json"
STAGING_DIR = PROJECT_ROOT / "data" / "staging"
CF_PATH = STAGING_DIR / "cf_dynamic.json"
PROCEDURE_PATH = STAGING_DIR / "procedure_trees.json"
EXPERT_TREE_PATH = STAGING_DIR / "expert_tree.json"
KG_PATH = STAGING_DIR / "kg_rules_from_dataset.json"
ALIASES_PATH = STAGING_DIR / "symptom_aliases.json"


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def load_records(path: str | Path = RAW_PATH) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    data = load_json(path)
    if isinstance(data, list):
        return [record for record in data if isinstance(record, dict)]
    if isinstance(data, dict):
        for key in ("records", "faults", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [record for record in value if isinstance(record, dict)]
    return []


def slugify(text: Any) -> str:
    text = str(text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def make_id(prefix: str, text: Any) -> str:
    return f"{prefix}_{slugify(text).upper()}"


def fault_id_for(index: int) -> str:
    return f"FLT_{index:03d}"


def symptom_id_for(symptom_text: str) -> str:
    return make_id("SYM", symptom_text)


def fault_name_for(record: dict[str, Any]) -> str:
    return slugify(record.get("subcategory") or record.get("fault") or record.get("name"))


def fault_display_for(record: dict[str, Any]) -> str:
    return str(record.get("subcategory") or record.get("fault") or record.get("name") or "Unknown Fault")


def extract_step_text(step: Any) -> str:
    if isinstance(step, str):
        return step.strip()
    if isinstance(step, dict):
        return str(step.get("step") or step.get("question") or step.get("instruction") or "").strip()
    return str(step or "").strip()


def extract_step_results(step: Any) -> list[str]:
    if isinstance(step, dict):
        result = step.get("result") or step.get("results") or []
        if isinstance(result, list):
            return [str(item) for item in result if str(item).strip()]
        if result:
            return [str(result)]
    return []


def normalise_category(category: str) -> tuple[str, str, list[str]]:
    text = str(category or "").lower()
    mapping = [
        ("brake", ("SYS_BRAKE", "SUB_FRICTION_BRAKE", ["CMP_BRAKE_PAD"])),
        ("abs", ("SYS_BRAKE", "SUB_ABS", ["CMP_ABS_CONTROL_MODULE"])),
        ("engine", ("SYS_ENGINE", "SUB_ENGINE_MECHANICAL", ["CMP_ENGINE_MOUNT"])),
        ("cool", ("SYS_COOLING", "SUB_COOLANT_CIRCUIT", ["CMP_RADIATOR"])),
        ("fuel", ("SYS_FUEL", "SUB_FUEL_DELIVERY", ["CMP_FUEL_PUMP"])),
        ("trans", ("SYS_TRANSMISSION", "SUB_AUTOMATIC_TRANSMISSION", ["CMP_TRANSMISSION"])),
        ("clutch", ("SYS_TRANSMISSION", "SUB_CLUTCH", ["CMP_CLUTCH_CABLE"])),
        ("suspension", ("SYS_SUSPENSION_STEERING", "SUB_SUSPENSION", ["CMP_SHOCK_ABSORBER"])),
        ("steering", ("SYS_SUSPENSION_STEERING", "SUB_STEERING", ["CMP_STEERING_RACK"])),
        ("hvac", ("SYS_HVAC", "SUB_BLOWER_VENT", ["CMP_BLOWER_MOTOR"])),
        ("air conditioning", ("SYS_HVAC", "SUB_AC_REFRIGERATION", ["CMP_AC_COMPRESSOR"])),
        ("exhaust", ("SYS_EXHAUST_EMISSION", "SUB_EXHAUST", ["CMP_MUFFLER"])),
        ("emission", ("SYS_EXHAUST_EMISSION", "SUB_EXHAUST", ["CMP_OXYGEN_SENSOR"])),
        ("electrical", ("SYS_ELECTRICAL", "SUB_STARTING", ["CMP_STARTER_MOTOR"])),
        ("battery", ("SYS_ELECTRICAL", "SUB_CHARGING", ["CMP_BATTERY"])),
        ("lighting", ("SYS_ELECTRICAL", "SUB_LIGHTING", ["CMP_HEADLAMP_BULB"])),
        ("body", ("SYS_ELECTRICAL", "SUB_BODY_ELECTRICAL", ["CMP_DOOR_LOCK_ACTUATOR"])),
    ]
    for keyword, value in mapping:
        if keyword in text:
            return value
    return "SYS_ELECTRICAL", "SUB_STARTING", ["CMP_STARTER_MOTOR"]


def compute_cf(records: list[dict[str, Any]]) -> dict[str, Any]:
    symptom_counts: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    faults: set[str] = set()

    for index, record in enumerate(records, start=1):
        fid = record.get("fault_id") or fault_id_for(index)
        faults.add(fid)
        for raw_symptom in record.get("symptoms", []):
            sid = symptom_id_for(raw_symptom)
            symptom_counts[sid] += 1
            pair_counts[(sid, fid)] += 1

    symptoms: dict[str, dict[str, float]] = defaultdict(dict)
    for (sid, fid), count in sorted(pair_counts.items()):
        cf = count / symptom_counts[sid]
        symptoms[sid][fid] = round(cf, 4)

    return {
        "_meta": {
            "total_records": len(records),
            "total_symptoms": len(symptom_counts),
            "total_faults": len(faults),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "low_cf_threshold": 0.15,
        },
        "symptoms": dict(symptoms),
    }


def build_aliases(records: list[dict[str, Any]]) -> dict[str, Any]:
    aliases: dict[str, dict[str, Any]] = {}
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


def build_primary_candidate_sets(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    category_faults: dict[str, list[str]] = {}
    symptom_faults: dict[str, list[str]] = {}

    for index, record in enumerate(records, start=1):
        fault_id = fault_id_for(index)
        category = str(record.get("category") or "").strip().lower()
        if category:
            category_faults.setdefault(category, []).append(fault_id)
        for symptom_text in record.get("symptoms", []):
            symptom_faults.setdefault(symptom_id_for(symptom_text), []).append(fault_id)

    candidate_sets: dict[str, list[str]] = {}
    for index, record in enumerate(records, start=1):
        symptoms = record.get("symptoms") or []
        if not symptoms:
            continue
        fault_id = fault_id_for(index)
        primary_symptom = symptom_id_for(symptoms[0])
        category = str(record.get("category") or "").strip().lower()
        candidates = list(
            dict.fromkeys(
                (symptom_faults.get(primary_symptom) or [])
                + (category_faults.get(category) or [])
                + [fault_id]
            )
        )
        candidate_sets[fault_id] = candidates
    return candidate_sets


def build_resolution(record: dict[str, Any], fault_id: str, fault_display: str) -> dict[str, Any]:
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


def build_procedure_trees(records: list[dict[str, Any]]) -> dict[str, Any]:
    trees = {}
    for index, record in enumerate(records, start=1):
        fault_id = fault_id_for(index)
        if not fault_name_for(record):
            continue
        raw_steps = record.get("diagnosis_steps") or []
        steps = {}
        step_ids = []

        for step_index, raw_step in enumerate(raw_steps, start=1):
            text = extract_step_text(raw_step)
            if not text:
                continue
            step_id = f"{fault_id.lower()}_s{step_index}"
            step_ids.append(step_id)
            results = extract_step_results(raw_step)
            instruction = text
            if results:
                instruction = f"{text}. Expected findings: {', '.join(results)}"

            is_question = "?" in text or any(keyword in text.lower() for keyword in ("check", "test", "verify", "inspect", "measure", "does", "is there", "if"))
            steps[step_id] = {
                "id": step_id,
                "question": text if text.endswith("?") else f"{text}?",
                "is_question": is_question,
                "yes_next": None,
                "no_next": "REFUTED",
                "instruction": None if is_question else instruction,
                "results": results,
            }

        if not steps:
            fallback_id = f"{fault_id.lower()}_s1"
            step_ids.append(fallback_id)
            steps[fallback_id] = {
                "id": fallback_id,
                "question": f"Verify symptoms for {fault_display_for(record)}?",
                "is_question": True,
                "yes_next": "DIAGNOSED",
                "no_next": "REFUTED",
                "instruction": None,
                "results": [],
            }

        for index, step_id in enumerate(step_ids):
            steps[step_id]["yes_next"] = step_ids[index + 1] if index + 1 < len(step_ids) else "DIAGNOSED"

        trees[fault_id] = {
            "fault_id": fault_id,
            "fault_name": fault_display_for(record),
            "entry_step": step_ids[0],
            "steps": steps,
        }
    return trees


def build_expert_tree(records: list[dict[str, Any]], rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rules = rules or []
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

    if rules:
        for rule in rules:
            primary_symptom_id = (rule.get("symptoms") or [{}])[0].get("symptom_id")
            if not primary_symptom_id:
                continue
            symptoms.setdefault(
                primary_symptom_id,
                {
                    "symptom_id": primary_symptom_id,
                    "type": "primary",
                    "candidate_fault_ids": [],
                    "deterministic": False,
                },
            )
            fault_id = rule.get("fault_id")
            if fault_id and fault_id not in symptoms[primary_symptom_id]["candidate_fault_ids"]:
                symptoms[primary_symptom_id]["candidate_fault_ids"].append(fault_id)

    return {
        "meta": {
            "purpose": "Primary symptoms identify systems and candidate fault sets; only deterministic symptoms may directly diagnose.",
        },
        "primary_symptoms": symptoms,
    }


def build_rules(records: list[dict[str, Any]], cf_data: dict[str, Any] | None = None, procedure_trees: dict[str, Any] | None = None) -> dict[str, Any]:
    cf_map = cf_data.get("symptoms", cf_data) if isinstance(cf_data, dict) else {}
    candidate_sets = build_primary_candidate_sets(records)
    rules = []

    for index, record in enumerate(records, start=1):
        fault_name = fault_name_for(record)
        if not fault_name:
            continue
        fault_id = fault_id_for(index)
        display = fault_display_for(record)
        system_id, subsystem_id, affected_components = normalise_category(record.get("category", ""))
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
        procedure = (procedure_trees or {}).get(fault_id) or {
            "entry_step": None,
            "steps": {},
        }

        rule = {
            "fault_id": fault_id,
            "fault_name": fault_name,
            "fault": fault_name,
            "display_name": display,
            "label_vi": display,
            "system": system_id,
            "system_id": system_id,
            "subsystem": subsystem_id,
            "subsystem_id": subsystem_id,
            "affected_components": affected_components,
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


def load_existing_artifact(path: Path) -> Any | None:
    return load_json(path) if path.exists() else None


def build_knowledge(rebuild_from_raw: bool = False) -> dict[str, Path]:
    records = load_records(RAW_PATH)

    if rebuild_from_raw and records:
        cf_data = compute_cf(records)
        procedure_trees = build_procedure_trees(records)
        expert_tree = build_expert_tree(records)
        rules = build_rules(records, cf_data, procedure_trees)
        aliases = build_aliases(records)
    else:
        cf_data = load_existing_artifact(CF_PATH) or compute_cf(records)
        procedure_trees = load_existing_artifact(PROCEDURE_PATH) or build_procedure_trees(records)
        expert_tree = load_existing_artifact(EXPERT_TREE_PATH) or build_expert_tree(records)
        aliases = load_existing_artifact(ALIASES_PATH) or build_aliases(records)
        rules = load_existing_artifact(KG_PATH) or build_rules(records, cf_data, procedure_trees)

    save_json(CF_PATH, cf_data)
    save_json(PROCEDURE_PATH, procedure_trees)
    save_json(EXPERT_TREE_PATH, expert_tree)
    save_json(ALIASES_PATH, aliases)
    save_json(KG_PATH, rules)

    return {
        "cf": CF_PATH,
        "procedures": PROCEDURE_PATH,
        "expert_tree": EXPERT_TREE_PATH,
        "aliases": ALIASES_PATH,
        "rules": KG_PATH,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build expert-system knowledge artifacts.")
    parser.add_argument(
        "--rebuild-from-raw",
        action="store_true",
        help="Recompute staging artifacts from data/raw instead of preserving current staging outputs.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    artifacts = build_knowledge(rebuild_from_raw=args.rebuild_from_raw)
    print("Built knowledge artifacts:")
    for label, path in artifacts.items():
        print(f"- {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
