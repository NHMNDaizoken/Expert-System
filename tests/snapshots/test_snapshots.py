import json
import os
from pathlib import Path
from src.expert_system.inference.engine import ExpertSystemEngine

SNAPSHOT_DIR = Path(__file__).parent / "data"

def sanitize_for_snapshot(data):
    """Recursively sort keys and remove volatile fields."""
    if isinstance(data, dict):
        return {k: sanitize_for_snapshot(v) for k, v in sorted(data.items())}
    elif isinstance(data, list):
        return [sanitize_for_snapshot(i) for i in data]
    elif isinstance(data, float):
        return round(data, 4)
    return data

def assert_match_snapshot(snapshot_name: str, actual_data):
    SNAPSHOT_DIR.mkdir(exist_ok=True, parents=True)
    snapshot_file = SNAPSHOT_DIR / f"{snapshot_name}.json"
    sanitized = sanitize_for_snapshot(actual_data)
    
    if os.getenv("UPDATE_SNAPSHOTS") == "1" or not snapshot_file.exists():
        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, ensure_ascii=False, indent=2)
        return

    with open(snapshot_file, "r", encoding="utf-8") as f:
        expected = json.load(f)

    assert sanitized == expected, f"Snapshot mismatch for {snapshot_name}. Run with UPDATE_SNAPSHOTS=1 to update."

def test_snapshot_engine_diagnosis_flow():
    engine = ExpertSystemEngine.from_staging()
    response = engine.diagnose("xe không nổ máy")
    assert_match_snapshot("diagnosis_flow_no_start", response)

def test_snapshot_engine_with_session():
    engine = ExpertSystemEngine.from_staging()
    res1 = engine.diagnose("động cơ quá nhiệt")
    next_q = res1.get("next_question")
    
    confirmed = []
    if res1.get("matched_symptoms"):
        confirmed.append(res1["matched_symptoms"][0]["symptom_id"])
    if next_q and "symptom_id" in next_q:
        confirmed.append(next_q["symptom_id"])
        
    res2 = engine.diagnose(
        "động cơ quá nhiệt", 
        confirmed_symptoms=confirmed
    )
    
    assert_match_snapshot("diagnosis_flow_overheat_step2", res2)

def test_snapshot_candidate_ranking():
    engine = ExpertSystemEngine.from_staging()
    res = engine.diagnose("động cơ nóng, hao nước làm mát")
    ranking = res.get("candidate_faults", [])
    assert_match_snapshot("candidate_ranking_multiple_symptoms", ranking)

def test_snapshot_trace_output():
    engine = ExpertSystemEngine.from_staging()
    res = engine.diagnose("khói đen từ ống xả")
    trace = res.get("reasoning_trace", {})
    assert_match_snapshot("reasoning_trace_black_smoke", trace)
