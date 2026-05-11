from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401

from dataset_rebuild_utils import (
    PROCEDURE_PATH,
    RAW_PATH,
    extract_step_results,
    extract_step_text,
    fault_display_for,
    fault_id_for,
    fault_name_for,
    load_records,
    save_json,
)


QUESTION_KEYWORDS = ("check", "test", "is there", "does", "if", "verify", "inspect", "measure")


def is_question(text: str) -> bool:
    lowered = text.lower()
    return "?" in text or any(keyword in lowered for keyword in QUESTION_KEYWORDS)


def question_text(text: str) -> str:
    text = text.strip()
    if not text:
        return "Confirm this diagnostic step?"
    return text if text.endswith("?") else f"{text}?"


def build_tree_for_record(record, fault_id: str):
    raw_steps = record.get("diagnosis_steps") or []
    steps = {}
    step_ids = []

    for index, raw_step in enumerate(raw_steps, start=1):
        text = extract_step_text(raw_step)
        if not text:
            continue
        step_id = f"{fault_id.lower()}_s{index}"
        step_ids.append(step_id)
        results = extract_step_results(raw_step)
        instruction = text
        if results:
            instruction = f"{text}. Expected findings: {', '.join(results)}"

        steps[step_id] = {
            "id": step_id,
            "question": question_text(text),
            "is_question": is_question(text),
            "yes_next": None,
            "no_next": "REFUTED",
            "instruction": None if is_question(text) else instruction,
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

    return {
        "fault_id": fault_id,
        "fault_name": fault_display_for(record),
        "entry_step": step_ids[0],
        "steps": steps,
    }


def build_procedure_trees(records):
    trees = {}
    for index, record in enumerate(records, start=1):
        fault_id = fault_id_for(index)
        if not fault_name_for(record):
            continue
        trees[fault_id] = build_tree_for_record(record, fault_id)
    return trees


def main() -> int:
    parser = argparse.ArgumentParser(description="Build YES/NO procedure trees from diagnosis steps.")
    parser.add_argument("--input", default=RAW_PATH)
    parser.add_argument("--output", default=PROCEDURE_PATH)
    args = parser.parse_args()

    records = load_records(args.input)
    save_json(args.output, build_procedure_trees(records))
    print(f"Built procedure trees for {len(records)} records -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
