from __future__ import annotations

import math
from typing import Any

from src.expert_system.explanation import ExplanationBuilder
from src.expert_system.knowledge_base import KnowledgeBase
from src.expert_system.models import DiagnosisResponse
from src.expert_system.procedure_runner import ProcedureRunner
from src.expert_system.symptom_matcher import SymptomMatcher
from src.expert_system.working_memory import WorkingMemory


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
        diagnoses = self._rank(candidate_rules, memory.confirmed_symptoms, memory.rejected_symptoms, top_k)
        memory.current_hypotheses = diagnoses
        memory.active_fault_id = diagnoses[0]["fault_id"] if diagnoses else None

        next_question, procedure_terminal = self._select_next_step(memory, diagnoses)
        if procedure_terminal and procedure_terminal != "DIAGNOSED" and not next_question:
            next_question = self._select_information_gain_question(memory, diagnoses)

        if procedure_terminal == "DIAGNOSED":
            status = "diagnosed"
            next_question = None
        else:
            status = "need_more_info"

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
                    "fault_label": rule.get("display_name", rule.get("fault_name", fault_id)),
                    "system": rule.get("system_id") or rule.get("system"),
                    "subsystem": rule.get("subsystem_id") or rule.get("subsystem"),
                    "score": final_cf,
                    "final_cf": final_cf,
                    "cf_breakdown": breakdown,
                    "score_breakdown": {
                        "cf_confidence": final_cf,
                        "note": "Certainty Factor confidence score, not Bayesian probability.",
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
        if not diagnoses:
            return self._select_information_gain_question(memory, diagnoses), None

        top = diagnoses[0]
        procedure = self.kb.get_procedure_for_fault(top.get("fault_id"))
        if procedure:
            if memory.current_step_id:
                step = self.procedure_runner.get_next_from_tree(
                    memory.current_step_id,
                    memory.last_answer,
                    procedure,
                )
            else:
                step = self.procedure_runner.entry_step(procedure)

            if step:
                terminal = step.get("terminal")
                if terminal == "DIAGNOSED":
                    return None, terminal
                if terminal:
                    return self._select_information_gain_question(memory, diagnoses), terminal
                return self._procedure_question(step, top), None

        return self._select_information_gain_question(memory, diagnoses), None

    def _select_information_gain_question(
        self,
        memory: WorkingMemory,
        ranked: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        all_symptoms = [
            symptom.get("symptom_id")
            for rule in self.kb.rules
            for symptom in rule.get("symptoms", [])
            if symptom.get("symptom_id")
        ]
        asked = set(memory.confirmed_symptoms) | set(memory.rejected_symptoms)
        result = self._select_by_information_gain(ranked, asked, all_symptoms, self.kb.cf_map)
        if not result:
            return None
        symptom_id = result["symptom_id"]
        label = self.kb.label_for_symptom(symptom_id)
        return {
            "symptom": symptom_id,
            "symptom_id": symptom_id,
            "label": label,
            "question": f"Do you also notice {label.lower()}?",
            "step_id": None,
            "mode": "information_gain",
            "information_gain": result["information_gain"],
            "fault_preview": None,
            "explanation": "Selected as the best unasked symptom to separate competing fault hypotheses.",
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
            "mode": "procedure_tree",
            "results": step.get("results", []),
            "fault_preview": {
                "fault_id": top.get("fault_id"),
                "fault_name": top.get("fault_name"),
                "score": top.get("score"),
                "final_cf": top.get("final_cf"),
            },
            "explanation": "Selected from the diagnostic procedure for the strongest active hypothesis.",
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
            return "Very likely"
        if score >= 0.6:
            return "Likely"
        if score >= 0.4:
            return "Possible"
        return "Uncertain"


# Public API for backward compatibility and tests
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
                "fault_label": rule.get("display_name", rule.get("fault_name", fault_id)),
                "system": rule.get("system_id") or rule.get("system"),
                "subsystem": rule.get("subsystem_id") or rule.get("subsystem"),
                "score": final_cf,
                "final_cf": final_cf,
                "cf_breakdown": breakdown,
                "score_breakdown": {
                    "cf_confidence": final_cf,
                    "note": "Certainty Factor confidence score, not Bayesian probability.",
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
