from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAGING_DIR = PROJECT_ROOT / "data" / "staging"
ALIASES_PATH = STAGING_DIR / "symptom_aliases.json"
RULES_PATH = STAGING_DIR / "kg_rules_from_dataset.json"
PROCEDURES_PATH = STAGING_DIR / "procedure_trees.json"


SYSTEM_DEFAULTS = {
    "brake": ("SYS_BRAKE", "SUB_FRICTION_BRAKE", ["CMP_BRAKE_PAD"]),
    "cool": ("SYS_COOLING", "SUB_COOLANT_CIRCUIT", ["CMP_RADIATOR"]),
    "engine": ("SYS_ENGINE", "SUB_ENGINE_MECHANICAL", ["CMP_ENGINE_MOUNT"]),
    "fuel": ("SYS_FUEL", "SUB_FUEL_DELIVERY", ["CMP_FUEL_PUMP"]),
    "trans": ("SYS_TRANSMISSION", "SUB_AUTOMATIC_TRANSMISSION", ["CMP_TRANSMISSION"]),
    "hvac": ("SYS_HVAC", "SUB_BLOWER_VENT", ["CMP_BLOWER_MOTOR"]),
    "electrical": ("SYS_ELECTRICAL", "SUB_STARTING", ["CMP_STARTER_MOTOR"]),
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp_file:
        temp_path = Path(temp_file.name)
        json.dump(data, temp_file, indent=2, ensure_ascii=False)
        temp_file.write("\n")
    os.replace(temp_path, path)


def _write_json_files_atomic(files: dict[Path, Any]) -> None:
    temp_paths: list[tuple[Path, Path]] = []
    try:
        for path, data in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(data, temp_file, indent=2, ensure_ascii=False)
                temp_file.write("\n")
            temp_paths.append((temp_path, path))

        for temp_path, path in temp_paths:
            os.replace(temp_path, path)
    finally:
        for temp_path, _ in temp_paths:
            if temp_path.exists():
                temp_path.unlink()


def _slug(text: Any) -> str:
    value = str(text or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "llm_item"


def _clamp_cf(value: Any, default: float = 0.35) -> float:
    try:
        cf = float(value)
    except (TypeError, ValueError):
        cf = default
    return round(max(0.0, min(cf, 0.65)), 4)


def _normalise_system(system: Any, system_id: Any = None) -> tuple[str, str, list[str]]:
    candidate = str(system_id or system or "").strip()
    if candidate.startswith("SYS_"):
        for default_system, subsystem, components in SYSTEM_DEFAULTS.values():
            if default_system == candidate:
                return default_system, subsystem, components
        return candidate, "SUB_STARTING", ["CMP_STARTER_MOTOR"]

    lowered = candidate.lower()
    for keyword, defaults in SYSTEM_DEFAULTS.items():
        if keyword in lowered:
            return defaults
    return SYSTEM_DEFAULTS["engine"]


def _merge_unique(existing: list[Any], additions: list[Any]) -> list[Any]:
    result = [item for item in existing if str(item).strip()]
    seen = {str(item) for item in result}
    for item in additions:
        if str(item).strip() and str(item) not in seen:
            result.append(item)
            seen.add(str(item))
    return result


def _repair_steps(diagnosis: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    for repair in diagnosis.get("repairs", []):
        if isinstance(repair, str):
            text = repair.strip()
            if text:
                steps.append(text)
            continue
        if not isinstance(repair, dict):
            continue
        for step in repair.get("steps", []):
            text = str(step).strip()
            if text:
                steps.append(text)
    return steps


def _procedure_for(fault_id: str, diagnosis: dict[str, Any], questions: list[Any]) -> dict[str, Any] | None:
    step_items = [_question_text(item) for item in questions]
    step_items = [item for item in step_items if item]
    if not step_items:
        return None

    steps: dict[str, dict[str, Any]] = {}
    base = _slug(fault_id)
    for index, text in enumerate(step_items, start=1):
        step_id = f"{base}_llm_s{index}"
        next_step = f"{base}_llm_s{index + 1}" if index < len(step_items) else "DIAGNOSED"
        steps[step_id] = {
            "id": step_id,
            "question": text,
            "is_question": True,
            "yes_next": next_step,
            "no_next": "REFUTED",
            "instruction": None,
            "results": [],
        }
    return {"fault_id": fault_id, "fault_name": diagnosis.get("fault_name", fault_id), "entry_step": f"{base}_llm_s1", "steps": steps}


def _question_text(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("question", "text", "label", "label_vi", "display_name"):
            if str(item.get(key) or "").strip():
                return str(item.get(key)).strip()
        return ""
    return str(item or "").strip()


def _diagnoses_from_payload(approved_payload: dict[str, Any]) -> list[dict[str, Any]]:
    source = approved_payload.get("llm_output") if isinstance(approved_payload.get("llm_output"), dict) else approved_payload
    diagnoses = source.get("diagnoses") or source.get("results") or source.get("current_hypotheses") or []
    return [diagnosis for diagnosis in diagnoses if isinstance(diagnosis, dict)]


def _primary_symptom_id(approved_payload: dict[str, Any], diagnosis: dict[str, Any]) -> str:
    for key in ("primary_symptom", "primary_symptom_id", "symptom_id", "symptom"):
        if str(diagnosis.get(key) or "").strip():
            return str(diagnosis.get(key)).strip()
    for matched_rule in diagnosis.get("matched_rules") or []:
        if isinstance(matched_rule, dict) and str(matched_rule.get("symptom_id") or "").strip():
            return str(matched_rule.get("symptom_id")).strip()
    for key in ("primary_symptom", "primary_symptom_id", "symptom_id", "symptom"):
        if str(approved_payload.get(key) or "").strip():
            return str(approved_payload.get(key)).strip()
    return ""


def _symptom_label(approved_payload: dict[str, Any], diagnosis: dict[str, Any], symptom_id: str) -> str:
    for key in ("symptom_label", "label_vi", "display_name", "label"):
        if str(diagnosis.get(key) or "").strip():
            return str(diagnosis.get(key)).strip()
    for matched_rule in diagnosis.get("matched_rules") or []:
        if isinstance(matched_rule, dict) and matched_rule.get("symptom_id") == symptom_id:
            label = matched_rule.get("symptom_label") or matched_rule.get("label_vi") or matched_rule.get("display_name")
            if str(label or "").strip():
                return str(label).strip()
    for key in ("label_vi", "symptom_label", "user_input"):
        if str(approved_payload.get(key) or "").strip():
            return str(approved_payload.get(key)).strip()
    return _slug(symptom_id)


def _symptom_name(diagnosis: dict[str, Any], symptom_id: str) -> str:
    for matched_rule in diagnosis.get("matched_rules") or []:
        if isinstance(matched_rule, dict) and matched_rule.get("symptom_id") == symptom_id:
            name = matched_rule.get("symptom_name") or matched_rule.get("name")
            if str(name or "").strip():
                return str(name).strip()
    return str(diagnosis.get("symptom_name") or _slug(symptom_id.removeprefix("SYM_")))


def _symptom_refs(diagnosis: dict[str, Any], primary_symptom: str, default_cf: float) -> list[dict[str, Any]]:
    raw_items = diagnosis.get("matched_rules") or diagnosis.get("symptoms") or []
    refs: list[dict[str, Any]] = []
    for priority, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        symptom_id = str(item.get("symptom_id") or item.get("id") or item.get("symptom") or "").strip()
        if not symptom_id or symptom_id == "USER_REPORTED_SYMPTOM":
            continue
        refs.append(
            {
                "symptom_id": symptom_id,
                "cf": _clamp_cf(item.get("cf"), default_cf),
                "priority": item.get("priority", priority),
            }
        )

    if primary_symptom and not any(ref["symptom_id"] == primary_symptom for ref in refs):
        refs.insert(0, {"symptom_id": primary_symptom, "cf": default_cf, "priority": 1})

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        if ref["symptom_id"] in seen:
            continue
        seen.add(ref["symptom_id"])
        deduped.append(ref)
    return deduped


def promote_approved_payload(approved_payload: dict[str, Any]) -> bool:
    if not isinstance(approved_payload, dict):
        raise ValueError("approved_payload must be a dict.")

    diagnoses = _diagnoses_from_payload(approved_payload)
    if not diagnoses:
        raise ValueError("approved_payload requires diagnoses list.")

    aliases = _load_json(ALIASES_PATH, {})
    rules_doc = _load_json(RULES_PATH, {"meta": {}, "rules": []})
    procedures = _load_json(PROCEDURES_PATH, {})

    rules = rules_doc.setdefault("rules", [])
    existing_by_key = {
        (str(rule.get("fault_id")), str(rule.get("primary_symptom") or rule.get("symptom"))): index
        for index, rule in enumerate(rules)
        if isinstance(rule, dict)
    }
    candidate_fault_ids = [
        str(item.get("fault_id"))
        for item in diagnoses
        if isinstance(item, dict) and str(item.get("fault_id")) != "UNMAPPED_SYMPTOM"
    ]

    promoted = False
    for diagnosis in diagnoses:
        if not isinstance(diagnosis, dict):
            continue
        fault_id = str(diagnosis.get("fault_id") or "").strip()
        if not fault_id or fault_id == "UNMAPPED_SYMPTOM":
            continue

        symptom_id = _primary_symptom_id(approved_payload, diagnosis)
        if not symptom_id:
            continue

        label_vi = _symptom_label(approved_payload, diagnosis, symptom_id)
        alias_entry = aliases.get(symptom_id, {})
        alias_values = approved_payload.get("aliases") if isinstance(approved_payload.get("aliases"), list) else []
        aliases[symptom_id] = {
            "symptom_id": symptom_id,
            "name": alias_entry.get("name") or _symptom_name(diagnosis, symptom_id),
            "display_name": label_vi,
            "label_vi": label_vi,
            "aliases": _merge_unique(alias_entry.get("aliases", []), [label_vi, _symptom_name(diagnosis, symptom_id), *alias_values]),
        }

        system_id, subsystem_id, components = _normalise_system(
            diagnosis.get("system"),
            diagnosis.get("system_id") or approved_payload.get("system_id"),
        )
        cf = _clamp_cf(diagnosis.get("final_cf", diagnosis.get("cf", 0.35)))
        symptom_refs = _symptom_refs(diagnosis, symptom_id, cf)

        repair_steps = _repair_steps(diagnosis)
        repair_id = f"REP_{_slug(fault_id).upper()}"
        fault_name = str(diagnosis.get("fault_name") or _slug(fault_id))
        fault_label = str(diagnosis.get("fault_label") or diagnosis.get("display_name") or fault_name)
        procedure_text = ". ".join(repair_steps) if repair_steps else "Kiểm tra theo xác nhận của chuyên gia."

        procedure = procedures.get(fault_id) or _procedure_for(
            fault_id,
            diagnosis,
            diagnosis.get("questions") or approved_payload.get("questions") or [],
        )

        rule = {
            "fault_id": fault_id,
            "fault_name": fault_name,
            "fault": fault_name,
            "display_name": fault_label,
            "label_vi": fault_label,
            "system": system_id,
            "system_id": system_id,
            "subsystem": subsystem_id,
            "subsystem_id": subsystem_id,
            "affected_components": components,
            "symptom": symptom_id,
            "primary_symptom": symptom_id,
            "candidate_fault_ids": candidate_fault_ids or [fault_id],
            "cf": cf,
            "final_cf": cf,
            "symptoms": symptom_refs,
            "resolution": {
                "parts": [fault_label],
                "tools": [],
                "procedure": procedure_text,
                "difficulty": "expert_review",
                "labor_hours": None,
            },
            "repairs": diagnosis.get("repairs", [])
            or [
                {
                    "repair_id": repair_id,
                    "repair_name": _slug(fault_id),
                    "display_name": f"Quy trình kiểm tra/sửa chữa: {fault_label}",
                    "label_vi": f"Quy trình kiểm tra/sửa chữa: {fault_label}",
                    "steps": repair_steps,
                }
            ],
            "status": "approved",
            "source": "llm_expert_review",
        }
        if procedure:
            rule["procedure"] = procedure

        key = (fault_id, symptom_id)
        if key in existing_by_key:
            rules[existing_by_key[key]] = rule
        else:
            existing_by_key[key] = len(rules)
            rules.append(rule)
        if procedure:
            procedures[fault_id] = procedure
        promoted = True

    if not promoted:
        raise ValueError("No promotable diagnoses were found.")

    rules_doc.setdefault("meta", {})["total_rules"] = len(rules)
    _write_json_files_atomic(
        {
            ALIASES_PATH: aliases,
            RULES_PATH: rules_doc,
            PROCEDURES_PATH: procedures,
        }
    )
    return True
