"""
engine — Main orchestrator for the expert-system diagnosis flow.

ExpertSystemEngine ties together fuzzy matching, certainty scoring,
question selection, procedure navigation, and decision policies
into a single diagnose() entry point. It does NOT contain the
detailed implementations of those algorithms — they live in their
own modules under inference/.
"""
from __future__ import annotations

from typing import Any

from src.expert_system.knowledge.loader import KnowledgeBase
from src.expert_system.llm_fallback import diagnose_with_llm
from src.expert_system.inference.procedure import ProcedureRunner
from src.expert_system.inference.fuzzy import SymptomMatcher
from src.expert_system.inference.certainty import rank_faults as _rank_faults_impl, load_cf_map
from src.expert_system.inference.question import (
    select_by_information_gain as _select_by_information_gain,
    select_information_gain_question as _select_ig_question,
    related_symptoms as _related_symptoms_impl,
)
from src.expert_system.inference.policy import apply_response_policy
from src.expert_system.runtime.state import WorkingMemory
from src.expert_system.runtime.result import DiagnosisResponse
from src.expert_system.runtime.trace import ExplanationBuilder
from src.expert_system.utils.scoring import combine_cf, confidence_label


class ExpertSystemEngine:
    """Orchestrates the hierarchical automotive diagnosis expert system."""

    def __init__(self, kb: KnowledgeBase | None = None, max_questions: int = 8):
        self.kb = kb or KnowledgeBase.from_staging()
        self.matcher = SymptomMatcher(self.kb.symptom_aliases)
        self.procedure_runner = ProcedureRunner()
        self.explanations = ExplanationBuilder(self.kb)
        self.max_questions = max_questions

    @classmethod
    def from_staging(cls) -> "ExpertSystemEngine":
        return cls(KnowledgeBase.from_staging())

    def diagnose(
        self,
        text: str,
        top_k: int = 5,
        confirmed_symptoms: list[str] | None = None,
        rejected_symptoms: list[str] | None = None,
        session: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        matched_symptoms = self.matcher.match(text)
        memory = self._prepare_memory(matched_symptoms, confirmed_symptoms, rejected_symptoms, session)

        if not memory.confirmed_symptoms:
            return self._llm_fallback_response(text, matched_symptoms, memory, top_k)

        memory.primary_symptom = self._select_primary_symptom(memory.confirmed_symptoms)
        memory.detected_systems = self._detect_systems(memory.confirmed_symptoms)
        candidate_rules = self._candidate_rules(memory)
        diagnoses = self._rank(candidate_rules, memory.confirmed_symptoms, memory.rejected_symptoms, top_k)
        
        if not diagnoses:
            return self._llm_fallback_response(text, matched_symptoms, memory, top_k)

        status, next_question, procedure_terminal = self._evaluate_state(memory, diagnoses)
        
        return self._build_response(
            text=text,
            matched_symptoms=matched_symptoms,
            memory=memory,
            diagnoses=diagnoses,
            status=status,
            next_question=next_question,
            procedure_terminal=procedure_terminal,
        )

    def _prepare_memory(
        self,
        matched_symptoms: list[dict[str, Any]],
        confirmed_symptoms: list[str] | None,
        rejected_symptoms: list[str] | None,
        session: dict[str, Any] | None,
    ) -> WorkingMemory:
        matched_ids = [item["symptom_id"] for item in matched_symptoms]
        if session:
            memory = WorkingMemory.from_session(session)
            for symptom_id in matched_ids:
                memory.confirm(symptom_id)
        else:
            memory = WorkingMemory.from_input(matched_ids, confirmed_symptoms, rejected_symptoms)

        if confirmed_symptoms:
            for symptom_id in confirmed_symptoms:
                memory.confirm(symptom_id)
        if rejected_symptoms:
            for symptom_id in rejected_symptoms:
                memory.reject(symptom_id)
        return memory

    def _evaluate_state(
        self,
        memory: WorkingMemory,
        diagnoses: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        if self._confident_enough(diagnoses, memory):
            next_question = None
            procedure_terminal = "DIAGNOSED"
        else:
            next_question, procedure_terminal = self._select_next_step(memory, diagnoses)

        memory.current_hypotheses = diagnoses
        memory.active_fault_id = diagnoses[0]["fault_id"] if diagnoses else None

        if procedure_terminal and procedure_terminal != "DIAGNOSED" and not next_question:
            next_question = _select_ig_question(memory, diagnoses, self.kb, self.max_questions)

        if procedure_terminal == "DIAGNOSED" or (diagnoses and not next_question):
            status = "diagnosed"
            next_question = None
        elif next_question:
            status = "need_more_info"
        else:
            status = "unknown_symptom"
            
        return status, next_question, procedure_terminal

    def _build_response(
        self,
        text: str,
        matched_symptoms: list[dict[str, Any]],
        memory: WorkingMemory,
        diagnoses: list[dict[str, Any]],
        status: str,
        next_question: dict[str, Any] | None,
        procedure_terminal: str | None,
    ) -> dict[str, Any]:
        trace = self.explanations.build(
            user_input=text,
            matched_symptoms=matched_symptoms,
            memory=memory,
            diagnoses=diagnoses,
            next_question=next_question,
            status=status,
        )
        response = DiagnosisResponse(
            matched_symptoms=matched_symptoms,
            diagnoses=diagnoses,
            results=diagnoses if status == "diagnosed" else [],
            current_hypotheses=diagnoses,
            candidate_faults=self._candidate_faults_payload(diagnoses),
            next_question=next_question,
            reasoning_trace=trace,
            status=status,
            is_final=status == "diagnosed",
            tree_level=self._tree_level(status, next_question),
            explanation_summary=self.explanations.summary(memory, diagnoses, status),
            source="staging_files_kg",
            procedure_terminal=procedure_terminal,
            **memory.to_response_fields(),
        )
        if status == "diagnosed" and diagnoses:
            response["resolution"] = diagnoses[0].get("resolution")
        return dict(response)

    def _confident_enough(self, diagnoses: list[dict[str, Any]], memory: WorkingMemory) -> bool:
        if not diagnoses:
            return False

        top = diagnoses[0]
        second = diagnoses[1] if len(diagnoses) > 1 else None

        top_cf = float(top.get("final_cf", top.get("confidence", 0)) or 0)
        second_cf = float(second.get("final_cf", second.get("confidence", 0)) or 0) if second else 0.0
        gap = top_cf - second_cf

        evidence_count = len(set(memory.confirmed_symptoms or []))

        # Chỉ kết luận sớm khi có ít nhất hai bằng chứng đã xác nhận.
        if evidence_count >= 2 and top_cf >= 0.75 and gap >= 0.20:
            return True

        # Nếu đã hỏi 3-4 câu rồi và top fault tương đối chắc thì dừng
        question_count = getattr(memory, "question_count", 0)
        if question_count >= 4 and top_cf >= 0.60:
            return True

        return False

    def _unknown_response(
        self,
        text: str,
        matched_symptoms: list[dict[str, Any]],
        memory: WorkingMemory,
    ) -> dict[str, Any]:
        trace = self.explanations.build(
            user_input=text,
            matched_symptoms=matched_symptoms,
            memory=memory,
            diagnoses=[],
            next_question=None,
            status="unknown_symptom",
        )
        return {
            "matched_symptoms": matched_symptoms,
            "diagnoses": [],
            "results": [],
            "current_hypotheses": [],
            "candidate_faults": [],
            "next_question": None,
            "reasoning_trace": trace,
            "status": "unknown_symptom",
            "is_final": False,
            "tree_level": "symptom",
            "explanation_summary": "Cơ sở tri thức chưa ánh xạ được triệu chứng đã mô tả.",
            "source": "staging_files_kg",
            "procedure_terminal": None,
            **memory.to_response_fields(),
        }

    def _llm_fallback_response(
        self,
        text: str,
        matched_symptoms: list[dict[str, Any]],
        memory: WorkingMemory,
        top_k: int,
    ) -> dict[str, Any]:
        fallback = diagnose_with_llm(text, top_k=top_k)
        diagnoses = fallback.get("diagnoses", [])
        missing_questions = (
            fallback.get("diagnostic_tree", {})
            .get("level_3_context", {})
            .get("missing_questions", [])
        )
        return {
            "matched_symptoms": matched_symptoms,
            "candidate_faults": [],
            "status": "need_more_info",
            "is_final": False,
            "source": "llm_fallback",
            "results": [],
            "diagnoses": [],
            "current_hypotheses": [],
            "llm_suggestions": diagnoses,
            "next_question": {
                "question": missing_questions[0]
                if missing_questions
                else "Mình chưa có triệu chứng này trong hệ thống. Triệu chứng thường xảy ra khi nào?",
                "type": "multiple_choice",
                "mode": "llm_fallback",
                "choices": [
                    {"value": "startup", "label": "Lúc khởi động"},
                    {"value": "accelerating", "label": "Khi tăng tốc"},
                    {"value": "idle", "label": "Khi chạy không tải"},
                    {"value": "high_speed", "label": "Ở tốc độ cao"},
                    {"value": "not_sure", "label": "Không chắc"},
                ],
                "why": "Cần thêm context trước khi chuyên gia thêm mapping mới vào Knowledge Graph.",
            },
            "notes": ["Triệu chứng đã được đưa vào hàng chờ chuyên gia; chưa có kết luận cuối."],
            "queued_for_review": fallback.get("queued_for_review", False),
            "reasoning_trace": [
                "Không tìm thấy triệu chứng phù hợp trong knowledge base.",
                "Đã đưa case vào hàng chờ chuyên gia.",
                "Không hiển thị candidate LLM như kết luận chẩn đoán.",
            ],
            "tree_level": "symptom",
            "explanation_summary": "Triệu chứng chưa có trong cơ sở tri thức; cần thêm thông tin và chuyên gia duyệt.",
            "debug": {
                "fallback_notes": fallback.get("notes", []),
                "raw_fallback": fallback,
            },
            "procedure_terminal": None,
            **memory.to_response_fields(),
        }

    def _select_primary_symptom(self, confirmed_symptoms: list[str]) -> str | None:
        if not confirmed_symptoms:
            return None
        best = confirmed_symptoms[0]
        best_priority = 999
        for symptom_id in confirmed_symptoms:
            for rule in self.kb.get_rules_for_symptom(symptom_id):
                if rule.get("symptom") == symptom_id:
                    return symptom_id
                for symptom in rule.get("symptoms", []):
                    if symptom.get("symptom_id") == symptom_id and int(symptom.get("priority", 2)) < best_priority:
                        best = symptom_id
                        best_priority = int(symptom.get("priority", 2))
        return best

    def _detect_systems(self, confirmed_symptoms: list[str]) -> list[str]:
        systems = {
            rule.get("system_id") or rule.get("system")
            for symptom_id in confirmed_symptoms
            for rule in self.kb.get_rules_for_symptom(symptom_id)
            if rule.get("system_id") or rule.get("system")
        }
        return sorted(systems)

    def _candidate_rules(self, memory: WorkingMemory) -> list[dict[str, Any]]:
        if memory.primary_symptom:
            for system_id in memory.detected_systems or [None]:
                candidates = self.kb.get_candidate_faults(system_id, memory.primary_symptom)
                if candidates:
                    return candidates
        return self.kb.rules_for_symptoms(memory.confirmed_symptoms)

    def _rank(
        self,
        candidate_rules: list[dict[str, Any]],
        confirmed_symptoms: list[str],
        rejected_symptoms: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        ranked = _rank_faults_impl(confirmed_symptoms, rejected_symptoms, candidate_rules, self.kb)[:top_k]
        for diagnosis in ranked:
            for rule in diagnosis.get("matched_rules", []):
                symptom_id = rule.get("symptom_id")
                rule["symptom_label"] = self.kb.label_for_symptom(symptom_id) if symptom_id else None
        return ranked

    def _select_next_step(
        self,
        memory: WorkingMemory,
        diagnoses: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str | None]:
        if memory.question_count >= self.max_questions:
            return None, "MAX_QUESTIONS_REACHED"

        if not diagnoses:
            return _select_ig_question(memory, diagnoses, self.kb, self.max_questions), None

        rejected_faults = set(getattr(memory, "rejected_faults", []) or [])

        top = next(
            (d for d in diagnoses if d.get("fault_id") not in rejected_faults),
            diagnoses[0],
        )

        procedure = self.kb.get_procedure_for_fault(top.get("fault_id"))
        if procedure:
            step = self._next_procedure_step(procedure, memory)

            if step:
                terminal = step.get("terminal")
                if terminal == "DIAGNOSED":
                    next_ig = _select_ig_question(memory, diagnoses, self.kb, self.max_questions)
                    if next_ig:
                        return next_ig, None
                    return None, terminal
                if terminal:
                    return _select_ig_question(memory, diagnoses, self.kb, self.max_questions), terminal
                return self._procedure_question(step, top), None

        return _select_ig_question(memory, diagnoses, self.kb, self.max_questions), None

    def _next_procedure_step(
        self,
        procedure: dict[str, Any],
        memory: WorkingMemory,
    ) -> dict[str, Any] | None:
        visited = set(memory.step_history or [])
        if memory.current_step_id:
            step = self.procedure_runner.get_next_from_tree(
                memory.current_step_id,
                memory.last_answer,
                procedure,
                visited=visited,
                max_depth=self.max_questions,
            )
        else:
            step = self.procedure_runner.entry_step(procedure)

        return self._skip_answered_procedure_steps(step, procedure, memory, visited)

    def _skip_answered_procedure_steps(
        self,
        step: dict[str, Any] | None,
        procedure: dict[str, Any],
        memory: WorkingMemory,
        visited: set[str],
    ) -> dict[str, Any] | None:
        confirmed = set(memory.confirmed_symptoms or [])
        rejected = set(memory.rejected_symptoms or [])

        while step and not step.get("terminal"):
            symptom_id = step.get("symptom_id")
            if symptom_id not in confirmed and symptom_id not in rejected:
                return step

            step_id = step.get("step_id")
            if not step_id or step_id in visited or len(visited) >= self.max_questions:
                return {"terminal": "END", "step_id": step_id, "error": "loop_detected"}

            visited.add(step_id)
            step = self.procedure_runner.get_next_from_tree(
                step_id,
                symptom_id in confirmed,
                procedure,
                visited=visited,
                max_depth=self.max_questions,
            )
        return step

    def _procedure_question(self, step: dict[str, Any], top: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": step.get("question"),
            "step_id": step.get("step_id"),
            "symptom": step.get("symptom_id"),
            "symptom_id": step.get("symptom_id"),
            "label": step.get("symptom_label"),
            "mode": "procedure_tree",
            "results": step.get("results", []),
            "fault_preview": {
                "fault_id": top.get("fault_id"),
                "fault_name": top.get("fault_name"),
                "score": top.get("score"),
                "final_cf": top.get("final_cf"),
            },
            "explanation": "Được chọn từ quy trình kiểm tra của giả thuyết lỗi mạnh nhất hiện tại.",
        }

    def _tree_level(self, status: str, next_question: dict[str, Any] | None) -> str:
        if status == "diagnosed":
            return "confirmation"
        if next_question and next_question.get("mode") == "procedure_tree":
            return "procedure"
        if next_question:
            return "secondary_symptom"
        return "fault"

    @staticmethod
    def _candidate_faults_payload(diagnoses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "fault_id": item.get("fault_id"),
                "fault_name": item.get("fault_name"),
                "fault_label": item.get("fault_label"),
                "system": item.get("system"),
                "final_cf": item.get("final_cf"),
                "confidence_label": item.get("confidence_label"),
            }
            for item in diagnoses
        ]

    # Keep these as static methods for backward compatibility
    @staticmethod
    def _combine_cf(cf_old: float, cf_new: float) -> float:
        return combine_cf(cf_old, cf_new)

    @staticmethod
    def _confidence_label(score: float) -> str:
        return confidence_label(score)

    # Keep _select_by_information_gain as static method for backward compatibility
    @staticmethod
    def _select_by_information_gain(
        ranked: list[dict[str, Any]],
        asked: set[str],
        all_symptoms: list[str],
        cf_map: dict[str, dict[str, float]],
    ) -> dict[str, Any] | None:
        return _select_by_information_gain(ranked, asked, all_symptoms, cf_map)


# ============================================================================
# Public API for backward compatibility and tests
# ============================================================================

def rank_faults(
    confirmed_symptoms: list[str],
    rejected_symptoms: list[str],
    cf_map: dict[str, dict[str, float]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Rank fault hypotheses using MYCIN-style certainty factors.
    Backward compatibility wrapper around the new certainty module.
    """
    confirmed = set(confirmed_symptoms or [])
    rejected = set(rejected_symptoms or [])
    ranked = []

    for rule in rules:
        fault_id = rule.get("fault_id")
        if not fault_id:
            continue

        score = 0.0
        breakdown = []
        matched_rules = []
        for symptom in rule.get("symptoms", []):
            symptom_id = symptom.get("symptom_id")
            if not symptom_id:
                continue
            cf = float(cf_map.get(symptom_id, {}).get(fault_id, symptom.get("cf", 0.5)))
            if symptom_id in confirmed:
                score = combine_cf(score, cf)
                breakdown.append({"symptom": symptom_id, "cf": cf, "direction": "confirmed"})
                matched_rules.append({**symptom, "symptom_name": symptom_id, "cf": cf})
            elif symptom_id in rejected:
                score *= max(0.0, 1 - cf)
                breakdown.append({"symptom": symptom_id, "cf": cf, "direction": "rejected"})

        if not matched_rules and confirmed and not rule.get("candidate_reason"):
            continue

        final_cf = round(min(max(score, 0.0), 1.0), 4)
        ranked.append(
            {
                "fault_id": fault_id,
                "fault_name": rule.get("fault_name", fault_id),
                "fault_label": rule.get("label_vi") or rule.get("display_name", rule.get("fault_name", fault_id)),
                "system": rule.get("system_id") or rule.get("system"),
                "subsystem": rule.get("subsystem_id") or rule.get("subsystem"),
                "score": final_cf,
                "final_cf": final_cf,
                "cf_breakdown": breakdown,
                "score_breakdown": {
                    "cf_confidence": final_cf,
                    "note": "Điểm tin cậy Certainty Factor, không phải xác suất Bayes.",
                },
                "confidence_label": confidence_label(final_cf),
                "decision": "accepted" if final_cf >= 0.5 else "uncertain",
                "candidate_reason": rule.get("candidate_reason"),
                "matched_rules": matched_rules,
                "repairs": rule.get("repairs", []),
                "resolution": rule.get("resolution"),
            }
        )

    return sorted(ranked, key=lambda item: item["final_cf"], reverse=True)


# Alias for backward compatibility
InferenceEngine = ExpertSystemEngine
