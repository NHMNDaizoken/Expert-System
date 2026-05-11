from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkingMemory:
    initial_symptoms: list[str] = field(default_factory=list)
    confirmed_symptoms: list[str] = field(default_factory=list)
    rejected_symptoms: list[str] = field(default_factory=list)
    detected_systems: list[str] = field(default_factory=list)
    primary_symptom: str | None = None
    current_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    active_fault_id: str | None = None
    current_step_id: str | None = None
    branch_path: list[dict[str, Any]] = field(default_factory=list)
    step_history: list[str] = field(default_factory=list)
    question_count: int = 0
    last_answer: bool | None = None

    @classmethod
    def from_input(
        cls,
        matched_symptom_ids: list[str],
        confirmed_symptoms: list[str] | None = None,
        rejected_symptoms: list[str] | None = None,
    ) -> "WorkingMemory":
        confirmed = sorted(set(confirmed_symptoms or []) | set(matched_symptom_ids))
        rejected = sorted(set(rejected_symptoms or []))
        return cls(
            initial_symptoms=list(matched_symptom_ids),
            confirmed_symptoms=sorted(set(confirmed) - set(rejected)),
            rejected_symptoms=rejected,
        )

    @classmethod
    def from_session(cls, session: dict[str, Any]) -> "WorkingMemory":
        return cls(
            confirmed_symptoms=list(session.get("confirmed_symptoms") or []),
            rejected_symptoms=list(session.get("rejected_symptoms") or []),
            current_hypotheses=list(session.get("current_hypotheses") or []),
            active_fault_id=session.get("active_fault_id"),
            current_step_id=session.get("current_step_id"),
            branch_path=list(session.get("branch_path") or []),
            step_history=list(session.get("step_history") or []),
            question_count=len(session.get("step_history") or []) + len(session.get("answers") or {}),
            last_answer=session.get("last_answer"),
        )

    def confirm(self, symptom_id: str) -> None:
        if symptom_id not in self.confirmed_symptoms:
            self.confirmed_symptoms.append(symptom_id)
        self.rejected_symptoms = [item for item in self.rejected_symptoms if item != symptom_id]

    def reject(self, symptom_id: str) -> None:
        if symptom_id not in self.rejected_symptoms:
            self.rejected_symptoms.append(symptom_id)
        self.confirmed_symptoms = [item for item in self.confirmed_symptoms if item != symptom_id]

    def to_response_fields(self) -> dict[str, Any]:
        return {
            "confirmed_symptoms": sorted(set(self.confirmed_symptoms)),
            "rejected_symptoms": sorted(set(self.rejected_symptoms)),
            "detected_systems": self.detected_systems,
            "primary_symptom": self.primary_symptom,
            "confirmed_context": sorted(set(self.confirmed_symptoms) - ({self.primary_symptom} if self.primary_symptom else set())),
            "rejected_context": sorted(set(self.rejected_symptoms)),
            "active_fault_path": self.branch_path,
        }
