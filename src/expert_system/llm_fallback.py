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

DECISION_NEEDS_REVIEW = "Cần chuyên gia xác nhận"
SOURCE_LLM_FALLBACK = "fallback_llm_ngoai_kb"
SOURCE_OFFLINE_FALLBACK = "fallback_offline_ngoai_kb"

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

SYSTEM_LABELS_VI = {
    "Engine": "Hệ thống động cơ",
    "Brake": "Hệ thống phanh",
    "Electrical": "Hệ thống điện",
    "Transmission": "Hệ thống hộp số",
    "Cooling System": "Hệ thống làm mát",
    "Fuel System": "Hệ thống nhiên liệu",
    "Suspension": "Hệ thống treo",
    "Steering": "Hệ thống lái",
    "Exhaust": "Hệ thống xả",
    "HVAC": "Hệ thống điều hòa",
    "Tire/Wheel": "Lốp và bánh xe",
    "Unknown": "Chưa xác định",
}

SOURCE_LABELS_VI = {
    "llm_fallback": SOURCE_LLM_FALLBACK,
    "offline_fallback": SOURCE_OFFLINE_FALLBACK,
    SOURCE_LLM_FALLBACK: SOURCE_LLM_FALLBACK,
    SOURCE_OFFLINE_FALLBACK: SOURCE_OFFLINE_FALLBACK,
}

DECISION_LABELS_VI = {
    "Needs expert review": DECISION_NEEDS_REVIEW,
    "need expert review": DECISION_NEEDS_REVIEW,
    "needs_review": DECISION_NEEDS_REVIEW,
    "Cần chuyên gia xác nhận": DECISION_NEEDS_REVIEW,
}

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


def _system_label_vi(system: str | None) -> str:
    if not system:
        return SYSTEM_LABELS_VI["Unknown"]
    return SYSTEM_LABELS_VI.get(system, system)


def _source_vi(source: str | None) -> str:
    return SOURCE_LABELS_VI.get(source or "", source or SOURCE_OFFLINE_FALLBACK)


def _decision_vi(decision: str | None) -> str:
    return DECISION_LABELS_VI.get(decision or "", decision or DECISION_NEEDS_REVIEW)


def _level_id(prefix: str, label: str) -> str:
    return f"{prefix}_{_slugify(label).upper()}"


def enqueue_llm_suggestion(
    user_input: str,
    llm_output: dict[str, Any],
    reason: str = "trieu_chung_chua_duoc_mapping",
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
Bạn là trợ lý chẩn đoán ô tô thận trọng, chỉ dùng làm fallback khi
Knowledge Graph dạng rule-based chưa có symptom khớp.

Chỉ trả về JSON hợp lệ. Không dùng markdown. Không giải thích ngoài JSON.
Toàn bộ giá trị hiển thị cho người dùng phải là tiếng Việt dễ hiểu.
Các key JSON giữ nguyên theo schema bên dưới để backend/UI dễ xử lý.

Triệu chứng người dùng nhập:
{user_input}

Chuẩn hóa kết quả thành cây chẩn đoán 6 tầng:
Tầng 1: hệ thống xe.
Tầng 2: triệu chứng chính.
Tầng 3: triệu chứng phụ và điều kiện xuất hiện.
Tầng 4: lỗi có thể xảy ra, sắp xếp theo confidence giảm dần.
Tầng 5: quy trình kiểm tra từng bước.
Tầng 6: test xác nhận, linh kiện cần thay nếu đủ điều kiện, và hướng xử lý.

System label kỹ thuật được phép dùng trong system_id hoặc system_code: {systems}
Nhưng các field hiển thị như system_label, fault_label_vi, reason_vi,
step_label_vi, expected_evidence, pass_condition, replace_when,
resolution_steps, notes phải viết bằng tiếng Việt.

Tạo tối đa {top_k} candidate chẩn đoán. Ưu tiên lỗi ô tô phổ biến.
Giữ confidence thận trọng vì đây không phải kết quả từ KG đã duyệt.
Không bao giờ đặt confidence cao hơn {MAX_LLM_CONFIDENCE}.

JSON shape:
{{
  "diagnostic_tree": {{
    "level_1_root": {{
      "system_id": "SYS_FUEL_SYSTEM_OR_UNKNOWN",
      "system_code": "Fuel System or Unknown",
      "system_label": "Tên hệ thống bằng tiếng Việt"
    }},
    "level_2_primary_symptom": {{
      "symptom_id": "SYM_SNAKE_CASE_ID",
      "symptom_name": "snake_case_name",
      "symptom_label_vi": "Tên triệu chứng ngắn gọn bằng tiếng Việt",
      "aliases": ["cách gọi khác bằng tiếng Việt"]
    }},
    "level_3_context": {{
      "secondary_symptoms": [
        {{"symptom_label_vi": "Triệu chứng phụ", "cf": 0.0}}
      ],
      "conditions": [
        {{"condition_label_vi": "Điều kiện xuất hiện triệu chứng", "cf": 0.0}}
      ],
      "missing_questions": ["Câu hỏi cần hỏi thêm tài xế bằng tiếng Việt"]
    }},
    "level_4_possible_faults": [
      {{
        "fault_id": "LLM_SNAKE_CASE_ID",
        "fault_name": "snake_case_name",
        "fault_label_vi": "Tên lỗi dễ đọc bằng tiếng Việt",
        "system": "Tên hệ thống bằng tiếng Việt",
        "confidence": 0.0,
        "reason_vi": "Lý do ngắn gọn và thận trọng bằng tiếng Việt",
        "decision": "Cần chuyên gia xác nhận",
        "matched_rules": [
          {{
            "symptom_id": "USER_REPORTED_SYMPTOM",
            "symptom_name": "user_reported_symptom",
            "symptom_label": "Triệu chứng người dùng báo bằng tiếng Việt",
            "cf": 0.0,
            "priority": 1,
            "source": "fallback_llm_ngoai_kb"
          }}
        ]
      }}
    ],
    "level_5_diagnosis_procedures": [
      {{
        "step_id": "STEP_1",
        "step_order": 1,
        "step_label_vi": "Bước kiểm tra an toàn bằng tiếng Việt",
        "expected_evidence": "Dấu hiệu/kết quả kỳ vọng bằng tiếng Việt"
      }}
    ],
    "level_6_confirmation_and_resolution": {{
      "confirmation_tests": [
        {{"test_label_vi": "Tên bài test bằng tiếng Việt", "pass_condition": "Điều kiện đạt bằng tiếng Việt"}}
      ],
      "parts_to_replace": [
        {{"part_label_vi": "Tên linh kiện bằng tiếng Việt", "replace_when": "Chỉ thay khi điều kiện này đúng"}}
      ],
      "resolution_steps": ["Hướng xử lý bằng tiếng Việt"]
    }}
  }},
  "summary_vi": "Một câu tóm tắt bằng tiếng Việt cho người review",
  "notes": ["Ghi chú thận trọng bằng tiếng Việt"]
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
    system_label = _system_label_vi(system)
    symptom_name = _slugify(user_input, default="user_reported_symptom")
    symptom_id = _level_id("SYM", user_input)

    return {
        "diagnostic_tree": {
            "level_1_root": {
                "system_id": _level_id("SYS", system),
                "system_code": system,
                "system_label": system_label,
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
                    "Có đèn cảnh báo hoặc đèn check engine sáng không?",
                    "Có mùi lạ, tiếng lạ, khói, rung giật hoặc rò rỉ chất lỏng không?",
                    "Xe đời nào, loại động cơ gì, đã bảo dưỡng hoặc thay linh kiện gì gần đây?",
                ],
            },
            "level_4_possible_faults": [
                {
                    "fault_id": "UNMAPPED_SYMPTOM",
                    "fault_name": "unmapped_symptom",
                    "fault_label_vi": "Triệu chứng chưa có trong Knowledge Graph",
                    "system": system_label,
                    "confidence": 0.2,
                    "reason_vi": "Chưa có rule đã duyệt để ánh xạ triệu chứng này sang lỗi cụ thể.",
                    "decision": DECISION_NEEDS_REVIEW,
                    "matched_rules": [
                        {
                            "symptom_id": "USER_REPORTED_SYMPTOM",
                            "symptom_name": "user_reported_symptom",
                            "symptom_label": user_input,
                            "cf": 0.2,
                            "priority": 1,
                            "source": SOURCE_OFFLINE_FALLBACK,
                        }
                    ],
                }
            ],
            "level_5_diagnosis_procedures": [
                {
                    "step_id": "STEP_COLLECT_CONTEXT",
                    "step_order": 1,
                    "step_label_vi": "Thu thập thêm thông tin về hệ thống xe, điều kiện xuất hiện, đèn cảnh báo, âm thanh, mùi và dữ liệu OBD nếu có.",
                    "expected_evidence": "Có đủ ngữ cảnh để chuyên gia chọn hệ thống, triệu chứng chính và lỗi nghi ngờ phù hợp.",
                },
                {
                    "step_id": "STEP_EXPERT_MAPPING",
                    "step_order": 2,
                    "step_label_vi": "Chuyên gia xác nhận đây có phải case thật và map vào cây chẩn đoán phù hợp.",
                    "expected_evidence": "Có rule hoặc mapping mới được duyệt trước khi đưa vào Knowledge Graph.",
                },
            ],
            "level_6_confirmation_and_resolution": {
                "confirmation_tests": [
                    {
                        "test_label_vi": "Review thủ công bởi chuyên gia",
                        "pass_condition": "Chuyên gia xác nhận hệ thống, lỗi, quy trình kiểm tra và hướng xử lý là hợp lệ.",
                    }
                ],
                "parts_to_replace": [],
                "resolution_steps": [
                    "Không khuyến nghị thay linh kiện cho tới khi có xác nhận chẩn đoán.",
                    "Nếu là case thật, thêm symptom và rule đã duyệt vào staging hoặc Knowledge Graph.",
                ],
            },
        },
        "summary_vi": f"Chưa có rule đã duyệt cho triệu chứng '{user_input}', cần chuyên gia xác nhận trước khi đưa vào Knowledge Graph.",
        "notes": [
            "Chưa cấu hình GEMINI_API_KEY nên hệ thống dùng fallback offline, không gọi LLM.",
        ],
    }


def _normalize_matched_rules(matched_rules: Any, user_input: str, source: str) -> list[dict[str, Any]]:
    if not isinstance(matched_rules, list) or not matched_rules:
        return [
            {
                "symptom_id": "USER_REPORTED_SYMPTOM",
                "symptom_name": "user_reported_symptom",
                "symptom_label": user_input,
                "cf": 0.2,
                "priority": 1,
                "source": _source_vi(source),
            }
        ]

    normalized = []
    for index, rule in enumerate(matched_rules, start=1):
        if not isinstance(rule, dict):
            continue
        normalized.append(
            {
                "symptom_id": rule.get("symptom_id") or "USER_REPORTED_SYMPTOM",
                "symptom_name": rule.get("symptom_name") or "user_reported_symptom",
                "symptom_label": rule.get("symptom_label") or user_input,
                "cf": rule.get("cf", 0.2),
                "priority": rule.get("priority", index),
                "source": _source_vi(rule.get("source") or source),
            }
        )
    return normalized


def _normalize_context(context: Any) -> dict[str, Any]:
    if not isinstance(context, dict):
        context = {}

    return {
        "secondary_symptoms": context.get("secondary_symptoms") or [],
        "conditions": context.get("conditions") or [],
        "missing_questions": context.get("missing_questions")
        or [
            "Triệu chứng xuất hiện trong điều kiện nào?",
            "Có đèn cảnh báo hoặc đèn check engine sáng không?",
            "Có tiếng lạ, mùi lạ, khói hoặc rung giật không?",
        ],
    }


def _normalize_resolution(resolution: Any) -> dict[str, Any]:
    if not isinstance(resolution, dict):
        resolution = {}

    return {
        "confirmation_tests": resolution.get("confirmation_tests") or [],
        "parts_to_replace": resolution.get("parts_to_replace") or [],
        "resolution_steps": resolution.get("resolution_steps")
        or ["Chỉ đưa vào Knowledge Graph sau khi chuyên gia xác nhận."],
    }


def _normalize_tree(payload: dict[str, Any], user_input: str, top_k: int, source: str) -> dict[str, Any]:
    if isinstance(payload.get("diagnostic_tree"), dict):
        tree = payload["diagnostic_tree"]
    else:
        tree = {}

    legacy_diagnoses = payload.get("diagnoses", [])
    possible_faults = tree.get("level_4_possible_faults") or legacy_diagnoses
    possible_faults = possible_faults[:top_k] if isinstance(possible_faults, list) else []

    inferred_system = _infer_system(user_input)
    first_system_code = next(
        (
            fault.get("system_code") or fault.get("system")
            for fault in possible_faults
            if isinstance(fault, dict) and (fault.get("system_code") or fault.get("system"))
        ),
        inferred_system,
    )
    if first_system_code == "Unknown" and inferred_system != "Unknown":
        first_system_code = inferred_system

    first_system_label = _system_label_vi(first_system_code)
    root = tree.get("level_1_root") if isinstance(tree.get("level_1_root"), dict) else {}
    symptom = tree.get("level_2_primary_symptom") if isinstance(tree.get("level_2_primary_symptom"), dict) else {}
    symptom_label = symptom.get("symptom_label_vi") or symptom.get("symptom_label") or user_input

    normalized_faults = []
    for index, fault in enumerate(possible_faults, start=1):
        if not isinstance(fault, dict):
            continue

        fault_id = fault.get("fault_id") or f"LLM_FAULT_{index}"
        fault_name = fault.get("fault_name") or _slugify(fault_id)
        fault_system_code = fault.get("system_code") or first_system_code or inferred_system
        fault_system_label = _system_label_vi(fault.get("system") or fault_system_code)
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
                "system": fault_system_label,
                "confidence": min(confidence, MAX_LLM_CONFIDENCE),
                "reason_vi": fault.get("reason_vi") or fault.get("reason") or "Đây là candidate từ fallback ngoài Knowledge Graph, cần chuyên gia xác nhận.",
                "decision": _decision_vi(fault.get("decision")),
                "matched_rules": _normalize_matched_rules(fault.get("matched_rules"), user_input, source),
            }
        )

    normalized_faults.sort(key=lambda item: item["confidence"], reverse=True)

    return {
        "level_1_root": {
            "system_id": root.get("system_id") or _level_id("SYS", first_system_code),
            "system_code": root.get("system_code") or first_system_code,
            "system_label": root.get("system_label") or first_system_label,
        },
        "level_2_primary_symptom": {
            "symptom_id": symptom.get("symptom_id") or _level_id("SYM", symptom_label),
            "symptom_name": symptom.get("symptom_name") or _slugify(symptom_label, default="user_reported_symptom"),
            "symptom_label_vi": symptom_label,
            "aliases": symptom.get("aliases") or [symptom_label],
        },
        "level_3_context": _normalize_context(tree.get("level_3_context")),
        "level_4_possible_faults": normalized_faults,
        "level_5_diagnosis_procedures": tree.get("level_5_diagnosis_procedures") or _legacy_repairs_to_steps(legacy_diagnoses),
        "level_6_confirmation_and_resolution": _normalize_resolution(tree.get("level_6_confirmation_and_resolution")),
    }


def _legacy_repairs_to_steps(diagnoses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    order = 1
    for diagnosis in diagnoses:
        if not isinstance(diagnosis, dict):
            continue
        for repair in diagnosis.get("repairs", []):
            if not isinstance(repair, dict):
                continue
            for step in repair.get("steps", []):
                steps.append(
                    {
                        "step_id": f"STEP_{order}",
                        "step_order": order,
                        "step_label_vi": step,
                        "expected_evidence": repair.get("repair_label") or "Cần kiểm tra để xác nhận bằng chứng chẩn đoán.",
                    }
                )
                order += 1

    return steps or [
        {
            "step_id": "STEP_REVIEW",
            "step_order": 1,
            "step_label_vi": "Chuyên gia review triệu chứng và chọn nhánh cây chẩn đoán phù hợp.",
            "expected_evidence": "Có mapping được duyệt.",
        }
    ]


def diagnose_with_llm(user_input: str, top_k: int = 5) -> dict[str, Any]:
    source = SOURCE_LLM_FALLBACK
    queue_reason = "trieu_chung_chua_duoc_mapping"

    if not _has_api_key():
        payload = _offline_response(user_input)
        source = SOURCE_OFFLINE_FALLBACK
        queue_reason = "offline_trieu_chung_chua_duoc_mapping"
    else:
        try:
            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(DEFAULT_MODEL)
            response = model.generate_content(_prompt(user_input, top_k))
            payload = _safe_json(response.text)
        except Exception as exc:
            payload = _offline_response(user_input)
            payload.setdefault("notes", []).append(f"Gọi LLM fallback thất bại: {exc}")
            source = SOURCE_OFFLINE_FALLBACK
            queue_reason = "offline_trieu_chung_chua_duoc_mapping"

    diagnostic_tree = _normalize_tree(payload, user_input=user_input, top_k=top_k, source=source)
    possible_faults = diagnostic_tree["level_4_possible_faults"]

    result = {
        "diagnostic_tree": diagnostic_tree,
        "summary_vi": payload.get("summary_vi")
        or f"Triệu chứng '{user_input}' đã được chuẩn hóa theo cây 6 tầng và cần chuyên gia xác nhận.",
        "diagnoses": possible_faults,  # Giữ tương thích ngược cho UI/API cũ.
        "notes": payload.get("notes", []),
        "source": source,
        "schema_version": "diagnostic_tree.v1",
        "queued_for_review": False,
    }

    try:
        enqueue_llm_suggestion(user_input, result, reason=queue_reason)
        result["queued_for_review"] = True
    except Exception as exc:
        result.setdefault("notes", []).append(f"Không thể đưa gợi ý vào hàng chờ review: {exc}")

    return result
