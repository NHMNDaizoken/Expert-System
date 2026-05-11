from __future__ import annotations

from typing import Any

TERMINALS = {"DIAGNOSED", "REFUTED", "END"}


class ProcedureReasoner:
    """Navigate fault-specific diagnostic procedure trees."""

    def get_next_from_tree(
        self,
        current_step_id: str,
        last_answer: bool | None,
        procedure: dict[str, Any],
    ) -> dict[str, Any] | None:
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
            "question": step.get("question") or step.get("instruction"),
            "instruction": step.get("instruction"),
            "results": step.get("results", []),
            "terminal": None,
        }


def get_next_from_tree(
    current_step_id: str,
    last_answer: bool | None,
    procedure: dict[str, Any],
) -> dict[str, Any] | None:
    return ProcedureReasoner().get_next_from_tree(current_step_id, last_answer, procedure)
