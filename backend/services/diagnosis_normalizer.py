from __future__ import annotations

from typing import Any


def normalize_diagnosis_response(payload: dict[str, Any], raw_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose a stable user-facing diagnosis shape while moving internals to debug."""
    tree = payload.get("diagnostic_tree") if isinstance(payload.get("diagnostic_tree"), dict) else {}
    context = tree.get("level_3_context") or {}
    faults = (
        payload.get("possible_faults")
        or payload.get("results")
        or payload.get("diagnoses")
        or tree.get("level_4_possible_faults")
        or []
    )

    debug = dict(payload.get("debug") or {})
    if raw_payload is not None:
        debug.setdefault("raw_payload", raw_payload)

    return {
        "system_level": payload.get("system_level") or tree.get("level_1_root") or {},
        "primary_symptom": payload.get("primary_symptom") or tree.get("level_2_primary_symptom") or {},
        "secondary_context": payload.get("secondary_context")
        or context.get("secondary_symptoms")
        or context.get("conditions")
        or [],
        "next_question": payload.get("next_question"),
        "possible_faults": faults,
        "diagnosis_steps": payload.get("diagnosis_steps") or tree.get("level_5_diagnosis_procedures") or [],
        "confirmation_tests": payload.get("confirmation_tests")
        or tree.get("level_6_confirmation_and_resolution", {}).get("confirmation_tests")
        or [],
        "parts": payload.get("parts")
        or tree.get("level_6_confirmation_and_resolution", {}).get("parts_to_replace")
        or [],
        "resolution": payload.get("resolution") or tree.get("level_6_confirmation_and_resolution") or {},
        "reasoning_summary": payload.get("reasoning_summary")
        or payload.get("reasoning_trace")
        or payload.get("explanation_summary")
        or [],
        "debug": debug,
    }
