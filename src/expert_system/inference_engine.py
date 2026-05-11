from __future__ import annotations

from typing import Any

from src.expert_system.cf_reasoner import CFReasoner
from src.expert_system.explanation import ExplanationBuilder
from src.expert_system.knowledge_base import KnowledgeBase
from src.expert_system.question_selector import QuestionSelector
from src.expert_system.symptom_matcher import SymptomMatcher
from src.expert_system.working_memory import WorkingMemory


class ExpertSystemEngine:
    """Orchestrates the hierarchical automotive diagnosis expert system."""

    def __init__(self, kb: KnowledgeBase | None = None, max_questions: int = 8):
        self.kb = kb or KnowledgeBase.from_staging()
        self.matcher = SymptomMatcher(self.kb.symptom_aliases)
        self.cf_reasoner = CFReasoner(self.kb.cf_map)
        self.question_selector = QuestionSelector(self.kb)
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
            return self._unknown_response(text, matched_symptoms, memory)

        memory.primary_symptom = self._select_primary_symptom(memory.confirmed_symptoms)
        memory.detected_systems = self._detect_systems(memory.confirmed_symptoms)
        candidate_rules = self._candidate_rules(memory)
        diagnoses = self._rank(candidate_rules, memory, top_k)
        memory.current_hypotheses = diagnoses
        memory.active_fault_id = diagnoses[0]["fault_id"] if diagnoses else None

        next_question = self.question_selector.select(memory, diagnoses) if diagnoses else None
        terminal = (next_question or {}).get("terminal")
        max_questions_reached = memory.question_count >= self.max_questions
        deterministic_match = self._has_deterministic_match(diagnoses, memory.confirmed_symptoms)
        should_diagnose = self.cf_reasoner.should_diagnose(
            diagnoses,
            has_useful_question=bool(next_question and not next_question.get("done")),
            procedure_terminal=terminal,
            max_questions_reached=max_questions_reached,
            confirmed_symptom_count=len(memory.confirmed_symptoms),
            question_count=memory.question_count,
            deterministic_match=deterministic_match,
        )
        if not diagnoses:
            status = "no_fault_found"
        elif should_diagnose:
            status = "diagnosed"
        else:
            status = "need_more_info"

        if status == "diagnosed":
            next_question = None

        results = diagnoses if status == "diagnosed" else []
        trace = self.explanations.build(
            user_input=text,
            matched_symptoms=matched_symptoms,
            memory=memory,
            diagnoses=diagnoses,
            next_question=next_question,
            status=status,
        )
        response = {
            "matched_symptoms": matched_symptoms,
            "diagnoses": diagnoses,
            "results": results,
            "current_hypotheses": diagnoses,
            "candidate_faults": self._candidate_faults_payload(diagnoses),
            "next_question": next_question,
            "reasoning_trace": trace,
            "status": status,
            "is_final": status == "diagnosed",
            "tree_level": self._tree_level(status, next_question),
            "explanation_summary": self.explanations.summary(memory, diagnoses, status),
            "source": "staging_files_kg",
            **memory.to_response_fields(),
        }
        if status == "diagnosed" and diagnoses:
            response["resolution"] = diagnoses[0].get("resolution")
        return response

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
            "explanation_summary": "The Knowledge Base could not map the reported symptom.",
            "source": "staging_files_kg",
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
        memory: WorkingMemory,
        top_k: int,
    ) -> list[dict[str, Any]]:
        ranked = self.cf_reasoner.rank(
            memory.confirmed_symptoms,
            memory.rejected_symptoms,
            candidate_rules,
            top_k,
        )
        for diagnosis in ranked:
            for rule in diagnosis.get("matched_rules", []):
                symptom_id = rule.get("symptom_id")
                rule["symptom_label"] = self.kb.label_for_symptom(symptom_id) if symptom_id else None
        return ranked

    def _has_deterministic_match(self, diagnoses: list[dict[str, Any]], confirmed_symptoms: list[str]) -> bool:
        if not diagnoses:
            return False
        top_fault = self.kb.get_fault(diagnoses[0].get("fault_id")) or {}
        if top_fault.get("deterministic"):
            return True
        confirmed = set(confirmed_symptoms)
        for symptom in top_fault.get("symptoms", []):
            if symptom.get("symptom_id") in confirmed and symptom.get("deterministic"):
                return True
        return False

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

    def _tree_level(self, status: str, next_question: dict[str, Any] | None) -> str:
        if status == "diagnosed":
            return "confirmation"
        if next_question and next_question.get("mode") == "procedure_tree":
            return "procedure"
        if next_question:
            return "secondary_symptom"
        return "fault"
