from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


RAW_PATH = Path("data/raw/automotive_faults.json")
OUTPUT_PATH = Path("data/staging/cf_dynamic.json")
LOW_CF_THRESHOLD = 0.15


def slugify(text: str) -> str:
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def symptom_id(text: str) -> str:
    return f"SYM_{slugify(text).upper()}"


def fault_id(index: int) -> str:
    return f"FLT_{index:03d}"


def load_records(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, dict):
        return data.get("records") or data.get("faults") or data.get("data") or []
    return data


def compute_cf(records: list[dict]) -> dict:
    symptom_counts: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    faults: set[str] = set()

    for index, record in enumerate(records, start=1):
        fid = record.get("fault_id") or fault_id(index)
        faults.add(fid)
        for raw_symptom in record.get("symptoms", []):
            sid = symptom_id(raw_symptom)
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
            "low_cf_threshold": LOW_CF_THRESHOLD,
        },
        "symptoms": dict(symptoms),
    }


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute dynamic symptom/fault CFs.")
    parser.add_argument("--input", type=Path, default=RAW_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    save_json(args.output, compute_cf(load_records(args.input)))
    print(f"Saved dynamic CF map to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
