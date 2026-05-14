from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

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
