from __future__ import annotations

import math
from typing import Any

from src.expert_system import knowledge_base
from src.expert_system.knowledge_base import KnowledgeBase
from src.expert_system.procedure import ProcedureRunner as ProcedureReasoner
from src.expert_system.engine import WorkingMemory


def select_by_information_gain(
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


class QuestionSelector:
    """Choose the next expert-system question."""

    def __init__(self, kb: KnowledgeBase, procedure_reasoner: ProcedureReasoner | None = None):
        self.kb = kb
        self.procedure_reasoner = procedure_reasoner or ProcedureReasoner()

    def select(self, hypotheses, memory, knowledge_base):
        procedure_question = self.procedure_reasoner.next_question(
            hypotheses=hypotheses,
            memory=memory,
            knowledge_base=knowledge_base,
        )

        if procedure_question:
            procedure_question["mode"] = "procedure_tree"
            return procedure_question

        ig_question = self._select_information_gain_question(
            hypotheses=hypotheses,
            memory=memory,
            knowledge_base=knowledge_base,
        )

        if ig_question:
            ig_question["mode"] = "information_gain"
            return ig_question

        return None

    def _procedure_question(
        self,
        memory: WorkingMemory,
        top: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not top or float(top.get("final_cf", top.get("score", 0))) < 0.60:
            return None
        fault_id = top.get("fault_id")
        procedure = self.kb.get_procedure_for_fault(fault_id)
        if not procedure:
            return None

        if memory.current_step_id:
            step = self.procedure_reasoner.get_next_from_tree(
                memory.current_step_id,
                memory.last_answer,
                procedure,
            )
        else:
            step = self.procedure_reasoner.entry_step(procedure)

        if not step:
            return None
        if step.get("terminal"):
            return {"done": True, "terminal": step.get("terminal"), "mode": "procedure_tree"}
        return self._tree_question(step, top)

    def _information_gain_question(
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
        result = select_by_information_gain(ranked, asked, all_symptoms, self.kb.cf_map)
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

    def _tree_question(self, step: dict[str, Any], top: dict[str, Any]) -> dict[str, Any]:
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


def get_next_question(
    session: dict[str, Any] | list[dict[str, Any]],
    ranked: list[dict[str, Any]] | list[str],
    cf_map: dict[str, dict[str, float]] | None = None,
    kg_rules: list[dict[str, Any]] | None = None,
    **legacy_kwargs: Any,
) -> dict[str, Any] | None:
    from src.expert_system.knowledge_base import KnowledgeBase

    if isinstance(session, list):
        diagnoses = session
        confirmed = ranked if isinstance(ranked, list) else []
        rules = legacy_kwargs.get("rules") or kg_rules or []
        kb = KnowledgeBase.from_data(
            symptom_aliases=legacy_kwargs.get("symptom_metadata") or {},
            rules=rules,
        )
        kb.cf_map = cf_map or kb.cf_map
        memory = WorkingMemory(confirmed_symptoms=list(confirmed))
        return QuestionSelector(kb).select(memory, diagnoses)

    rules = kg_rules or []
    kb = KnowledgeBase.from_data(
        symptom_aliases=legacy_kwargs.get("symptom_metadata") or {},
        rules=rules,
    )
    kb.cf_map = cf_map or kb.cf_map
    memory = WorkingMemory.from_session(session or {})
    return QuestionSelector(kb).select(memory, ranked if isinstance(ranked, list) else [])
