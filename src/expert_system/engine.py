from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from src.expert_system.knowledge_base import KnowledgeBase
from src.expert_system.llm_fallback import diagnose_with_llm
from src.expert_system.procedure import ProcedureRunner
from src.expert_system.matcher import SymptomMatcher


# ============================================================================
# WorkingMemory — Manage diagnosis session state
# ============================================================================

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
    rejected_faults: list[str] = field(default_factory=list)

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
        asked_items = set(session.get("step_history") or []) | set((session.get("answers") or {}).keys())
        return cls(
            confirmed_symptoms=list(session.get("confirmed_symptoms") or []),
            rejected_symptoms=list(session.get("rejected_symptoms") or []),
            rejected_faults=list(session.get("rejected_faults") or []),  # thêm dòng này
            current_hypotheses=list(session.get("current_hypotheses") or []),
            active_fault_id=session.get("active_fault_id"),
            current_step_id=session.get("current_step_id"),
            branch_path=list(session.get("branch_path") or []),
            step_history=list(session.get("step_history") or []),
            question_count=len(asked_items),
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
            "rejected_faults": sorted(set(self.rejected_faults)),
            "detected_systems": self.detected_systems,
            "primary_symptom": self.primary_symptom,
            "confirmed_context": sorted(set(self.confirmed_symptoms) - ({self.primary_symptom} if self.primary_symptom else set())),
            "rejected_context": sorted(set(self.rejected_symptoms)),
            "active_fault_path": self.branch_path,
        }


# ============================================================================
# ExplanationBuilder — Build human and machine-readable reasoning details
# ============================================================================

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
            return "Không có lỗi nào trong cơ sở tri thức khớp với các triệu chứng đã xác nhận."
        top = diagnoses[0]
        system = self.kb.system_label(top.get("system")) or top.get("system") or "Hệ thống chưa rõ"
        primary = self.kb.label_for_symptom(memory.primary_symptom) if memory.primary_symptom else "triệu chứng đã mô tả"
        return (
            f"{system} > {primary} > {top.get('fault_label', top.get('fault_name'))} "
            f"với CF {top.get('final_cf')}. Trạng thái: {status}."
        )

    def _question_selection(self, next_question: dict[str, Any] | None) -> dict[str, Any]:
        if not next_question or next_question.get("done"):
            return {
                "status": "not_selected",
                "explanation": "Không còn câu hỏi bổ sung hữu ích.",
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
            "rule_text": f"NẾU {' VÀ '.join(symptoms) if symptoms else 'chưa có triệu chứng khớp'} THÌ {diagnosis.get('fault_label', diagnosis['fault_name'])}",
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
                    "formula": "cf_kết_hợp = cf_cũ + cf_bằng_chứng * (1 - cf_cũ)",
                    "explanation": "Triệu chứng đã xác nhận làm tăng độ tin cậy của lỗi theo hệ số chắc chắn trong luật.",
                }
            )
        steps.append(
            {
                "fault_id": diagnosis["fault_id"],
                "fault_label": diagnosis.get("fault_label"),
                "formula": "cf_cuối là điểm tin cậy có giới hạn, không phải xác suất Bayes.",
                "score_breakdown": diagnosis.get("score_breakdown", {}),
            }
        )
        return steps


# ============================================================================
# ExpertSystemEngine — Main orchestrator
# ============================================================================

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
        from src.expert_system.schemas import DiagnosisResponse

        matched_symptoms = self.matcher.match(text)
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

        if not memory.confirmed_symptoms:
            return self._llm_fallback_response(text, matched_symptoms, memory, top_k)

        memory.primary_symptom = self._select_primary_symptom(memory.confirmed_symptoms)
        memory.detected_systems = self._detect_systems(memory.confirmed_symptoms)
        candidate_rules = self._candidate_rules(memory)
        diagnoses = self._rank(candidate_rules, memory.confirmed_symptoms, memory.rejected_symptoms, top_k)
        if not diagnoses:
            return self._llm_fallback_response(text, matched_symptoms, memory, top_k)

        # Stop early when the top diagnosis is confident enough.
        if self._confident_enough(diagnoses, memory):
            next_question = None
            procedure_terminal = "DIAGNOSED"
        else:
            next_question, procedure_terminal = self._select_next_step(memory, diagnoses)

        memory.current_hypotheses = diagnoses
        memory.active_fault_id = diagnoses[0]["fault_id"] if diagnoses else None

        if procedure_terminal and procedure_terminal != "DIAGNOSED" and not next_question:
            next_question = self._select_information_gain_question(memory, diagnoses)

        if procedure_terminal == "DIAGNOSED" or (diagnoses and not next_question):
            status = "diagnosed"
            next_question = None
        elif next_question:
            status = "need_more_info"
        else:
            status = "unknown_symptom"

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
        ranked = self._rank_faults(confirmed_symptoms, rejected_symptoms, candidate_rules)[:top_k]
        for diagnosis in ranked:
            for rule in diagnosis.get("matched_rules", []):
                symptom_id = rule.get("symptom_id")
                rule["symptom_label"] = self.kb.label_for_symptom(symptom_id) if symptom_id else None
        return ranked
    
    def _related_symptoms(self, symptom_id: str) -> set[str]:
        label = (self.kb.label_for_symptom(symptom_id) or symptom_id).lower()

        groups = [
            ("warning_light", ["warning", "light", "đèn", "cảnh báo", "abs"]),
            ("noise", ["noise", "tiếng", "kêu", "ồn"]),
            ("leak", ["leak", "rò", "rỉ", "chảy"]),
            ("overheat", ["overheat", "quá nhiệt", "nhiệt"]),
            ("vibration", ["vibration", "rung"]),
        ]

        active_group = None
        for group_name, keywords in groups:
            if any(k in label or k in symptom_id.lower() for k in keywords):
                active_group = keywords
                break

        if not active_group:
            return {symptom_id}

        related = {symptom_id}
        for rule in self.kb.rules:
            for symptom in rule.get("symptoms", []):
                sid = symptom.get("symptom_id")
                slabel = (self.kb.label_for_symptom(sid) or sid or "").lower()
                if sid and any(k in slabel or k in sid.lower() for k in active_group):
                    related.add(sid)

        return related

    def _rank_faults(
        self,
        confirmed_symptoms: list[str],
        rejected_symptoms: list[str],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
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
                cf = float(self.kb.cf_map.get(symptom_id, {}).get(fault_id, symptom.get("cf", 0.5)))
                if symptom_id in confirmed:
                    score = self._combine_cf(score, cf)
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
                    "fault_label": self.kb.label_for_fault(rule, fault_id),
                    "system": rule.get("system_id") or rule.get("system"),
                    "subsystem": rule.get("subsystem_id") or rule.get("subsystem"),
                    "score": final_cf,
                    "final_cf": final_cf,
                    "cf_breakdown": breakdown,
                    "score_breakdown": {
                        "cf_confidence": final_cf,
                        "note": "Điểm tin cậy Certainty Factor, không phải xác suất Bayes.",
                    },
                    "confidence_label": self._confidence_label(final_cf),
                    "decision": "accepted" if final_cf >= 0.5 else "uncertain",
                    "candidate_reason": rule.get("candidate_reason"),
                    "matched_rules": matched_rules,
                    "repairs": rule.get("repairs", []),
                    "resolution": rule.get("resolution"),
                }
            )

        return sorted(ranked, key=lambda item: item["final_cf"], reverse=True)

    def _select_next_step(
        self,
        memory: WorkingMemory,
        diagnoses: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str | None]:
        if memory.question_count >= self.max_questions:
            return None, "MAX_QUESTIONS_REACHED"

        if not diagnoses:
            return self._select_information_gain_question(memory, diagnoses), None

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
                    next_ig = self._select_information_gain_question(memory, diagnoses)
                    if next_ig:
                        return next_ig, None
                    return None, terminal
                if terminal:
                    return self._select_information_gain_question(memory, diagnoses), terminal
                return self._procedure_question(step, top), None

        return self._select_information_gain_question(memory, diagnoses), None

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
    
    def _symptom_question(self, symptom_id: str, label: str | None) -> str:
        label = (label or symptom_id).strip()
        text = f"{symptom_id} {label}".lower()

        patterns = [
            (("leak", "rò rỉ", "chảy"), f"Bạn có thấy dấu hiệu rò rỉ liên quan đến {label.lower()} không?"),
            (("noise", "tiếng", "kêu", "grinding"), f"Bạn có nghe thấy {label.lower()} không?"),
            (("smoke", "khói"), f"Bạn có thấy {label.lower()} không?"),
            (("warning", "light", "đèn"), f"Có cảnh báo hoặc đèn báo liên quan đến {label.lower()} không?"),
            (("vibration", "rung"), f"Xe có bị {label.lower()} không?"),
            (("temperature", "nhiệt", "overheat"), f"Nhiệt độ động cơ có biểu hiện {label.lower()} không?"),
            (("level", "mức"), f"Mức chất lỏng/dầu/nước có biểu hiện {label.lower()} không?"),
        ]

        for keywords, question in patterns:
            if any(key in text for key in keywords):
                return question

        return f"Bạn có nhận thấy dấu hiệu này không: {label.lower()}?"

    def _select_information_gain_question(
        self,
        memory: WorkingMemory,
        ranked: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if memory.question_count >= self.max_questions:
            return None

        top_ranked = ranked[:3]
        candidate_fault_ids = {
            diagnosis.get("fault_id")
            for diagnosis in top_ranked
            if diagnosis.get("fault_id")
        }
        all_symptoms = [
            symptom.get("symptom_id")
            for rule in self.kb.rules
            if rule.get("fault_id") in candidate_fault_ids
            for symptom in rule.get("symptoms", [])
            if symptom.get("symptom_id")
        ]
        if not all_symptoms:
            all_symptoms = [
                symptom.get("symptom_id")
                for rule in self.kb.rules_for_symptoms(memory.confirmed_symptoms)
                for symptom in rule.get("symptoms", [])
                if symptom.get("symptom_id")
            ]
        asked = (
            set(memory.confirmed_symptoms)
            | set(memory.rejected_symptoms)
            | set(memory.step_history or [])
        )

        # Chặn hỏi lại các symptom cùng nhóm với primary symptom
        if memory.primary_symptom:
            asked |= self._related_symptoms(memory.primary_symptom)
        result = self._select_by_information_gain(ranked, asked, all_symptoms, self.kb.cf_map)
        if not result:
            return None
        symptom_id = result["symptom_id"]
        label = self.kb.label_for_symptom(symptom_id)
        return {
            "symptom": symptom_id,
            "symptom_id": symptom_id,
            "label": label,
            "question": self._symptom_question(symptom_id, label),
            "step_id": None,
            "mode": "information_gain",
            "information_gain": result["information_gain"],
            "fault_preview": None,
            "explanation": "Được chọn vì đây là triệu chứng chưa hỏi giúp phân biệt tốt nhất giữa các giả thuyết lỗi.",
        }

    @staticmethod
    def _select_by_information_gain(
        ranked: list[dict[str, Any]],
        asked: set[str],
        all_symptoms: list[str],
        cf_map: dict[str, dict[str, float]],
    ) -> dict[str, Any] | None:
        def entropy(distribution: list[dict[str, Any]]) -> float:
            total = sum(float(item.get("final_cf", item.get("score", 0))) for item in distribution) or 1.0
            value = 0.0
            for item in distribution:
                probability = float(item.get("final_cf", item.get("score", 0))) / total
                if probability > 0:
                    value -= probability * math.log2(probability + 1e-9)
            return value

        current_entropy = entropy(ranked)
        best_ig = -1.0
        best_symptom = None
        for symptom_id in sorted(set(all_symptoms)):
            if symptom_id in asked:
                continue
            yes_ranked = [
                {
                    **fault,
                    "score": float(fault.get("final_cf", fault.get("score", 0)))
                    * float(cf_map.get(symptom_id, {}).get(fault.get("fault_id"), 0.01)),
                }
                for fault in ranked
            ]
            no_ranked = [
                {
                    **fault,
                    "score": float(fault.get("final_cf", fault.get("score", 0)))
                    * (1 - float(cf_map.get(symptom_id, {}).get(fault.get("fault_id"), 0.01))),
                }
                for fault in ranked
            ]
            total = sum(float(fault.get("final_cf", fault.get("score", 0))) for fault in ranked) or 1.0
            p_yes = min(max(sum(float(fault.get("score", 0)) for fault in yes_ranked) / total, 0.0), 1.0)
            p_no = 1 - p_yes
            ig = current_entropy - (p_yes * entropy(yes_ranked) + p_no * entropy(no_ranked))
            if ig > best_ig:
                best_ig = ig
                best_symptom = symptom_id

        if not best_symptom:
            return None
        return {"symptom_id": best_symptom, "information_gain": round(best_ig, 4)}

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

    @staticmethod
    def _combine_cf(cf_old: float, cf_new: float) -> float:
        return cf_old + cf_new * (1 - cf_old)

    @staticmethod
    def _confidence_label(score: float) -> str:
        if score >= 0.8:
            return "Rất có khả năng"
        if score >= 0.6:
            return "Có khả năng"
        if score >= 0.4:
            return "Có thể xảy ra"
        return "Chưa chắc chắn"


# ============================================================================
# Public API for backward compatibility and tests
# ============================================================================

def load_cf_map(kg_rules: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Build a symptom→fault certainty factor map from knowledge rules."""
    cf_map: dict[str, dict[str, float]] = {}
    for rule in kg_rules:
        fault_id = rule.get("fault_id")
        for symptom in rule.get("symptoms", []):
            symptom_id = symptom.get("symptom_id")
            if symptom_id and fault_id:
                cf_map.setdefault(symptom_id, {})[fault_id] = float(symptom.get("cf", 0.5))
    return cf_map


def rank_faults(
    confirmed_symptoms: list[str],
    rejected_symptoms: list[str],
    cf_map: dict[str, dict[str, float]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Rank fault hypotheses using MYCIN-style certainty factors.
    Backward compatibility wrapper around ExpertSystemEngine._rank_faults.
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
                score = ExpertSystemEngine._combine_cf(score, cf)
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
                "confidence_label": ExpertSystemEngine._confidence_label(final_cf),
                "decision": "accepted" if final_cf >= 0.5 else "uncertain",
                "candidate_reason": rule.get("candidate_reason"),
                "matched_rules": matched_rules,
                "repairs": rule.get("repairs", []),
                "resolution": rule.get("resolution"),
            }
        )

    return sorted(ranked, key=lambda item: item["final_cf"], reverse=True)
