"""
smoke_test — Quick sanity check that the expert system can load and diagnose.

Run from project root:
    python scripts/dev/smoke_test.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_INPUTS = [
    "ABS warning light on",
    "brake pedal pulsation",
    "engine overheating",
]


def main() -> int:
    from src.expert_system.inference.engine import ExpertSystemEngine

    print("Loading ExpertSystemEngine from staging data...")
    try:
        engine = ExpertSystemEngine.from_staging()
    except Exception as exc:
        print(f"FAIL: Could not load engine: {exc}")
        return 1

    print(f"Loaded {len(engine.kb.rules)} rules, {len(engine.kb.symptom_aliases)} symptoms\n")

    all_ok = True
    for text in DEFAULT_INPUTS:
        print(f"Input: {text}")
        try:
            result = engine.diagnose(text, top_k=3)
            status = result.get("status", "?")
            diagnoses = result.get("diagnoses", [])
            print(f"  Status: {status}")
            print(f"  Diagnoses: {len(diagnoses)}")
            if diagnoses:
                top = diagnoses[0]
                print(f"  Top: {top.get('fault_id')} (CF={top.get('final_cf')})")
            print()
        except Exception as exc:
            print(f"  FAIL: {exc}\n")
            all_ok = False

    if all_ok:
        print("SMOKE TEST PASSED")
        return 0
    else:
        print("SMOKE TEST FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
