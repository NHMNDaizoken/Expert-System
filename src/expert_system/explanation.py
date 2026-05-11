from __future__ import annotations

from typing import Any

from src.expert_system.knowledge_base import KnowledgeBase
from src.expert_system.working_memory import WorkingMemory


class ExplanationBuilder:
    """Build human and machine-readable reasoning details."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def build(
        self,
        *,
        user_input: str,
        matched_symptoms: list[dict[str, Any]],
        memory: WorkingMemory,
        diagnoses: list[dict[str, Any]],
        next_question: dict[str, Any] | None,
        status: str,
    ) -> dict[str, Any]:
        top = diagnoses[0] if diagnoses else None
        return {
            "input": user_input,
            "normalization": {
                "status": "matched" if matched_symptoms else "failed",
                "matched_symptoms": matched_symptoms,
                "confirmed_symptoms": memory.confirmed_symptoms,
                "rejected_symptoms": memory.rejected_symptoms,
            },
            "system_selection": {
                "detected_systems": memory.detected_systems,
                "explanation": "Systems were selected from rules connected to the matched and confirmed symptoms.",
            },
            "primary_symptom": memory.primary_symptom,
            "hypothesis_generation": [
                {
                    "fault_id": diagnosis["fault_id"],
                    "fault_name": diagnosis["fault_name"],
                    "fault_label": diagnosis.get("fault_label"),
                    "system": diagnosis.get("system"),
                    "triggered_by": [
                        rule.get("symptom_id")
                        for rule in diagnosis.get("matched_rules", [])
                        if rule.get("symptom_id")
                    ],
                    "matched_rule_count": len(diagnosis.get("matched_rules", [])),
                    "explanation": "Fault is a candidate because confirmed symptoms match KB rules.",
                }
                for diagnosis in diagnoses
            ],
            "question_selection": self._question_selection(next_question),
            "backward_chaining": [self._rule_trace(diagnosis) for diagnosis in diagnoses],
            "cf_calculation_steps": [
                step
                for diagnosis in diagnoses
                for step in self._cf_steps_for_diagnosis(diagnosis)
            ],
            "final_decision": {
                "status": status,
                "top_fault": (
                    {
                        "fault_id": top["fault_id"],
                        "fault_label": top.get("fault_label"),
                        "final_cf": top.get("final_cf"),
                        "decision": top.get("decision"),
                    }
                    if top
                    else None
                ),
            },
            "ranking": [
                {
                    "fault_id": diagnosis["fault_id"],
                    "score": diagnosis["score"],
                    "final_cf": diagnosis["final_cf"],
                    "matched_symptom_count": len(diagnosis["matched_rules"]),
                }
                for diagnosis in diagnoses
            ],
        }

    def summary(self, memory: WorkingMemory, diagnoses: list[dict[str, Any]], status: str) -> str:
        if not diagnoses:
            return "No Knowledge Base fault matched the confirmed symptoms."
        top = diagnoses[0]
        system = self.kb.system_label(top.get("system")) or top.get("system") or "Unknown system"
        primary = self.kb.label_for_symptom(memory.primary_symptom) if memory.primary_symptom else "the reported symptom"
        return (
            f"{system} > {primary} > {top.get('fault_label', top.get('fault_name'))} "
            f"with CF {top.get('final_cf')}. Status: {status}."
        )

    def _question_selection(self, next_question: dict[str, Any] | None) -> dict[str, Any]:
        if not next_question or next_question.get("done"):
            return {
                "status": "not_selected",
                "explanation": "No useful follow-up question remains.",
            }
        return {
            "status": "selected",
            "selected_symptom": next_question.get("symptom_id"),
            "selected_label": next_question.get("label"),
            "question": next_question.get("question"),
            "mode": next_question.get("mode"),
            "information_gain": next_question.get("information_gain"),
            "fault_preview": next_question.get("fault_preview"),
            "explanation": next_question.get("explanation"),
        }

    def _rule_trace(self, diagnosis: dict[str, Any]) -> dict[str, Any]:
        symptoms = [
            rule.get("symptom_label") or rule.get("symptom_id")
            for rule in diagnosis.get("matched_rules", [])
        ]
        return {
            "fault_id": diagnosis["fault_id"],
            "then": diagnosis.get("fault_label", diagnosis["fault_name"]),
            "if": [
                {
                    "symptom_id": rule.get("symptom_id"),
                    "symptom_label": rule.get("symptom_label"),
                    "cf": rule.get("cf"),
                    "priority": rule.get("priority"),
                }
                for rule in diagnosis.get("matched_rules", [])
            ],
            "rule_text": f"IF {' AND '.join(symptoms) if symptoms else 'no matched symptom'} THEN {diagnosis.get('fault_label', diagnosis['fault_name'])}",
        }

    def _cf_steps_for_diagnosis(self, diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
        steps = []
        for rule in diagnosis.get("matched_rules", []):
            steps.append(
                {
                    "fault_id": diagnosis["fault_id"],
                    "fault_label": diagnosis.get("fault_label"),
                    "symptom_id": rule.get("symptom_id"),
                    "symptom_label": rule.get("symptom_label"),
                    "evidence_cf": rule.get("cf"),
                    "priority": rule.get("priority"),
                    "formula": "combined_cf = old_cf + evidence_cf * (1 - old_cf)",
                    "explanation": "A confirmed symptom increases fault confidence through its rule certainty factor.",
                }
            )
        steps.append(
            {
                "fault_id": diagnosis["fault_id"],
                "fault_label": diagnosis.get("fault_label"),
                "formula": "final_cf is a bounded confidence score, not Bayesian probability.",
                "score_breakdown": diagnosis.get("score_breakdown", {}),
            }
        )
        return steps
