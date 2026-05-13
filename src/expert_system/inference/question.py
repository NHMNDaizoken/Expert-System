"""
question — Next-question selection via information gain.

Selects the best unasked symptom to maximize information gain
across the current fault hypotheses, enabling the engine to
disambiguate between competing candidates efficiently.
"""
from __future__ import annotations

import math
from typing import Any

from src.expert_system.knowledge.loader import KnowledgeBase
from src.expert_system.runtime.state import WorkingMemory


def select_by_information_gain(
    ranked: list[dict[str, Any]],
    asked: set[str],
    all_symptoms: list[str],
    cf_map: dict[str, dict[str, float]],
) -> dict[str, Any] | None:
    """Pick the unasked symptom with the highest expected information gain."""

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


def related_symptoms(symptom_id: str, kb: KnowledgeBase) -> set[str]:
    """Find symptoms in the same semantic group as the given symptom."""
    label = (kb.label_for_symptom(symptom_id) or symptom_id).lower()

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
    for rule in kb.rules:
        for symptom in rule.get("symptoms", []):
            sid = symptom.get("symptom_id")
            slabel = (kb.label_for_symptom(sid) or sid or "").lower()
            if sid and any(k in slabel or k in sid.lower() for k in active_group):
                related.add(sid)

    return related


def select_information_gain_question(
    memory: WorkingMemory,
    ranked: list[dict[str, Any]],
    kb: KnowledgeBase,
    max_questions: int,
) -> dict[str, Any] | None:
    """Build a full next-question payload using information gain."""
    if memory.question_count >= max_questions:
        return None

    top_ranked = ranked[:3]
    candidate_fault_ids = {
        diagnosis.get("fault_id")
        for diagnosis in top_ranked
        if diagnosis.get("fault_id")
    }
    all_symptoms = [
        symptom.get("symptom_id")
        for rule in kb.rules
        if rule.get("fault_id") in candidate_fault_ids
        for symptom in rule.get("symptoms", [])
        if symptom.get("symptom_id")
    ]
    if not all_symptoms:
        all_symptoms = [
            symptom.get("symptom_id")
            for rule in kb.rules_for_symptoms(memory.confirmed_symptoms)
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
        asked |= related_symptoms(memory.primary_symptom, kb)
    result = select_by_information_gain(ranked, asked, all_symptoms, kb.cf_map)
    if not result:
        return None
    symptom_id = result["symptom_id"]
    label = kb.label_for_symptom(symptom_id)
    return {
        "symptom": symptom_id,
        "symptom_id": symptom_id,
        "label": label,
        "question": _symptom_question(symptom_id, label),
        "step_id": None,
        "mode": "information_gain",
        "information_gain": result["information_gain"],
        "fault_preview": None,
        "explanation": "Được chọn vì đây là triệu chứng chưa hỏi giúp phân biệt tốt nhất giữa các giả thuyết lỗi.",
    }


def _symptom_question(symptom_id: str, label: str | None) -> str:
    """Generate a Vietnamese question for a symptom."""
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
