"""
trace — Human and machine-readable reasoning trace builder.

ExplanationBuilder produces structured explanation objects that
document each step of the inference process: normalization,
hypothesis generation, question selection, backward chaining,
CF calculation, and the final decision.
"""
from __future__ import annotations

from typing import Any

from src.expert_system.knowledge.loader import KnowledgeBase
from src.expert_system.runtime.state import WorkingMemory
from src.expert_system.runtime.trace_models import (
    FuzzyTrace,
    CFTrace,
    QuestionTrace,
    PolicyTrace,
    RejectedCandidateTrace,
    TraceEvent
)


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
        
        fuzzy_trace = FuzzyTrace(
            input_text=user_input,
            matched_symptoms=matched_symptoms
        ).model_dump()
        
        question_selection = self._question_selection(next_question)
        
        cf_calculation_steps = [
            step
            for diagnosis in diagnoses
            for step in self._cf_steps_for_diagnosis(diagnosis)
        ]
        
        rejected_candidates = [
            RejectedCandidateTrace(fault_id=fault_id, reason="Rejected via procedure tree or user answer").model_dump()
            for fault_id in (memory.rejected_faults or [])
        ]

        return {
            "input": user_input,
            "normalization": {
                "status": "matched" if matched_symptoms else "failed",
                "fuzzy_trace": fuzzy_trace,
                "confirmed_symptoms": memory.confirmed_symptoms,
                "rejected_symptoms": memory.rejected_symptoms,
            },
            "system_selection": {
                "detected_systems": memory.detected_systems,
                "explanation": "Hệ thống được chọn từ các luật liên kết với triệu chứng đã khớp và đã xác nhận.",
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
                    "explanation": "Lỗi này là ứng viên vì triệu chứng đã xác nhận khớp với luật trong cơ sở tri thức.",
                }
                for diagnosis in diagnoses
            ],
            "question_selection": question_selection,
            "backward_chaining": [self._rule_trace(diagnosis) for diagnosis in diagnoses],
            "cf_calculation_steps": cf_calculation_steps,
            "rejected_candidates": rejected_candidates,
            "final_decision": {
                "status": status,
                "top_fault": (
                    {
                        "fault_id": top["fault_id"],
                        "fault_label": top.get("fault_label"),
                        "confidence": top.get("confidence", top.get("final_cf")),
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
                    "confidence": diagnosis.get("confidence", diagnosis.get("final_cf")),
                    "matched_symptom_count": len(diagnosis["matched_rules"]),
                }
                for diagnosis in diagnoses
            ],
        }

    def summary(self, memory: WorkingMemory, diagnoses: list[dict[str, Any]], status: str) -> str:
        if not diagnoses:
            return "Không có lỗi nào trong cơ sở tri thức khớp với các triệu chứng đã xác nhận."
        top = diagnoses[0]
        system = self.kb.system_label(top.get("system")) or top.get("system") or "Hệ thống chưa rõ"
        primary = self.kb.label_for_symptom(memory.primary_symptom) if memory.primary_symptom else "triệu chứng đã mô tả"
        confidence = top.get('confidence', top.get('final_cf'))
        return (
            f"{system} > {primary} > {top.get('fault_label', top.get('fault_name'))} "
            f"với CF {confidence}. Trạng thái: {status}."
        )

    def _question_selection(self, next_question: dict[str, Any] | None) -> dict[str, Any]:
        if not next_question or next_question.get("done"):
            return {
                "status": "not_selected",
                "explanation": "Không còn câu hỏi bổ sung hữu ích.",
            }
            
        trace = QuestionTrace(
            question_id=next_question.get("symptom_id", "unknown"),
            mode=next_question.get("mode", "unknown"),
            score=next_question.get("information_gain", 0.0)
        ).model_dump()
        
        return {
            "status": "selected",
            "trace": trace,
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
            "rule_text": f"NẾU {' VÀ '.join(symptoms) if symptoms else 'chưa có triệu chứng khớp'} THÌ {diagnosis.get('fault_label', diagnosis['fault_name'])}",
        }

    def _cf_steps_for_diagnosis(self, diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
        steps = []
        contributions = []
        for rule in diagnosis.get("matched_rules", []):
            contributions.append({
                "symptom_id": rule.get("symptom_id"),
                "cf": rule.get("cf")
            })
            steps.append(
                {
                    "fault_id": diagnosis["fault_id"],
                    "fault_label": diagnosis.get("fault_label"),
                    "symptom_id": rule.get("symptom_id"),
                    "symptom_label": rule.get("symptom_label"),
                    "evidence_cf": rule.get("cf"),
                    "priority": rule.get("priority"),
                    "formula": "cf_kết_hợp = cf_cũ + cf_bằng_chứng * (1 - cf_cũ)",
                    "explanation": "Triệu chứng đã xác nhận làm tăng độ tin cậy của lỗi theo hệ số chắc chắn trong luật.",
                }
            )
            
        cf_trace = CFTrace(
            fault_id=diagnosis["fault_id"],
            initial_cf=0.0,
            contributions=contributions,
            final_cf=diagnosis.get("confidence", diagnosis.get("final_cf", 0.0))
        ).model_dump()
        
        steps.append(
            {
                "fault_id": diagnosis["fault_id"],
                "fault_label": diagnosis.get("fault_label"),
                "formula": "cf_cuối là điểm tin cậy có giới hạn, không phải xác suất Bayes.",
                "score_breakdown": diagnosis.get("score_breakdown", {}),
                "cf_trace": cf_trace
            }
        )
        return steps
