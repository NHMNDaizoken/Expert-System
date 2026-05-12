from __future__ import annotations

from typing import Any

DIAGNOSIS_THRESHOLD = 0.70
DIAGNOSIS_GAP_THRESHOLD = 0.30
MIN_CONFIRMED_SYMPTOMS = 2
MIN_QUESTIONS_ASKED = 1


def combine_cf(cf_old: float, cf_new: float) -> float:
    """MYCIN-style combination for positive confidence evidence."""
    return cf_old + cf_new * (1 - cf_old)


def confidence_label(score: float) -> str:
    if score >= 0.8:
        return "Rất có khả năng"
    if score >= 0.6:
        return "Có khả năng"
    if score >= 0.4:
        return "Có thể xảy ra"
    return "Chưa chắc chắn"


def load_cf_map(kg_rules: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
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
            if symptom_id in confirmed:
                cf = float(cf_map.get(symptom_id, {}).get(fault_id, symptom.get("cf", 0.5)))
                score = combine_cf(score, cf)
                breakdown.append({"symptom": symptom_id, "cf": cf, "direction": "confirmed"})
                matched_rules.append({**symptom, "symptom_name": symptom_id, "cf": cf})
            elif symptom_id in rejected:
                cf = float(cf_map.get(symptom_id, {}).get(fault_id, symptom.get("cf", 0.5)))
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


def check_diagnosed(ranked: list[dict[str, Any]]) -> bool:
    if not ranked:
        return False
    top = float(ranked[0].get("final_cf", ranked[0].get("score", 0)))
    second = float(ranked[1].get("final_cf", ranked[1].get("score", 0))) if len(ranked) > 1 else 0
    confirmed_count = len(ranked[0].get("matched_rules", []))
    question_count = int(ranked[0].get("question_count", 0) or 0)
    if ranked[0].get("deterministic"):
        return top >= DIAGNOSIS_THRESHOLD
    return (
        top >= DIAGNOSIS_THRESHOLD
        and confirmed_count >= MIN_CONFIRMED_SYMPTOMS
        and question_count >= MIN_QUESTIONS_ASKED
        and (top - second) >= DIAGNOSIS_GAP_THRESHOLD
    )


class CFReasoner:
    """Ranks fault hypotheses using Certainty Factor confidence."""

    def __init__(
        self,
        cf_map: dict[str, dict[str, float]],
        diagnosis_threshold: float = DIAGNOSIS_THRESHOLD,
        gap_threshold: float = DIAGNOSIS_GAP_THRESHOLD,
        min_confirmed_symptoms: int = MIN_CONFIRMED_SYMPTOMS,
        min_questions_asked: int = MIN_QUESTIONS_ASKED,
    ):
        self.cf_map = cf_map
        self.diagnosis_threshold = diagnosis_threshold
        self.gap_threshold = gap_threshold
        self.min_confirmed_symptoms = min_confirmed_symptoms
        self.min_questions_asked = min_questions_asked

    def rank(
        self,
        confirmed_symptoms: list[str],
        rejected_symptoms: list[str],
        rules: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        return rank_faults(confirmed_symptoms, rejected_symptoms, self.cf_map, rules)[:top_k]

    def should_diagnose(
        self,
        ranked: list[dict[str, Any]],
        *,
        has_useful_question: bool = False,
        procedure_terminal: str | None = None,
        max_questions_reached: bool = False,
        confirmed_symptom_count: int = 0,
        question_count: int = 0,
        deterministic_match: bool = False,
    ) -> bool:
        if procedure_terminal == "DIAGNOSED":
            return bool(ranked)
        if not ranked:
            return False
        top = float(ranked[0].get("final_cf", ranked[0].get("score", 0)))
        second = float(ranked[1].get("final_cf", ranked[1].get("score", 0))) if len(ranked) > 1 else 0.0
        if deterministic_match:
            return top >= self.diagnosis_threshold

        strong_enough = top >= self.diagnosis_threshold
        clear_gap = top - second >= self.gap_threshold
        enough_context = (
            confirmed_symptom_count >= self.min_confirmed_symptoms
            and question_count >= self.min_questions_asked
        )
        if max_questions_reached and not has_useful_question:
            return strong_enough and enough_context and clear_gap
        return strong_enough and enough_context and clear_gap
