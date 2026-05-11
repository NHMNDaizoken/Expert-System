from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from src.kg_inference import KGInference


DEFAULT_CASES_PATH = Path("data/staging/test_cases.json")


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def hit_at(predicted: list[str], expected: list[str], k: int) -> bool:
    if not expected:
        return True
    return expected[0] in predicted[:k]


def evaluate(cases: list[dict[str, Any]], top_k: int) -> tuple[dict[str, float], list[dict[str, Any]]]:
    engine = KGInference.from_files()
    details = []

    for case in cases:
        result = engine.diagnose(case["input"], top_k=top_k)
        predicted = [diagnosis["fault_id"] for diagnosis in result["diagnoses"]]
        expected = case.get("expected_faults", case.get("expected_faults_any_order", []))
        expected_prefix = True if not expected else predicted[: len(expected)] == expected
        expected_status = case.get("expected_status")
        status_match = expected_status is None or result["status"] == expected_status

        details.append(
            {
                "id": case["id"],
                "description": case.get("description", ""),
                "input": case["input"],
                "expected": expected,
                "expected_status": expected_status,
                "predicted": predicted,
                "status": result["status"],
                "top1": hit_at(predicted, expected, 1),
                "top3": hit_at(predicted, expected, 3),
                "top5": hit_at(predicted, expected, 5),
                "expected_prefix": expected_prefix,
                "status_match": status_match,
            }
        )

    total = len(details)
    if total == 0:
        return {"top1": 0.0, "top3": 0.0, "top5": 0.0}, details

    metrics = {
        "top1": sum(item["top1"] for item in details) / total,
        "top3": sum(item["top3"] for item in details) / total,
        "top5": sum(item["top5"] for item in details) / total,
    }
    return metrics, details


def print_report(metrics: dict[str, float], details: list[dict[str, Any]]) -> None:
    print("Diagnosis Evaluation")
    print("====================")
    print(f"Cases: {len(details)}")
    print(f"Top-1: {metrics['top1']:.2%}")
    print(f"Top-3: {metrics['top3']:.2%}")
    print(f"Top-5: {metrics['top5']:.2%}")
    print()

    for item in details:
        top_flags = (
            f"Top1={'PASS' if item['top1'] else 'FAIL'} "
            f"Top3={'PASS' if item['top3'] else 'FAIL'} "
            f"Top5={'PASS' if item['top5'] else 'FAIL'} "
            f"Order={'PASS' if item['expected_prefix'] else 'FAIL'}"
        )
        print(f"{item['id']} - {item['description']}")
        print(f"  Input:     {item['input']}")
        print(f"  Expected:  {item['expected']}")
        print(f"  ExpStatus: {item['expected_status']}")
        print(f"  Predicted: {item['predicted']}")
        print(f"  Status:    {item['status']} | Status={'PASS' if item['status_match'] else 'FAIL'} | {top_flags}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate KG diagnosis rankings.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to JSON test cases.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of diagnoses to request from the engine.",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Always exit 0 after printing the report.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        cases = load_cases(args.cases)
        metrics, details = evaluate(cases, args.top_k)
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2

    print_report(metrics, details)
    if args.allow_failures:
        return 0
    return 0 if all(item["top1"] and item["status_match"] for item in details) else 1


if __name__ == "__main__":
    raise SystemExit(main())
