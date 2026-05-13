"""
certainty — MYCIN-style certainty factor scoring and fault ranking.

Ranks fault hypotheses by combining confirmed/rejected symptom
evidence using the incremental CF combination formula.
Produces a sorted list of candidate diagnoses with scores,
breakdowns, and confidence labels.
"""
from __future__ import annotations

from typing import Any

from src.expert_system.knowledge.loader import KnowledgeBase
from src.expert_system.utils.scoring import combine_cf, confidence_label


def rank_faults(
    confirmed_symptoms: list[str],
    rejected_symptoms: list[str],
    rules: list[dict[str, Any]],
    kb: KnowledgeBase,
) -> list[dict[str, Any]]:
    """
    Rank fault hypotheses using MYCIN-style certainty factors.

    Each confirmed symptom increases the CF score via the combination
    formula; each rejected symptom reduces it proportionally.
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
            cf = float(kb.cf_map.get(symptom_id, {}).get(fault_id, symptom.get("cf", 0.5)))
            if symptom_id in confirmed:
                score = combine_cf(score, cf)
                breakdown.append({"symptom": symptom_id, "cf": cf, "direction": "confirmed"})
                matched_rules.append({**symptom, "symptom_name": symptom_id, "cf": cf})
            elif symptom_id in rejected:
                score *= max(0.0, 1 - cf)
                breakdown.append({"symptom": symptom_id, "cf": cf, "direction": "rejected"})

        if not matched_rules and confirmed and not rule.get("candidate_reason"):
            continue

        confidence = round(min(max(score, 0.0), 1.0), 4)
        ranked.append(
            {
                "fault_id": fault_id,
                "fault_name": rule.get("fault_name", fault_id),
                "fault_label": kb.label_for_fault(rule, fault_id),
                "system": rule.get("system_id") or rule.get("system"),
                "subsystem": rule.get("subsystem_id") or rule.get("subsystem"),
                "score": confidence,
                "confidence": confidence,
                "final_cf": confidence,  # Legacy alias
                "cf_breakdown": breakdown,
                "score_breakdown": {
                    "cf_confidence": confidence,
                    "confidence": confidence,
                    "note": "Điểm tin cậy Certainty Factor, không phải xác suất Bayes.",
                },
                "confidence_label": confidence_label(confidence),
                "decision": "accepted" if confidence >= 0.5 else "uncertain",
                "candidate_reason": rule.get("candidate_reason"),
                "matched_rules": matched_rules,
                "repairs": rule.get("repairs", []),
                "resolution": rule.get("resolution"),
            }
        )

    return sorted(ranked, key=lambda item: item["confidence"], reverse=True)


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
