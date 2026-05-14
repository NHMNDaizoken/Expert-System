from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.expert_system.config import ENV_PATH

load_dotenv(ENV_PATH)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PLACEHOLDER_KEYS = {"", "your_gemini_api_key", "change_me", "changeme"}
LLM_SUGGESTION_QUEUE = Path("data/staging/llm_suggestions.jsonl")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# --- Schema Templates ---

CANDIDATE_SCHEMA = {
    "candidate_id": "string",
    "source": "llm_fallback",
    "language": "vi",
    "status": "pending_expert_review",
    "vehicle_context": {
        "make": None,
        "model": None,
        "year": None,
        "engine": None,
        "mileage_km": None
    },
    "input_symptoms": ["string"],
    "faults": [
        {
            "fault_id": "snake_case_unique_id",
            "fault_name": "Vietnamese fault name",
            "system": "engine|cooling_system|fuel_system|ignition_system|brake_system|electrical_system|transmission|unknown",
            "severity": "low|medium|high|critical",
            "confidence": 0.0,
            "symptoms": [
                {
                    "symptom_id": "snake_case_id",
                    "label_vi": "Vietnamese symptom",
                    "aliases": ["alias 1", "alias 2"]
                }
            ],
            "components": [
                {
                    "component_id": "snake_case_id",
                    "name_vi": "Vietnamese component name"
                }
            ],
            "causes": ["Possible cause"],
            "diagnostic_steps": ["Diagnostic step"],
            "repair_steps": ["Repair step"],
            "safety_notes": ["Safety warning"],
            "when_to_stop": ["When user should stop self-repair"]
        }
    ]
}

QUESTION_SCHEMA = {
    "next_question": "string",
    "reasoning": "string",
    "missing_info": ["string"]
}

DECISION_TREE_SCHEMA = {
    "type": "diagnostic_decision_tree",
    "candidate_id": "string",
    "source": "llm_fallback",
    "language": "vi",
    "root_symptom": {
        "symptom_id": "snake_case_id",
        "label_vi": "Triệu chứng gốc",
        "aliases": ["alias 1", "alias 2"],
    },
    "tree": {
        "root_node_id": "q1",
        "nodes": [
            {
                "node_id": "q1",
                "type": "question",
                "question": "Câu hỏi yes/no đầu tiên?",
                "answer_type": "yes_no",
                "yes_next": "q2",
                "no_next": "q3",
                "unknown_next": "q_unknown_1",
                "purpose": "Vì sao hỏi câu này",
            },
            {
                "node_id": "r1",
                "type": "result",
                "fault": {
                    "fault_id": "snake_case_fault_id",
                    "fault_name": "Tên lỗi tiếng Việt",
                    "system": "engine|cooling_system|fuel_system|ignition_system|brake_system|electrical_system|transmission|suspension|steering|unknown",
                    "severity": "low|medium|high|critical",
                    "confidence": 0.0,
                },
                "components": [{"component_id": "snake_case_id", "name_vi": "Tên bộ phận"}],
                "causes": ["Nguyên nhân"],
                "diagnostic_steps": ["Cách kiểm tra"],
                "repair_steps": ["Cách sửa"],
                "safety_notes": ["Lưu ý an toàn"],
                "when_to_stop": ["Khi nào cần dừng và đưa xe tới thợ"],
            },
        ],
    },
    "expert_review": {"candidate_ready": True, "status": "pending_expert_review"},
}

# --- Helpers ---

def _has_api_key() -> bool:
    return bool(GEMINI_API_KEY and GEMINI_API_KEY.strip() not in PLACEHOLDER_KEYS)

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

def _get_model():
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(DEFAULT_MODEL)

def validate_candidate(candidate: dict[str, Any]) -> bool:
    """Strict validation of the LLM candidate JSON."""
    if not isinstance(candidate, dict): return False
    if "faults" not in candidate or not candidate["faults"]: return False
    
    for fault in candidate["faults"]:
        if not all(k in fault for k in ("fault_id", "fault_name", "symptoms", "repair_steps")):
            return False
        if not fault["repair_steps"]:
            # Auto-generate fallback steps
            fault["repair_steps"] = [
                "Xác minh các triệu chứng đã báo cáo.",
                "Kiểm tra các bộ phận liên quan.",
                "Sửa chữa hoặc thay thế các bộ phận bị hỏng theo khuyến nghị của chuyên gia."
            ]
    return True

def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value or "unknown"

def _snake_vi(text: str) -> str:
    normalized = (
        text.lower()
        .replace("đ", "d")
        .replace("Đ", "d")
    )
    import unicodedata
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return _slug(normalized)

def _fallback_decision_tree(user_input: str) -> dict[str, Any]:
    symptom_id = _snake_vi(user_input)
    candidate_id = f"llm_tree_{symptom_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    is_underbody = any(token in user_input.lower() for token in ("gầm", "gam", "rung", "kêu", "ồn"))
    if is_underbody:
        root_label = "Gầm xe kêu hoặc rung không đều"
        nodes = [
            {
                "node_id": "q1",
                "type": "question",
                "question": "Tiếng kêu hoặc rung xuất hiện rõ hơn khi đi qua ổ gà, đường xấu không?",
                "answer_type": "yes_no",
                "yes_next": "q2",
                "no_next": "q3",
                "unknown_next": "q_unknown_1",
                "purpose": "Phân biệt lỗi treo/gầm với lỗi truyền động hoặc bánh xe.",
            },
            {
                "node_id": "q2",
                "type": "question",
                "question": "Xe có bị lệch lái, nhao lái hoặc lắc thân xe khi phanh hay ôm cua không?",
                "answer_type": "yes_no",
                "yes_next": "r1",
                "no_next": "r2",
                "unknown_next": "r_unknown_1",
                "purpose": "Tìm dấu hiệu rotuyn, cao su càng A hoặc giảm xóc bị mòn.",
            },
            {
                "node_id": "q3",
                "type": "question",
                "question": "Rung tăng theo tốc độ xe và giảm khi chạy chậm lại không?",
                "answer_type": "yes_no",
                "yes_next": "r3",
                "no_next": "r4",
                "unknown_next": "r_unknown_1",
                "purpose": "Phân biệt mất cân bằng bánh/lốp với tiếng kêu cục bộ dưới gầm.",
            },
            {
                "node_id": "q_unknown_1",
                "type": "question",
                "question": "Âm thanh giống tiếng cộc cộc kim loại khi xe bắt đầu chạy hoặc chuyển số không?",
                "answer_type": "yes_no",
                "yes_next": "r5",
                "no_next": "r_unknown_1",
                "unknown_next": "r_unknown_1",
                "purpose": "Khi người dùng chưa rõ điều kiện xuất hiện, kiểm tra nhóm truyền động an toàn trước.",
            },
            {
                "node_id": "r1",
                "type": "result",
                "fault": {"fault_id": "mon_rotuyn_cao_su_cang_a", "fault_name": "Mòn rotuyn hoặc cao su càng A", "system": "suspension", "severity": "high", "confidence": 0.78},
                "components": [{"component_id": "rotuyn_lai", "name_vi": "Rotuyn lái"}, {"component_id": "cao_su_cang_a", "name_vi": "Cao su càng A"}],
                "causes": ["Bạc cao su lão hóa", "Rotuyn rơ do mòn", "Va chạm ổ gà mạnh"],
                "diagnostic_steps": ["Nâng xe an toàn và kiểm tra độ rơ bánh trước.", "Dùng đòn bẩy kiểm tra cao su càng A nứt, rách hoặc xê dịch.", "Kiểm tra độ chụm nếu xe bị lệch lái."],
                "repair_steps": ["Thay rotuyn hoặc cao su càng A hỏng.", "Siết đúng lực các bu-lông treo.", "Cân chỉnh thước lái sau sửa chữa."],
                "safety_notes": ["Không chui dưới xe khi chỉ dùng kích cơ.", "Ngừng chạy nếu xe nhao lái mạnh hoặc có tiếng va đập lớn."],
                "when_to_stop": ["Vô lăng rung mạnh", "Xe mất ổn định khi phanh hoặc ôm cua"],
            },
            {
                "node_id": "r2",
                "type": "result",
                "fault": {"fault_id": "giam_xoc_hoac_cao_su_chan_giam_xoc_yeu", "fault_name": "Giảm xóc hoặc cao su chân giảm xóc yếu", "system": "suspension", "severity": "medium", "confidence": 0.68},
                "components": [{"component_id": "giam_xoc", "name_vi": "Giảm xóc"}, {"component_id": "cao_su_chan_giam_xoc", "name_vi": "Cao su chân giảm xóc"}],
                "causes": ["Giảm xóc rò dầu", "Cao su đỡ bị chai hoặc nứt", "Lò xo hoặc cụm treo làm việc không đều"],
                "diagnostic_steps": ["Quan sát dầu rò trên thân giảm xóc.", "Ấn mạnh góc xe để xem thân xe có dao động nhiều lần không.", "Kiểm tra cao su chân giảm xóc khi đánh lái và qua gờ."],
                "repair_steps": ["Thay giảm xóc theo cặp cùng trục nếu yếu.", "Thay cao su chân giảm xóc bị nứt.", "Kiểm tra lại góc đặt bánh sau khi tháo cụm treo."],
                "safety_notes": ["Lò xo treo có lực nén lớn, cần dụng cụ ép lò xo đúng chuẩn."],
                "when_to_stop": ["Giảm xóc chảy dầu nhiều", "Xe chòng chành khó kiểm soát"],
            },
            {
                "node_id": "r3",
                "type": "result",
                "fault": {"fault_id": "mat_can_bang_banh_xe_hoac_lop_bien_dang", "fault_name": "Mất cân bằng bánh xe hoặc lốp biến dạng", "system": "suspension", "severity": "medium", "confidence": 0.74},
                "components": [{"component_id": "lop_xe", "name_vi": "Lốp xe"}, {"component_id": "mam_banh", "name_vi": "Mâm bánh"}],
                "causes": ["Lốp mòn lệch", "Mâm cong", "Chì cân bằng bánh bị rơi"],
                "diagnostic_steps": ["Kiểm tra áp suất và độ mòn từng lốp.", "Quan sát phồng, méo hoặc rạn trên hông lốp.", "Cân bằng động bánh xe và kiểm tra đảo mâm."],
                "repair_steps": ["Cân bằng động lại bánh xe.", "Đảo lốp hoặc thay lốp biến dạng.", "Nắn hoặc thay mâm nếu cong nặng."],
                "safety_notes": ["Không chạy tốc độ cao khi lốp phồng hoặc nứt hông."],
                "when_to_stop": ["Lốp phồng rộp", "Vô lăng rung mạnh ở tốc độ cao"],
            },
            {
                "node_id": "r4",
                "type": "result",
                "fault": {"fault_id": "tam_chan_gam_ong_xa_long", "fault_name": "Tấm chắn gầm hoặc ống xả bị lỏng", "system": "unknown", "severity": "low", "confidence": 0.57},
                "components": [{"component_id": "tam_chan_gam", "name_vi": "Tấm chắn gầm"}, {"component_id": "ong_xa", "name_vi": "Ống xả"}],
                "causes": ["Ốc giữ tấm chắn gầm lỏng", "Cao su treo ống xả hỏng", "Tấm cách nhiệt va vào thân xe"],
                "diagnostic_steps": ["Kiểm tra các tấm nhựa/kim loại dưới gầm.", "Lắc nhẹ ống xả khi xe nguội để tìm điểm va chạm.", "Quan sát cao su treo ống xả bị đứt hoặc giãn."],
                "repair_steps": ["Siết hoặc thay ốc kẹp tấm chắn.", "Thay cao su treo ống xả.", "Cố định lại tấm cách nhiệt."],
                "safety_notes": ["Chỉ kiểm tra ống xả khi đã nguội."],
                "when_to_stop": ["Ngửi thấy mùi khí xả trong cabin", "Ống xả có nguy cơ rơi hoặc kéo lê"],
            },
            {
                "node_id": "r5",
                "type": "result",
                "fault": {"fault_id": "cao_su_chan_may_hop_so_hong", "fault_name": "Cao su chân máy hoặc chân hộp số hỏng", "system": "transmission", "severity": "medium", "confidence": 0.64},
                "components": [{"component_id": "cao_su_chan_may", "name_vi": "Cao su chân máy"}, {"component_id": "cao_su_chan_hop_so", "name_vi": "Cao su chân hộp số"}],
                "causes": ["Cao su chân máy chai nứt", "Chân hộp số rơ", "Cụm động cơ dịch chuyển quá mức khi vào số"],
                "diagnostic_steps": ["Quan sát động cơ khi chuyển số D/R với phanh giữ chắc.", "Kiểm tra cao su chân máy nứt, xẹp hoặc tách lớp.", "Tìm vết va giữa cụm máy/hộp số với khung phụ."],
                "repair_steps": ["Thay chân máy hoặc chân hộp số hỏng.", "Siết lại bu-lông giá đỡ theo lực chuẩn.", "Kiểm tra rung sau khi thay."],
                "safety_notes": ["Cần người có kinh nghiệm khi kiểm tra chuyển số tại chỗ."],
                "when_to_stop": ["Cụm máy giật mạnh khi vào số", "Có tiếng va kim loại lớn"],
            },
            {
                "node_id": "r_unknown_1",
                "type": "result",
                "fault": {"fault_id": "tieng_keu_gam_chua_xac_dinh", "fault_name": "Tiếng kêu gầm chưa xác định cần kiểm tra tổng quát", "system": "unknown", "severity": "medium", "confidence": 0.42},
                "components": [{"component_id": "cum_gam_treo_truyen_dong", "name_vi": "Cụm gầm, treo và truyền động"}],
                "causes": ["Thông tin điều kiện xuất hiện chưa đủ", "Nhiều nhóm lỗi có triệu chứng tương tự"],
                "diagnostic_steps": ["Ghi lại tốc độ, mặt đường và thời điểm tiếng kêu xuất hiện.", "Kiểm tra tổng quát gầm trên cầu nâng.", "Ưu tiên kiểm tra các chi tiết an toàn như rotuyn, càng A, giảm xóc, lốp."],
                "repair_steps": ["Không thay linh kiện khi chưa xác định điểm rơ hoặc hỏng.", "Đưa xe đến xưởng để kiểm tra trên cầu nâng nếu tiếng kêu lặp lại."],
                "safety_notes": ["Dừng xe nếu âm thanh đi kèm mất lái, rung mạnh hoặc mùi khét."],
                "when_to_stop": ["Không xác định được nguồn tiếng kêu", "Tiếng kêu tăng nhanh theo thời gian"],
            },
        ]
    else:
        root_label = user_input.strip()
        nodes = [
            {"node_id": "q1", "type": "question", "question": "Triệu chứng xuất hiện liên tục khi xe đang vận hành không?", "answer_type": "yes_no", "yes_next": "q2", "no_next": "q3", "unknown_next": "r_unknown_1", "purpose": "Phân biệt lỗi thường trực với lỗi ngắt quãng."},
            {"node_id": "q2", "type": "question", "question": "Có đèn cảnh báo hoặc âm thanh bất thường đi kèm không?", "answer_type": "yes_no", "yes_next": "r1", "no_next": "r2", "unknown_next": "r_unknown_1", "purpose": "Xác định mức độ ưu tiên kiểm tra an toàn."},
            {"node_id": "q3", "type": "question", "question": "Triệu chứng chỉ xuất hiện trong một điều kiện cụ thể như phanh, tăng tốc hoặc đánh lái không?", "answer_type": "yes_no", "yes_next": "r3", "no_next": "r_unknown_1", "unknown_next": "r_unknown_1", "purpose": "Khoanh vùng hệ thống liên quan."},
            {"node_id": "r1", "type": "result", "fault": {"fault_id": "loi_can_quet_ma_va_kiem_tra_an_toan", "fault_name": "Lỗi cần quét mã và kiểm tra an toàn", "system": "unknown", "severity": "high", "confidence": 0.55}, "components": [{"component_id": "he_thong_lien_quan", "name_vi": "Hệ thống liên quan"}], "causes": ["Có dấu hiệu cảnh báo đi kèm"], "diagnostic_steps": ["Quét mã lỗi OBD nếu có.", "Ghi nhận điều kiện xuất hiện triệu chứng."], "repair_steps": ["Xử lý theo mã lỗi và kết quả kiểm tra thực tế."], "safety_notes": ["Không tiếp tục chạy nếu xe mất công suất, mất phanh hoặc mất lái."], "when_to_stop": ["Có đèn cảnh báo đỏ hoặc xe vận hành bất thường nghiêm trọng"]},
            {"node_id": "r2", "type": "result", "fault": {"fault_id": "loi_co_khi_hoac_bao_duong_can_kiem_tra", "fault_name": "Lỗi cơ khí hoặc bảo dưỡng cần kiểm tra", "system": "unknown", "severity": "medium", "confidence": 0.45}, "components": [{"component_id": "cum_co_khi_lien_quan", "name_vi": "Cụm cơ khí liên quan"}], "causes": ["Mòn, lỏng hoặc sai chỉnh"], "diagnostic_steps": ["Kiểm tra trực quan các cụm liên quan.", "So sánh tiếng/rung với điều kiện vận hành."], "repair_steps": ["Siết, chỉnh hoặc thay linh kiện hỏng sau khi xác minh."], "safety_notes": ["Dùng dụng cụ nâng đỡ an toàn khi kiểm tra."], "when_to_stop": ["Triệu chứng tăng nhanh hoặc ảnh hưởng điều khiển xe"]},
            {"node_id": "r3", "type": "result", "fault": {"fault_id": "loi_phu_thuoc_dieu_kien_van_hanh", "fault_name": "Lỗi phụ thuộc điều kiện vận hành", "system": "unknown", "severity": "medium", "confidence": 0.5}, "components": [{"component_id": "he_thong_theo_dieu_kien", "name_vi": "Hệ thống theo điều kiện xuất hiện"}], "causes": ["Lỗi chỉ xuất hiện khi tải hoặc thao tác cụ thể"], "diagnostic_steps": ["Tái hiện triệu chứng trong điều kiện an toàn.", "Khoanh vùng theo thao tác phanh, tăng tốc, đánh lái hoặc vào số."], "repair_steps": ["Kiểm tra và sửa nhóm linh kiện tương ứng với điều kiện tái hiện."], "safety_notes": ["Không thử xe ở tốc độ cao trên đường công cộng."], "when_to_stop": ["Không tái hiện an toàn được triệu chứng"]},
            {"node_id": "r_unknown_1", "type": "result", "fault": {"fault_id": "trieu_chung_chua_du_thong_tin", "fault_name": "Triệu chứng chưa đủ thông tin", "system": "unknown", "severity": "medium", "confidence": 0.35}, "components": [{"component_id": "he_thong_chua_xac_dinh", "name_vi": "Hệ thống chưa xác định"}], "causes": ["Mô tả ban đầu còn mơ hồ"], "diagnostic_steps": ["Bổ sung thời điểm, tốc độ, âm thanh, đèn báo và điều kiện xuất hiện.", "Kiểm tra tổng quát tại xưởng nếu triệu chứng lặp lại."], "repair_steps": ["Chưa nên sửa hoặc thay linh kiện khi chưa xác minh."], "safety_notes": ["Dừng xe nếu có dấu hiệu mất an toàn."], "when_to_stop": ["Không có đủ dữ liệu để tự kiểm tra"]},
        ]
    return {
        "type": "diagnostic_decision_tree",
        "candidate_id": candidate_id,
        "source": "llm_fallback",
        "language": "vi",
        "root_symptom": {
            "symptom_id": symptom_id,
            "label_vi": root_label,
            "aliases": list(dict.fromkeys([user_input.strip(), root_label, "Gầm xe kêu"] if is_underbody else [user_input.strip(), root_label])),
        },
        "tree": {"root_node_id": "q1", "nodes": nodes},
        "expert_review": {"candidate_ready": True, "status": "pending_expert_review"},
    }

def validate_decision_tree(candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return False, ["candidate must be an object"]
    if candidate.get("type") != "diagnostic_decision_tree":
        errors.append("type must be diagnostic_decision_tree")
    tree = candidate.get("tree") or {}
    nodes = tree.get("nodes") or []
    node_map = {node.get("node_id"): node for node in nodes if isinstance(node, dict)}
    root_id = tree.get("root_node_id")
    if not root_id or root_id not in node_map:
        errors.append("root_node_id must exist in nodes")
    result_count = 0
    for node in nodes:
        node_id = node.get("node_id")
        if node.get("type") == "question":
            for branch in ("yes_next", "no_next", "unknown_next"):
                target = node.get(branch)
                if not target or target not in node_map:
                    errors.append(f"{node_id}.{branch} points to missing node {target}")
            if node.get("answer_type") != "yes_no":
                errors.append(f"{node_id}.answer_type must be yes_no")
        elif node.get("type") == "result":
            result_count += 1
            if not node.get("fault"):
                errors.append(f"{node_id} result node must have fault")
            if not node.get("repair_steps"):
                errors.append(f"{node_id} result node must have repair_steps")
            if not node.get("diagnostic_steps"):
                errors.append(f"{node_id} result node must have diagnostic_steps")
        else:
            errors.append(f"{node_id} has invalid type")
    if result_count < 3:
        errors.append("tree must contain at least 3 result leaf nodes")
    return not errors, errors

# --- Prompts ---

def generate_clarification_question(user_input: str, asked_questions: list[str]) -> dict[str, Any]:
    model = _get_model()
    prompt = f"""
Bạn là một chuyên gia chẩn đoán ô tô. Người dùng đã mô tả triệu chứng: "{user_input}".
Các câu hỏi đã hỏi: {json.dumps(asked_questions, ensure_ascii=False)}.

Nhiệm vụ: Tạo một câu hỏi tiếp theo để làm rõ tình trạng xe. 
Yêu cầu:
- KHÔNG lặp lại các câu hỏi đã hỏi.
- Câu hỏi ngắn gọn, chuyên nghiệp, bằng tiếng Việt.
- Trả về JSON theo schema: {json.dumps(QUESTION_SCHEMA)}
"""
    try:
        response = model.generate_content(prompt)
        return _safe_json(response.text)
    except Exception as e:
        return {"next_question": "Bạn có thể mô tả chi tiết hơn về tình trạng xe không?", "error": str(e)}

def generate_candidate(user_input: str, conversation_state: dict[str, Any], retry=False) -> dict[str, Any]:
    model = _get_model()
    prompt = f"""
Bạn là chuyên gia chẩn đoán ô tô. 
Triệu chứng người dùng: "{user_input}"
Thông tin thêm từ hội thoại: {json.dumps(conversation_state, ensure_ascii=False)}

Nhiệm vụ: Tạo một đề xuất chẩn đoán (candidate) hoàn chỉnh.
Yêu cầu:
- TRẢ VỀ DUY NHẤT JSON. KHÔNG markdown, KHÔNG giải thích.
- Tuân thủ schema: {json.dumps(CANDIDATE_SCHEMA, ensure_ascii=False)}
"""
    if retry:
        prompt += "\nLƯU Ý: Lần trước bạn đã trả về JSON không hợp lệ. Vui lòng CHỈ trả về JSON hợp lệ ngay bây giờ."

    try:
        response = model.generate_content(prompt)
        candidate = _safe_json(response.text)
        if validate_candidate(candidate):
            return candidate
        if not retry:
            return generate_candidate(user_input, conversation_state, retry=True)
    except Exception as e:
        print(f"LLM Error: {e}")
    
    return None

def generate_decision_tree_candidate(user_input: str, conversation_state: dict[str, Any] | None = None, retry=False) -> dict[str, Any]:
    if not _has_api_key():
        return _fallback_decision_tree(user_input)

    model = _get_model()
    prompt = f"""
Bạn là chuyên gia chẩn đoán ô tô.
Triệu chứng ban đầu của người dùng: "{user_input}"
Ngữ cảnh phiên: {json.dumps(conversation_state or {}, ensure_ascii=False)}

Nhiệm vụ: Tạo TOÀN BỘ cây quyết định chẩn đoán Yes/No/Unknown ngay từ đầu.
Đây KHÔNG phải vòng hỏi đáp hội thoại. Không tạo một câu hỏi riêng lẻ.

Yêu cầu bắt buộc:
- TRẢ VỀ DUY NHẤT JSON hợp lệ. KHÔNG markdown, KHÔNG giải thích.
- Tuân thủ schema: {json.dumps(DECISION_TREE_SCHEMA, ensure_ascii=False)}
- Tất cả node question phải có answer_type="yes_no" và đủ yes_next/no_next/unknown_next.
- Có ít nhất 3 node result cho triệu chứng phổ biến.
- Mỗi result phải có fault, components, causes, diagnostic_steps, repair_steps, safety_notes, when_to_stop.
- source phải là "llm_fallback"; expert_review.candidate_ready phải là true.
"""
    if retry:
        prompt += "\nLƯU Ý: JSON trước đó không hợp lệ. Hãy sửa nhánh bị thiếu và chỉ trả JSON."
    try:
        response = model.generate_content(prompt)
        candidate = _safe_json(response.text)
        ok, errors = validate_decision_tree(candidate)
        if ok:
            return candidate
        if not retry:
            return generate_decision_tree_candidate(user_input, conversation_state, retry=True)
        print(f"Decision tree validation failed: {errors}")
    except Exception as e:
        print(f"LLM Error: {e}")
    return _fallback_decision_tree(user_input)

def enqueue_llm_suggestion(user_input: str, candidate: dict[str, Any]) -> bool:
    if not candidate: return False
    LLM_SUGGESTION_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_input": user_input,
        "llm_output": candidate,
        "reviewed": False,
        "promoted_to_kb": False
    }
    
    try:
        with LLM_SUGGESTION_QUEUE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False

# --- Main Entry Point ---

def diagnose_with_llm(user_input: str, session: dict[str, Any]) -> dict[str, Any]:
    """
    Main entry point for LLM fallback flow.
    Generates a complete diagnostic decision tree once for the initial symptom.
    """
    existing = (session or {}).get("decision_tree")
    if existing:
        return {
            "status": "pending_expert_review",
            "candidate": existing,
            "llm_candidate_generated": False,
            "type": "diagnostic_decision_tree",
        }

    candidate = generate_decision_tree_candidate(user_input, session or {})
    ok, errors = validate_decision_tree(candidate)
    if not ok:
        fallback = _fallback_decision_tree(user_input)
        candidate = fallback
    enqueue_llm_suggestion(user_input, candidate)
    return {
        "status": "pending_expert_review",
        "candidate": candidate,
        "llm_candidate_generated": True,
        "type": "diagnostic_decision_tree",
    }
