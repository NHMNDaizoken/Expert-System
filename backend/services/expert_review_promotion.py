from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.expert_system.utils.text import slugify

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_EXPERT_PATH = PROJECT_ROOT / "data" / "raw" / "expert_accepted_faults.json"
RAW_EXPERT_TREES_PATH = PROJECT_ROOT / "data" / "raw" / "expert_accepted_decision_trees.json"
BUILD_KNOWLEDGE_SCRIPT = PROJECT_ROOT / "scripts" / "build" / "build_knowledge.py"
IMPORT_GRAPH_SCRIPT = PROJECT_ROOT / "scripts" / "graph" / "import_graph.py"

def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return default

def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

def _is_decision_tree(candidate: dict[str, Any]) -> bool:
    return isinstance(candidate, dict) and candidate.get("type") == "diagnostic_decision_tree"

def _system_to_category(system: str) -> str:
    mapping = {
        "engine": "Engine",
        "cooling_system": "Cooling System",
        "fuel_system": "Fuel System",
        "ignition_system": "Engine",
        "brake_system": "Brake System",
        "electrical_system": "Electrical System",
        "transmission": "Transmission",
        "suspension": "Suspension and Steering",
        "steering": "Suspension and Steering",
    }
    return mapping.get(str(system or "").lower(), "Electrical System")


def _merge_name_list(*groups: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for item in group or []:
            if isinstance(item, dict):
                text = str(item.get("name_vi") or item.get("component_id") or item.get("name") or "").strip()
            else:
                text = str(item or "").strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def _flatten_steps(*groups: list[Any]) -> list[str]:
    steps: list[str] = []
    for group in groups:
        for entry in group or []:
            if isinstance(entry, str):
                text = entry.strip()
            elif isinstance(entry, dict):
                text = str(entry.get("step") or entry.get("instruction") or "").strip()
            else:
                text = str(entry or "").strip()
            if text:
                steps.append(text)
    return steps


def _fault_records_from_decision_tree_candidate(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Flatten each RESULT leaf into raw automotive_faults-style rows for expert_accepted_faults.json.
    Questions are not persisted as KG nodes.
    """
    root = candidate.get("root_symptom") or {}
    root_label = str(root.get("label_vi") or root.get("symptom_id") or "").strip() or "Triệu chứng đã duyệt"
    candidate_id = candidate.get("candidate_id") or "unknown_candidate"
    selected_path = candidate.get("selected_path") or []
    selected_result_id = candidate.get("selected_result_node_id")
    tree = candidate.get("tree") or {}
    nodes = [n for n in tree.get("nodes", []) if isinstance(n, dict)]
    result_nodes = [n for n in nodes if n.get("type") == "result"]
    if not result_nodes:
        return []

    records: list[dict[str, Any]] = []
    for node in result_nodes:
        fault = node.get("fault") or {}
        fault_name = str(fault.get("fault_name") or fault.get("fault_id") or node.get("node_id") or "fault").strip()
        fault_id = (
            str(fault.get("fault_id") or "").strip()
            or f"FLT_{slugify(str(candidate_id) + '_' + str(node.get('node_id'))).upper()}"
        )
        diagnostic = _flatten_steps(node.get("diagnostic_steps"), fault.get("diagnostic_steps"))
        repair = _flatten_steps(node.get("repair_steps"), fault.get("repair_steps"))
        causes = [str(c).strip() for c in (node.get("causes") or fault.get("causes") or []) if str(c).strip()]
        safety = [str(s).strip() for s in (node.get("safety_notes") or fault.get("safety_notes") or []) if str(s).strip()]
        components = _merge_name_list(node.get("components"), fault.get("components"))
        path_for_meta = selected_path if selected_result_id and node.get("node_id") == selected_result_id else []

        diag_steps_payload = []
        for s in diagnostic:
            diag_steps_payload.append({"step": s, "result": ["Bất thường", "Bình thường"]})
        for s in repair:
            diag_steps_payload.append({"step": f"Thực hiện: {s}", "result": ["Hoàn thành", "Chưa hoàn thành"]})

        severity = fault.get("severity") or node.get("severity") or "medium"
        confidence = float(fault.get("confidence") or 0.5)

        records.append(
            {
                "fault_id": fault_id,
                "category": _system_to_category(fault.get("system")),
                "subcategory": fault_name,
                "symptoms": [root_label],
                "diagnosis_steps": diag_steps_payload,
                "parts": components or [fault_name],
                "tools": ["Máy quét OBD", "Đồng hồ vạn năng"],
                "difficulty": "advanced" if str(severity).lower() in {"high", "critical"} else "intermediate",
                "labor_hours": max(1, min(8, len(repair) or 1)),
                "causes": causes,
                "safety_notes": safety,
                "confidence": confidence,
                "promotion_metadata": {
                    "source": "expert_approved_llm_tree",
                    "candidate_id": candidate_id,
                    "original_tree_path": path_for_meta,
                    "result_node_id": node.get("node_id"),
                    "severity": severity,
                    "diagnostic_steps": diagnostic,
                    "repair_steps": repair,
                },
            }
        )
    return records


def _append_expert_faults_from_tree(candidate: dict[str, Any]) -> None:
    new_rows = _fault_records_from_decision_tree_candidate(candidate)
    if not new_rows:
        raise ValueError("Decision tree candidate has no RESULT leaves to promote.")
    existing = _load_json(RAW_EXPERT_PATH, [])
    if not isinstance(existing, list):
        existing = []

    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        meta = row.get("promotion_metadata") or {}
        return (meta.get("candidate_id"), meta.get("result_node_id"), row.get("fault_id"), tuple(row.get("symptoms") or []))

    existing_keys = {key(r) for r in existing if isinstance(r, dict)}
    for row in new_rows:
        if key(row) not in existing_keys:
            existing.append(row)
            existing_keys.add(key(row))

    _write_json(RAW_EXPERT_PATH, existing)


def _promote_decision_tree(candidate: dict[str, Any]) -> None:
    data = _load_json(RAW_EXPERT_TREES_PATH, {"trees": []})
    if not isinstance(data, dict):
        data = {"trees": []}
    trees = data.setdefault("trees", [])
    existing_ids = {tree.get("candidate_id") for tree in trees if isinstance(tree, dict)}
    approved = {
        "candidate_id": candidate.get("candidate_id"),
        "source": "expert_approved_llm_tree",
        "root_symptom": candidate.get("root_symptom", {}),
        "tree": candidate.get("tree", {}),
        "type": candidate.get("type"),
        "approved_at": candidate.get("approved_at") or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "approved_by": "expert",
        "selected_paths": candidate.get("selected_paths") or ([candidate.get("selected_path")] if candidate.get("selected_path") else []),
    }
    if approved["candidate_id"] in existing_ids:
        for index, tree in enumerate(trees):
            if tree.get("candidate_id") == approved["candidate_id"]:
                trees[index] = approved
                break
    else:
        trees.append(approved)
    _write_json(RAW_EXPERT_TREES_PATH, data)

def _llm_to_raw_dataset(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts LLM candidate schema to raw dataset schema."""
    records = []
    faults = candidate.get("faults", [])
    
    for fault in faults:
        # Map system to friendly category
        system_map = {
            "engine": "Engine",
            "cooling_system": "Cooling System",
            "fuel_system": "Fuel System",
            "brake_system": "Brake System",
            "electrical_system": "Electrical System",
            "transmission": "Transmission",
        }
        category = system_map.get(fault.get("system"), "Electrical System")
        
        # Build diagnosis steps from both diagnostic and repair steps
        diag_steps = []
        for s in fault.get("diagnostic_steps", []):
            diag_steps.append({"step": s, "result": ["Bất thường", "Bình thường"]})
        for s in fault.get("repair_steps", []):
            diag_steps.append({"step": f"Thực hiện: {s}", "result": ["Hoàn thành", "Chưa hoàn thành"]})

        record = {
            "category": category,
            "subcategory": fault.get("fault_name", "Unknown Fault"),
            "symptoms": [s.get("label_vi") for s in fault.get("symptoms", []) if s.get("label_vi")],
            "diagnosis_steps": diag_steps,
            "parts": [c.get("name_vi") for c in fault.get("components", []) if c.get("name_vi")],
            "tools": ["Máy quét OBD", "Đồng hồ vạn năng"],
            "difficulty": "intermediate" if fault.get("severity") != "critical" else "advanced",
            "labor_hours": 2,
            "causes": fault.get("causes", []),
            "safety_notes": fault.get("safety_notes", []),
            "confidence": fault.get("confidence", 0.5)
        }
        records.append(record)
    return records

def promote_approved_payload(approved_payload: dict[str, Any]) -> bool:
    """
    Promotes an approved LLM suggestion by:
    1. Converting it to the raw dataset format.
    2. Appending it to expert_accepted_faults.json.
    3. Rebuilding the knowledge base and graph.
    """
    if not isinstance(approved_payload, dict):
        raise ValueError("approved_payload must be a dict.")

    # Extract candidate
    candidate = approved_payload.get("llm_output")
    if not candidate:
        # Try if the payload IS the candidate (legacy or direct)
        candidate = approved_payload

    if _is_decision_tree(candidate):
        _promote_decision_tree(candidate)
        _append_expert_faults_from_tree(candidate)
        try:
            subprocess.run([sys.executable, str(BUILD_KNOWLEDGE_SCRIPT), "--rebuild-from-raw"], check=True)
            subprocess.run([sys.executable, str(IMPORT_GRAPH_SCRIPT), "--clear"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error during rebuild pipeline: {e}")
            return False
        return True

    new_records = _llm_to_raw_dataset(candidate)
    if not new_records:
        raise ValueError("No valid diagnostic records found in approved payload.")

    # Load existing expert accepted faults
    existing_records = _load_json(RAW_EXPERT_PATH, [])
    if not isinstance(existing_records, list):
        existing_records = []
    
    # Merge (avoiding duplicates by subcategory and primary symptom)
    for nr in new_records:
        is_dup = False
        for er in existing_records:
            if er.get("subcategory") == nr.get("subcategory") and er.get("symptoms") == nr.get("symptoms"):
                is_dup = True
                break
        if not is_dup:
            existing_records.append(nr)

    # Save back to raw
    _write_json(RAW_EXPERT_PATH, existing_records)

    # Trigger Rebuild Pipeline
    try:
        print("Starting knowledge rebuild...")
        # 1. Build knowledge artifacts from raw (including the new expert-accepted ones)
        subprocess.run([sys.executable, str(BUILD_KNOWLEDGE_SCRIPT), "--rebuild-from-raw"], check=True)
        
        # 2. Import to Neo4j graph
        print("Starting graph import...")
        subprocess.run([sys.executable, str(IMPORT_GRAPH_SCRIPT), "--clear"], check=True)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error during rebuild pipeline: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False
