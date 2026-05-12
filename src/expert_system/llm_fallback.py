from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.config import ENV_PATH


load_dotenv(ENV_PATH)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PLACEHOLDER_KEYS = {"", "your_gemini_api_key", "change_me", "changeme"}
LLM_SUGGESTION_QUEUE = Path("data/staging/llm_suggestions.jsonl")
MAX_LLM_CONFIDENCE = 0.55

SYSTEM_CANDIDATES = [
    "Engine",
    "Brake",
    "Electrical",
    "Transmission",
    "Cooling System",
    "Fuel System",
    "Suspension",
    "Steering",
    "Exhaust",
    "HVAC",
    "Tire/Wheel",
    "Unknown",
]

SYSTEM_KEYWORDS = {
    "Fuel System": ["hao xăng", "tốn xăng", "mùi xăng", "xăng", "nhiên liệu", "fuel"],
    "Cooling System": ["nóng máy", "quá nhiệt", "nhiệt cao", "két nước", "nước làm mát", "coolant"],
    "Brake": ["phanh", "thắng", "brake"],
    "Electrical": ["đèn báo", "đèn lỗi", "ắc quy", "acquy", "điện", "battery", "check engine"],
    "Transmission": ["hộp số", "sang số", "trượt số", "transmission"],
    "Suspension": ["giảm xóc", "xóc", "treo", "suspension"],
    "Steering": ["lái", "vô lăng", "steering"],
    "Exhaust": ["khói", "ống xả", "exhaust"],
    "Engine": ["động cơ", "rung", "giật", "khó nổ", "máy", "engine"],
    "Tire/Wheel": ["lốp", "bánh", "mâm", "tire", "wheel"],
    "HVAC": ["điều hòa", "máy lạnh", "ac", "hvac"],
}


def _slugify(value: str, default: str = "unknown") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return value or default


def _has_api_key() -> bool:
    return bool(GEMINI_API_KEY and GEMINI_API_KEY.strip() not in PLACEHOLDER_KEYS)


def _infer_system(user_input: str) -> str:
    text = user_input.strip().lower()
    for system, keywords in SYSTEM_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return system
    return "Unknown"


def _level_id(prefix: str, label: str) -> str:
    return f"{prefix}_{_slugify(label).upper()}"


def enqueue_llm_suggestion(
    user_input: str,
    llm_output: dict[str, Any],
    reason: str = "unmatched_symptom",
) -> None:
    LLM_SUGGESTION_QUEUE.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "user_input": user_input,
        "llm_output": llm_output,
        "reviewed": False,
        "promoted_to_kb": False,
    }

    with LLM_SUGGESTION_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _prompt(user_input: str, top_k: int) -> str:
    systems = ", ".join(SYSTEM_CANDIDATES)
    return f"""
You are a cautious automotive diagnostic assistant used as a fallback when a
rule-based Knowledge Graph has no matching symptom.

Return only valid JSON. Do not include markdown.

User symptom text:
{user_input}

Normalize the answer into this 6-level diagnostic tree:
Level 1 root: vehicle system.
Level 2 primary symptom.
Level 3 secondary symptoms and operating context.
Level 4 possible faults sorted by confidence.
Level 5 step-by-step diagnosis procedures.
Level 6 confirmation tests, parts to replace, and resolution.

Allowed system labels: {systems}

Create up to {top_k} possible diagnostic candidates. Prefer common automotive
faults. Keep confidence conservative because this is not from the approved KG.
Never set confidence above {MAX_LLM_CONFIDENCE}.

JSON shape:
{{
  "diagnostic_tree": {{
    "level_1_root": {{
      "system_id": "FUEL_SYSTEM_OR_UNKNOWN",
      "system_label": "Fuel System or Unknown"
    }},
    "level_2_primary_symptom": {{
      "symptom_id": "SYM_SNAKE_CASE_ID",
      "symptom_name": "snake_case_name",
      "symptom_label_vi": "short Vietnamese symptom label",
      "aliases": ["alias 1"]
    }},
    "level_3_context": {{
      "secondary_symptoms": [
        {{"symptom_label_vi": "secondary symptom", "cf": 0.0}}
      ],
      "conditions": [
        {{"condition_label_vi": "when/where symptom appears", "cf": 0.0}}
      ],
      "missing_questions": ["question to ask the driver"]
    }},
    "level_4_possible_faults": [
      {{
        "fault_id": "LLM_SNAKE_CASE_ID",
        "fault_name": "snake_case_name",
        "fault_label_vi": "Vietnamese readable fault",
        "fault_label_en": "English readable fault",
        "system": "Vehicle system or Unknown",
        "confidence": 0.0,
        "reason_vi": "short cautious reason",
        "decision": "Needs expert review",
        "matched_rules": [
          {{
            "symptom_id": "USER_REPORTED_SYMPTOM",
            "symptom_name": "user_reported_symptom",
            "symptom_label": "short symptom label",
            "cf": 0.0,
            "priority": 1,
            "source": "llm_fallback"
          }}
        ]
      }}
    ],
    "level_5_diagnosis_procedures": [
      {{
        "step_id": "STEP_1",
        "step_order": 1,
        "step_label_vi": "safe inspection step",
        "expected_evidence": "what this step confirms or rules out"
      }}
    ],
    "level_6_confirmation_and_resolution": {{
      "confirmation_tests": [
        {{"test_label_vi": "test", "pass_condition": "expected result"}}
      ],
      "parts_to_replace": [
        {{"part_label_vi": "part", "replace_when": "condition for replacement"}}
      ],
      "resolution_steps": ["recommended resolution step"]
    }}
  }},
  "summary_vi": "one sentence summary for reviewer",
  "notes": ["short caveat"]
}}
""".strip()


def _safe_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _offline_response(user_input: str) -> dict[str, Any]:
    system = _infer_system(user_input)
    symptom_name = _slugify(user_input, default="user_reported_symptom")
    symptom_id = _level_id("SYM", user_input)

    return {
        "diagnostic_tree": {
            "level_1_root": {
                "system_id": _level_id("SYS", system),
                "system_label": system,
            },
            "level_2_primary_symptom": {
                "symptom_id": symptom_id,
                "symptom_name": symptom_name,
                "symptom_label_vi": user_input,
                "aliases": [user_input],
            },
            "level_3_context": {
                "secondary_symptoms": [],
                "conditions": [],
                "missing_questions": [
                    "Triệu chứng xuất hiện khi nào: lúc khởi động, chạy chậm, tăng tốc hay chạy đường dài?",
                    "Có đèn cảnh báo/check engine sáng không?",
                    "Có mùi lạ, tiếng lạ, khói, rung giật hoặc rò rỉ chất lỏng không?",
                    "Xe đời nào, loại động cơ gì, đã bảo dưỡng/thay linh kiện gì gần đây?",
                ],
            },
            "level_4_possible_faults": [
                {
                    "fault_id": "UNMAPPED_SYMPTOM",
                    "fault_name": "unmapped_symptom",
                    "fault_label_vi": "Triệu chứng chưa có trong Knowledge Graph",
                    "fault_label_en": "Symptom is not covered by current KG",
                    "system": system,
                    "confidence": 0.2,
                    "reason_vi": "Không có rule đã duyệt để ánh xạ triệu chứng này sang lỗi cụ thể.",
                    "decision": "Needs expert review",
                    "matched_rules": [
                        {
                            "symptom_id": "USER_REPORTED_SYMPTOM",
                            "symptom_name": "user_reported_symptom",
                            "symptom_label": user_input,
                            "cf": 0.2,
                            "priority": 1,
                            "source": "offline_fallback",
                        }
                    ],
                }
            ],
            "level_5_diagnosis_procedures": [
                {
                    "step_id": "STEP_COLLECT_CONTEXT",
                    "step_order": 1,
                    "step_label_vi": "Thu thập thêm hệ thống xe, điều kiện xuất hiện, đèn cảnh báo, âm thanh, mùi và dữ liệu OBD nếu có.",
                    "expected_evidence": "Có đủ context để chuyên gia chọn system, primary symptom và possible faults.",
                },
                {
                    "step_id": "STEP_EXPERT_MAPPING",
                    "step_order": 2,
                    "step_label_vi": "Chuyên gia xác nhận symptom có phải case thật và map vào cây chẩn đoán phù hợp.",
                    "expected_evidence": "Có rule hoặc mapping mới được duyệt trước khi promote vào KB.",
                },
            ],
            "level_6_confirmation_and_resolution": {
                "confirmation_tests": [
                    {
                        "test_label_vi": "Review thủ công bởi chuyên gia",
                        "pass_condition": "Chuyên gia xác nhận system, fault, procedure và resolution hợp lệ.",
                    }
                ],
                "parts_to_replace": [],
                "resolution_steps": [
                    "Không khuyến nghị thay linh kiện cho tới khi có xác nhận chẩn đoán.",
                    "Nếu là case thật, thêm symptom và rule đã duyệt vào data/staging hoặc Knowledge Graph.",
                ],
            },
        },
        "summary_vi": f"Chưa có rule đã duyệt cho triệu chứng '{user_input}', cần chuyên gia review trước khi đưa vào Knowledge Graph.",
        "notes": [
            "GEMINI_API_KEY is not configured, so no LLM diagnosis was generated.",
        ],
    }


def _normalize_tree(payload: dict[str, Any], user_input: str, top_k: int) -> dict[str, Any]:
    if isinstance(payload.get("diagnostic_tree"), dict):
        tree = payload["diagnostic_tree"]
    else:
        tree = {}

    legacy_diagnoses = payload.get("diagnoses", [])
    possible_faults = tree.get("level_4_possible_faults") or legacy_diagnoses
    possible_faults = possible_faults[:top_k] if isinstance(possible_faults, list) else []

    inferred_system = _infer_system(user_input)
    first_system = next(
        (fault.get("system") for fault in possible_faults if isinstance(fault, dict) and fault.get("system")),
        inferred_system,
    )
    if first_system == "Unknown" and inferred_system != "Unknown":
        first_system = inferred_system

    symptom = tree.get("level_2_primary_symptom") or {}
    symptom_label = symptom.get("symptom_label_vi") or symptom.get("symptom_label") or user_input

    normalized_faults = []
    for index, fault in enumerate(possible_faults, start=1):
        if not isinstance(fault, dict):
            continue
        fault_id = fault.get("fault_id") or f"LLM_FAULT_{index}"
        fault_name = fault.get("fault_name") or _slugify(fault_id)
        confidence = fault.get("confidence", fault.get("final_cf", 0.35))
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.35

        normalized_faults.append(
            {
                "fault_id": fault_id,
                "fault_name": fault_name,
                "fault_label_vi": fault.get("fault_label_vi") or fault.get("fault_label") or fault_name,
                "fault_label_en": fault.get("fault_label_en") or fault.get("fault_label") or fault_name,
                "system": fault.get("system") or first_system or "Unknown",
                "confidence": min(confidence, MAX_LLM_CONFIDENCE),
                "reason_vi": fault.get("reason_vi") or fault.get("reason") or "LLM fallback candidate; cần chuyên gia xác nhận.",
                "decision": fault.get("decision") or "Needs expert review",
                "matched_rules": fault.get("matched_rules") or [],
            }
        )

    normalized_faults.sort(key=lambda item: item["confidence"], reverse=True)

    tree = {
        "level_1_root": {
            "system_id": tree.get("level_1_root", {}).get("system_id") or _level_id("SYS", first_system),
            "system_label": tree.get("level_1_root", {}).get("system_label") or first_system or "Unknown",
        },
        "level_2_primary_symptom": {
            "symptom_id": symptom.get("symptom_id") or _level_id("SYM", symptom_label),
            "symptom_name": symptom.get("symptom_name") or _slugify(symptom_label, default="user_reported_symptom"),
            "symptom_label_vi": symptom_label,
            "aliases": symptom.get("aliases") or [symptom_label],
        },
        "level_3_context": tree.get("level_3_context")
        or {
            "secondary_symptoms": [],
            "conditions": [],
            "missing_questions": [
                "Triệu chứng xuất hiện trong điều kiện nào?",
                "Có đèn cảnh báo/check engine sáng không?",
                "Có tiếng lạ, mùi lạ, khói hoặc rung giật không?",
            ],
        },
        "level_4_possible_faults": normalized_faults,
        "level_5_diagnosis_procedures": tree.get("level_5_diagnosis_procedures")
        or _legacy_repairs_to_steps(legacy_diagnoses),
        "level_6_confirmation_and_resolution": tree.get("level_6_confirmation_and_resolution")
        or {
            "confirmation_tests": [],
            "parts_to_replace": [],
            "resolution_steps": ["Chỉ promote vào KB sau khi chuyên gia xác nhận."],
        },
    }

    return tree


def _legacy_repairs_to_steps(diagnoses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    order = 1
    for diagnosis in diagnoses:
        for repair in diagnosis.get("repairs", []):
            for step in repair.get("steps", []):
                steps.append(
                    {
                        "step_id": f"STEP_{order}",
                        "step_order": order,
                        "step_label_vi": step,
                        "expected_evidence": repair.get("repair_label", "Initial check"),
                    }
                )
                order += 1
    return steps or [
        {
            "step_id": "STEP_REVIEW",
            "step_order": 1,
            "step_label_vi": "Chuyên gia review symptom và chọn nhánh cây chẩn đoán phù hợp.",
            "expected_evidence": "Có mapping được duyệt.",
        }
    ]


def diagnose_with_llm(user_input: str, top_k: int = 5) -> dict[str, Any]:
    source = "llm_fallback"
    queue_reason = "unmatched_symptom"

    if not _has_api_key():
        payload = _offline_response(user_input)
        source = "offline_fallback"
        queue_reason = "offline_unmatched_symptom"
    else:
        try:
            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(DEFAULT_MODEL)
            response = model.generate_content(_prompt(user_input, top_k))
            payload = _safe_json(response.text)
        except Exception as exc:
            payload = _offline_response(user_input)
            payload["notes"].append(f"LLM fallback failed: {exc}")
            source = "offline_fallback"
            queue_reason = "offline_unmatched_symptom"

    diagnostic_tree = _normalize_tree(payload, user_input=user_input, top_k=top_k)
    possible_faults = diagnostic_tree["level_4_possible_faults"]

    result = {
        "diagnostic_tree": diagnostic_tree,
        "summary_vi": payload.get("summary_vi")
        or f"Triệu chứng '{user_input}' đã được chuẩn hóa theo cây 6 tầng và cần chuyên gia review.",
        "diagnoses": possible_faults,  # Backward compatible for old UI/API consumers.
        "notes": payload.get("notes", []),
        "source": source,
        "schema_version": "diagnostic_tree.v1",
        "queued_for_review": False,
    }

    try:
        enqueue_llm_suggestion(user_input, result, reason=queue_reason)
        result["queued_for_review"] = True
    except Exception as exc:
        result.setdefault("notes", []).append(f"Failed to queue LLM suggestion: {exc}")

    return result
