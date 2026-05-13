from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import _bootstrap  # type: ignore # noqa: F401
except ModuleNotFoundError:
    from scripts import _bootstrap  # type: ignore # noqa: F401

from src.expert_system.utils.text import slugify

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "automotive_faults.json"
STAGING_DIR = PROJECT_ROOT / "data" / "staging"
CF_PATH = STAGING_DIR / "cf_dynamic.json"
PROCEDURE_PATH = STAGING_DIR / "procedure_trees.json"
EXPERT_TREE_PATH = STAGING_DIR / "expert_tree.json"
KG_PATH = STAGING_DIR / "kg_rules_from_dataset.json"
ALIASES_PATH = STAGING_DIR / "symptom_aliases.json"
TRANSLATION_PATH = STAGING_DIR / "vi_translations.json"

DEFAULT_TRANSLATIONS = {
    "obd_scanner": "Máy quét OBD",
    "multimeter": "Đồng hồ vạn năng",
}


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

def load_translations() -> dict[str, str]:
    translations = dict(DEFAULT_TRANSLATIONS)
    if TRANSLATION_PATH.exists():
        data = load_json(TRANSLATION_PATH)
        if isinstance(data, dict):
            translations.update({
                str(key): str(value)
                for key, value in data.items()
            })
    return translations


def vi_label(value: Any, translations: dict[str, str]) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    return translations.get(slugify(text), text)


def vi_system_label(system_id: str, translations: dict[str, str]) -> str:
    labels = {
        "SYS_BRAKE": "Brake System",
        "SYS_ENGINE": "Engine",
        "SYS_COOLING": "Cooling System",
        "SYS_FUEL": "Fuel System",
        "SYS_TRANSMISSION": "Transmission",
        "SYS_SUSPENSION_STEERING": "Suspension and Steering",
        "SYS_HVAC": "HVAC",
        "SYS_EXHAUST_EMISSION": "Exhaust and Emission",
        "SYS_ELECTRICAL": "Electrical System",
    }
    return vi_label(labels.get(system_id, system_id), translations)


def repair_display_for(fault_display_vi: str) -> str:
    return f"Quy trình kiểm tra/sửa chữa: {fault_display_vi}"


def symptom_to_question_vi(symptom: Any, translations: dict[str, str] | None = None) -> str:
    translations = translations or {}
    label = vi_label(symptom, translations)
    raw = str(symptom or "").lower()
    label_lower = label.lower()
    searchable = f"{raw} {label_lower}"

    patterns = [
        (("hard start", "difficulty starting", "khó nổ", "khó khởi động"), "Xe có khó nổ máy không?"),
        (("cold", "trời lạnh", "máy nguội"), "Xe có khó nổ khi máy nguội hoặc trời lạnh không?"),
        (("white smoke", "khói trắng"), "Khi khởi động, xe có khói trắng bất thường không?"),
        (("rough idle", "garanti", "rung giật", "không đều"), "Khi chạy garanti, động cơ có rung hoặc không đều không?"),
        (("check engine", "đèn báo lỗi động cơ"), "Đèn báo lỗi động cơ có sáng không?"),
        (("abs warning", "đèn abs"), "Đèn cảnh báo ABS có sáng không?"),
        (("grinding", "tiếng nghiến", "tiếng mài"), "Xe có phát ra tiếng nghiến hoặc tiếng mài bất thường không?"),
        (("vibration", "rung"), "Xe có bị rung bất thường khi vận hành không?"),
        (("low voltage", "điện áp thấp", "voltage"), "Đèn hoặc thiết bị điện trên xe có yếu bất thường không?"),
        (("noise", "tiếng ồn", "kêu"), "Xe có tiếng ồn bất thường không?"),
        (("leak", "rò rỉ", "chảy"), "Bạn có thấy dấu hiệu rò rỉ bất thường không?"),
        (("smell", "mùi"), "Bạn có ngửi thấy mùi bất thường khi xe hoạt động không?"),
        (("warning light", "đèn cảnh báo"), "Có đèn cảnh báo nào sáng trên bảng đồng hồ không?"),
        (("overheat", "quá nhiệt", "nhiệt độ cao"), "Kim nhiệt độ có tăng cao hoặc vào vùng đỏ không?"),
        (("coolant", "nước làm mát"), "Mức nước làm mát có thấp hoặc có dấu hiệu rò rỉ không?"),
        (("brake pedal", "bàn đạp phanh"), "Bàn đạp phanh có cảm giác bất thường không?"),
        (("battery", "ắc quy", "ac quy"), "Ắc quy hoặc hệ thống điện có dấu hiệu yếu không?"),
    ]
    for keywords, question in patterns:
        if any(keyword in searchable for keyword in keywords):
            return question

    return f"Bạn có nhận thấy dấu hiệu này không: {label_lower}?"



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


def build_aliases(
    records: list[dict[str, Any]],
    translations: dict[str, str] | None = None,
) -> dict[str, Any]:
    translations = translations or {}
    aliases: dict[str, dict[str, Any]] = {}
    for record in records:
        for symptom_text in record.get("symptoms", []):
            symptom_text = str(symptom_text).strip()
            if not symptom_text:
                continue
            symptom_id = symptom_id_for(symptom_text)
            display = vi_label(symptom_text, translations)
            aliases.setdefault(
                symptom_id,
                {
                    "name": slugify(symptom_text),
                    "display_name": display,
                    "label_vi": display,
                    "aliases": [symptom_text, display] if display != symptom_text else [symptom_text],
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


def build_resolution(
    record: dict[str, Any],
    fault_id: str,
    fault_display: str,
    translations: dict[str, str] | None = None,
) -> dict[str, Any]:
    translations = translations or {}
    steps = []
    for raw_step in record.get("diagnosis_steps") or []:
        text = extract_step_text(raw_step)
        if text:
            steps.append(vi_label(text, translations))
        for result in extract_step_results(raw_step):
            steps.append(f"Kết quả có thể: {vi_label(result, translations)}")

    procedure = ". ".join(steps) if steps else f"Inspect and repair {fault_display}."
    return {
        "parts": [vi_label(part, translations) for part in (record.get("parts") or [fault_display])],
        "tools": [vi_label(tool, translations) for tool in (record.get("tools") or ["OBD scanner", "Multimeter"])],
        "procedure": vi_label(procedure, translations),
        "difficulty": record.get("difficulty") or "intermediate",
        "labor_hours": record.get("labor_hours") or max(1, min(8, len(steps) or 1)),
        "repair_id": f"REP_{fault_id.split('_')[-1]}",
        "repair_name": f"diagnose_{fault_name_for(record)}",
        "steps": [vi_label(step, translations) for step in (steps or [procedure])],
    }

def build_procedure_trees(
    records: list[dict[str, Any]],
    translations: dict[str, str] | None = None,
) -> dict[str, Any]:
    translations = translations or {}
    trees = {}
    for index, record in enumerate(records, start=1):
        fault_id = fault_id_for(index)
        if not fault_name_for(record):
            continue
        raw_symptoms = record.get("symptoms") or []
        steps = {}
        step_ids = []

        for step_index, symptom in enumerate(raw_symptoms, start=1):
            symptom_text = str(symptom or "").strip()
            if not symptom_text:
                continue
            symptom_id = symptom_id_for(symptom_text)
            step_id = f"{fault_id.lower()}_s{step_index}"
            step_ids.append(step_id)
            steps[step_id] = {
                "id": step_id,
                "symptom_id": symptom_id,
                "symptom_label": vi_label(symptom_text, translations),
                "question": symptom_to_question_vi(symptom_text, translations),
                "is_question": True,
                "yes_next": None,
                "no_next": "REFUTED",
                "instruction": None,
                "results": [],
            }

        if not steps:
            fallback_id = f"{fault_id.lower()}_s1"
            step_ids.append(fallback_id)
            steps[fallback_id] = {
                "id": fallback_id,
                "question": f"Xác nhận các triệu chứng của {vi_label(fault_display_for(record), translations)}?",
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


def build_expert_tree(
    records: list[dict[str, Any]],
    rules: list[dict[str, Any]] | None = None,
    translations: dict[str, str] | None = None,
) -> dict[str, Any]:
    translations = translations or {}
    tree: dict[str, Any] = {
        "meta": {
            "version": "4.0",
            "architecture": "hierarchical_6_levels",
            "levels": [
                "system",
                "primary_symptom",
                "secondary_symptoms_context",
                "possible_faults",
                "diagnosis_procedures",
                "confirmation_tests_parts_resolution",
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "systems": {},
    }

    for index, record in enumerate(records, start=1):
        raw_symptoms = record.get("symptoms") or []
        if not raw_symptoms:
            continue

        fault_id = record.get("fault_id") or fault_id_for(index)
        fault_name = fault_name_for(record)
        fault_display = fault_display_for(record)
        fault_display_vi = vi_label(fault_display, translations)
        system_id, subsystem_id, affected_components = normalise_category(record.get("category", ""))

        primary_text = str(raw_symptoms[0]).strip()
        primary_id = symptom_id_for(primary_text)
        primary_display = vi_label(primary_text, translations)

        secondary_items = []
        for symptom_text in raw_symptoms[1:]:
            symptom_text = str(symptom_text).strip()
            if symptom_text:
                secondary_display = vi_label(symptom_text, translations)
                secondary_items.append(
                    {
                        "symptom_id": symptom_id_for(symptom_text),
                        "name": slugify(symptom_text),
                        "display_name": secondary_display,
                        "label_vi": secondary_display,
                    }
                )

        diagnosis_steps = []
        confirmation_tests = []
        for raw_step in record.get("diagnosis_steps") or []:
            text = extract_step_text(raw_step)
            if text:
                diagnosis_steps.append(vi_label(text, translations))
            for result in extract_step_results(raw_step):
                confirmation_tests.append(vi_label(result, translations))

        if not diagnosis_steps:
            diagnosis_steps = [vi_label(f"Inspect and verify {fault_display}.", translations)]

        resolution = build_resolution(record, fault_id, fault_display, translations)
        system_display = vi_system_label(system_id, translations)

        system_node = tree["systems"].setdefault(
            system_id,
            {
                "system_id": system_id,
                "display_name": system_display,
                "label_vi": system_display,
                "primary_symptoms": {},
            },
        )

        primary_node = system_node["primary_symptoms"].setdefault(
            primary_id,
            {
                "symptom_id": primary_id,
                "name": slugify(primary_text),
                "display_name": primary_display,
                "label_vi": primary_display,
                "secondary_symptoms": [],
                "possible_faults": [],
            },
        )

        existing_secondary_ids = {item["symptom_id"] for item in primary_node["secondary_symptoms"]}
        for item in secondary_items:
            if item["symptom_id"] not in existing_secondary_ids:
                primary_node["secondary_symptoms"].append(item)
                existing_secondary_ids.add(item["symptom_id"])

        primary_node["possible_faults"].append(
            {
                "fault_id": fault_id,
                "fault_name": fault_name,
                "display_name": fault_display_vi,
                "label_vi": fault_display_vi,
                "system_id": system_id,
                "subsystem_id": subsystem_id,
                "affected_components": affected_components,
                "confidence": float(record.get("cf") or record.get("confidence") or 0.5),
                "diagnosis_procedures": diagnosis_steps,
                "confirmation_tests": confirmation_tests,
                "required_parts": resolution["parts"],
                "tools": resolution["tools"],
                "resolution": {
                    "procedure": resolution["procedure"],
                    "difficulty": resolution["difficulty"],
                    "labor_hours": resolution["labor_hours"],
                    "steps": resolution["steps"],
                },
            }
        )

    for system in tree["systems"].values():
        for primary in system["primary_symptoms"].values():
            primary["possible_faults"].sort(key=lambda item: item.get("confidence", 0), reverse=True)

    return tree

def build_rules(
    records: list[dict[str, Any]],
    cf_data: dict[str, Any] | None = None,
    procedure_trees: dict[str, Any] | None = None,
    translations: dict[str, str] | None = None,
) -> dict[str, Any]:
    translations = translations or {}
    cf_map = cf_data.get("symptoms", cf_data) if isinstance(cf_data, dict) else {}
    candidate_sets = build_primary_candidate_sets(records)
    rules = []

    for index, record in enumerate(records, start=1):
        fault_name = fault_name_for(record)
        if not fault_name:
            continue
        fault_id = record.get("fault_id") or fault_id_for(index)
        display = fault_display_for(record)
        display_vi = vi_label(display, translations)
        system_id, subsystem_id, affected_components = normalise_category(record.get("category", ""))
        symptom_refs = []

        for priority, symptom_text in enumerate(record.get("symptoms", []), start=1):
            symptom_id = symptom_id_for(symptom_text)
            cf = float(cf_map.get(symptom_id, {}).get(fault_id, 0.5))
            symptom_refs.append({"symptom_id": symptom_id, "cf": round(cf, 4), "priority": priority})

        if not symptom_refs:
            continue

        resolution = build_resolution(record, fault_id, display, translations)
        procedure = (procedure_trees or {}).get(fault_id) or {"entry_step": None, "steps": {}}
        repair_display = repair_display_for(display_vi)

        rule = {
            "fault_id": fault_id,
            "fault_name": fault_name,
            "fault": fault_name,
            "display_name": display_vi,
            "label_vi": display_vi,
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
            "procedure": {"entry_step": procedure.get("entry_step"), "steps": procedure.get("steps", {})},
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
                    "display_name": repair_display,
                    "label_vi": repair_display,
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
    translations = load_translations()

    if rebuild_from_raw and records:
        cf_data = compute_cf(records)
        procedure_trees = build_procedure_trees(records, translations)
        rules = build_rules(records, cf_data, procedure_trees, translations)
        expert_tree = build_expert_tree(records, rules.get("rules", []), translations)
        aliases = build_aliases(records, translations)
    else:
        cf_data = load_existing_artifact(CF_PATH) or compute_cf(records)
        procedure_trees = load_existing_artifact(PROCEDURE_PATH) or build_procedure_trees(records, translations)
        rules = load_existing_artifact(KG_PATH) or build_rules(records, cf_data, procedure_trees, translations)
        expert_tree = build_expert_tree(records, rules.get("rules", []), translations)
        aliases = load_existing_artifact(ALIASES_PATH) or build_aliases(records, translations)

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
