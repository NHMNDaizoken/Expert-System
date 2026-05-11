from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RAW_PATH = Path("data/raw/automotive_faults.json")
CF_PATH = Path("data/staging/cf_dynamic.json")
PROCEDURE_PATH = Path("data/staging/procedure_trees.json")
KG_PATH = Path("data/staging/kg_rules_from_dataset.json")
ALIASES_PATH = Path("data/staging/symptom_aliases.json")


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def slugify(text: Any) -> str:
    text = str(text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def make_id(prefix: str, text: Any) -> str:
    return f"{prefix}_{slugify(text).upper()}"


def load_records(path: str | Path = RAW_PATH) -> list[dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, list):
        return [record for record in data if isinstance(record, dict)]
    if isinstance(data, dict):
        for key in ("records", "faults", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [record for record in value if isinstance(record, dict)]
    return []


def fault_id_for(index: int) -> str:
    return f"FLT_{index:03d}"


def fault_name_for(record: dict[str, Any]) -> str:
    return slugify(record.get("subcategory") or record.get("fault") or record.get("name"))


def fault_display_for(record: dict[str, Any]) -> str:
    return str(record.get("subcategory") or record.get("fault") or record.get("name") or "Unknown Fault")


def symptom_id_for(symptom_text: str) -> str:
    return make_id("SYM", symptom_text)


def normalize_category(category: str) -> dict[str, Any]:
    return {
        "system_id": "SYS_ELECTRICAL",
        "subsystem_id": "SUB_STARTING",
        "affected_components": ["CMP_STARTER_MOTOR"],
    }


def extract_step_text(step: Any) -> str:
    if isinstance(step, str):
        return step
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
