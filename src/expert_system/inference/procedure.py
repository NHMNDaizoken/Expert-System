"""
procedure — Procedure-tree navigation for fault-specific diagnostic flows.

ProcedureRunner navigates step-by-step diagnostic procedure trees,
following yes/no branches based on user answers until reaching
a terminal state (DIAGNOSED, REFUTED, or END).
"""
from __future__ import annotations

from typing import Any


TERMINALS = {"DIAGNOSED", "REFUTED", "END"}
MAX_QUESTION_DEPTH = 8


class ProcedureRunner:
    """Navigate fault-specific diagnostic procedure trees."""

    def get_next_from_tree(
        self,
        current_step_id: str,
        last_answer: bool | None,
        procedure: dict[str, Any],
        visited: set[str] | list[str] | None = None,
        max_depth: int = MAX_QUESTION_DEPTH,
    ) -> dict[str, Any] | None:
        visited_set = set(visited or [])
        if current_step_id in visited_set and last_answer is None:
            return {"terminal": "END", "step_id": current_step_id, "error": "loop_detected"}
        if len(visited_set) >= max_depth:
            return {"terminal": "END", "step_id": current_step_id, "error": "max_depth_reached"}

        steps = procedure.get("steps", {})
        step = steps.get(current_step_id)
        if not step:
            return None

        if last_answer is None:
            return self._step_payload(current_step_id, step)

        branch = "yes_next" if last_answer else "no_next"
        next_id = step.get(branch)
        if next_id in (None, "DIAGNOSED", "REFUTED"):
            return {"terminal": next_id or "END", "step_id": next_id}
        if next_id in visited_set:
            return {"terminal": "END", "step_id": next_id, "error": "loop_detected"}
        if len(visited_set) + 1 >= max_depth:
            return {"terminal": "END", "step_id": next_id, "error": "max_depth_reached"}

        next_step = steps.get(next_id)
        if not next_step:
            return {"terminal": "END", "step_id": next_id, "error": "missing_step"}
        return self._step_payload(next_id, next_step)

    def entry_step(self, procedure: dict[str, Any] | None) -> dict[str, Any] | None:
        if not procedure:
            return None
        entry = procedure.get("entry_step")
        step = procedure.get("steps", {}).get(entry)
        if not entry or not step:
            return None
        return self._step_payload(entry, step)

    def _step_payload(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        return {
            "step_id": step_id,
            "symptom_id": step.get("symptom_id"),
            "symptom_label": step.get("symptom_label"),
            "question": step.get("question") or step.get("instruction"),
            "instruction": step.get("instruction"),
            "results": step.get("results", []),
            "terminal": None,
        }


def get_next_from_tree(
    current_step_id: str,
    last_answer: bool | None,
    procedure: dict[str, Any],
    visited: set[str] | list[str] | None = None,
) -> dict[str, Any] | None:
    return ProcedureRunner().get_next_from_tree(current_step_id, last_answer, procedure, visited)


# Backward compatibility alias
ProcedureReasoner = ProcedureRunner
