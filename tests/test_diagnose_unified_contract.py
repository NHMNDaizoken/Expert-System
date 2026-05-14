"""Contract tests: POST /api/diagnose (and /diagnose) unified expert-system shape."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def _kg_need_more():
    return {
        "matched_symptoms": [{"symptom_id": "SYM_X", "label": "x"}],
        "status": "need_more_info",
        "next_question": {
            "step_id": "SYM_Q1",
            "symptom_id": "SYM_Q1",
            "question": "Có tiếng kêu lạ khi nổ máy không?",
            "mode": "information_gain",
        },
        "diagnoses": [{"fault_id": "FLT_A", "fault_label_vi": "Lỗi A", "final_cf": 0.4}],
        "current_hypotheses": [{"fault_id": "FLT_A", "fault_label_vi": "Lỗi A", "final_cf": 0.4}],
        "candidate_faults": [],
        "reasoning_trace": {},
        "is_final": False,
        "tree_level": 1,
        "explanation_summary": "",
        "source": "staging_files_kg",
        "procedure_terminal": None,
        "confirmed_symptoms": ["SYM_X"],
        "rejected_symptoms": [],
        "rejected_faults": [],
        "detected_systems": [],
        "primary_symptom": "SYM_X",
        "confirmed_context": [],
        "rejected_context": [],
        "active_fault_path": [],
    }


def _kg_inconclusive_low_confidence():
    return {
        "matched_symptoms": [{"symptom_id": "SYM_G_M_XE_K_U_HO_C_RUNG_KH_NG_U", "label": "Gầm xe kêu hoặc rung không đều"}],
        "status": "diagnosed",
        "next_question": None,
        "diagnoses": [
            {"fault_id": "general_inspection_needed", "fault_label_vi": "Cần kiểm tra tổng quát", "final_cf": 0.25},
            {"fault_id": "wheel_bearing_fault", "fault_label_vi": "Lỗi bi moay-ơ", "final_cf": 0.25},
        ],
        "current_hypotheses": [
            {"fault_id": "general_inspection_needed", "fault_label_vi": "Cần kiểm tra tổng quát", "final_cf": 0.25},
            {"fault_id": "wheel_bearing_fault", "fault_label_vi": "Lỗi bi moay-ơ", "final_cf": 0.25},
        ],
        "candidate_faults": [],
        "reasoning_trace": {},
        "is_final": False,
        "source": "staging_files_kg",
        "confirmed_symptoms": ["SYM_G_M_XE_K_U_HO_C_RUNG_KH_NG_U"],
        "rejected_symptoms": [],
        "rejected_faults": [],
        "detected_systems": [],
        "primary_symptom": "SYM_G_M_XE_K_U_HO_C_RUNG_KH_NG_U",
        "confirmed_context": [],
        "rejected_context": [],
        "active_fault_path": [],
    }


def _llm_candidate_tree():
    return {
        "type": "diagnostic_decision_tree",
        "candidate_id": "llm_underbody_symptom",
        "source": "llm_fallback",
        "language": "vi",
        "root_symptom": {
            "symptom_id": "sym_underbody_noise",
            "label_vi": "Gầm xe kêu hoặc rung không đều",
            "aliases": ["Gầm xe kêu hoặc rung không đều"],
        },
        "tree": {
            "root_node_id": "q1",
            "nodes": [
                {
                    "node_id": "q1",
                    "type": "question",
                    "question": "Tiếng kêu/rung xuất hiện rõ nhất khi nào?",
                    "answer_type": "yes_no",
                    "yes_next": "r1",
                    "no_next": "r2",
                    "unknown_next": "r_unknown",
                },
                {
                    "node_id": "r1",
                    "type": "result",
                    "fault": {
                        "fault_id": "suspension_bushing_link_fault",
                        "fault_name": "Lỗi cao su bushing/càng liên kết treo",
                        "system": "suspension",
                                "severity": "medium",
                                "confidence": 0.65,
                    },
                    "components": [{"component_id": "suspension_bushing", "name_vi": "Cao su treo"}],
                    "causes": ["Ổ gà/đường xấu"],
                    "diagnostic_steps": ["Kiểm tra cao su và khớp kết nối treo gần cầu trước."],
                    "repair_steps": ["Thay cao su bushing hoặc càng treo bị hỏng."],
                    "safety_notes": ["Đảm bảo xe được giữ chắc khi kiểm tra gầm."],
                },
                {
                    "node_id": "r2",
                    "type": "result",
                    "fault": {
                        "fault_id": "cv_joint_fault",
                        "fault_name": "Lỗi khớp CV",
                        "system": "drivetrain",
                                "severity": "medium",
                                "confidence": 0.6,
                    },
                    "components": [{"component_id": "cv_joint", "name_vi": "Khớp CV"}],
                    "causes": ["Đánh lái hoặc tăng tốc"],
                    "diagnostic_steps": ["Kiểm tra khớp CV và lớp bảo vệ bụi."],
                    "repair_steps": ["Thay khớp CV hoặc bảo vệ bị rách."],
                    "safety_notes": ["Không lái xe khi khớp CV bị hỏng nặng."],
                },
                {
                    "node_id": "r_unknown",
                    "type": "result",
                    "fault": {
                        "fault_id": "unknown_underbody_noise",
                        "fault_name": "Tiếng kêu gầm chưa xác định",
                        "system": "unknown",
                                "severity": "medium",
                                "confidence": 0.4,
                    },
                    "components": [{"component_id": "underbody_components", "name_vi": "Các bộ phận gầm"}],
                    "causes": ["Thông tin chưa đủ"],
                    "diagnostic_steps": ["Ghi lại điều kiện xuất hiện triệu chứng và kiểm tra tổng quát."],
                    "repair_steps": ["Đưa xe tới xưởng để kiểm tra gầm."],
                    "safety_notes": ["Không tự thay thế khi chưa xác định đúng nguyên nhân."],
                },
            ],
        },
        "expert_review": {"candidate_ready": True, "status": "pending_expert_review"},
    }


def test_post_diagnose_and_api_diagnose_same_router():
    with patch("backend.services.diagnosis_service.get_engine") as ge:
        ge.return_value.diagnose = MagicMock(return_value=_kg_need_more())
        r1 = client.post("/diagnose", json={"symptom": "xe khó nổ", "top_k": 5})
        r2 = client.post("/api/diagnose", json={"symptom": "xe khó nổ", "top_k": 5})
    assert r1.status_code == 200 and r2.status_code == 200
    for r in (r1, r2):
        data = r.json()
        assert data["status"] == "need_more_info"
        assert data.get("next_question", {}).get("question")
        assert data.get("session_id")


def test_no_llm_when_kg_need_more_info_has_next_question():
    """Runtime only uses KG/expert-system - no LLM fallback in diagnose()"""
    with patch("backend.services.diagnosis_service.get_engine") as ge:
        ge.return_value.diagnose = MagicMock(return_value=_kg_need_more())
        r = client.post("/api/diagnose", json={"symptom": "xe khó nổ", "top_k": 5})
    assert r.status_code == 200
    assert r.json()["source"] == "knowledge_graph"


def test_llm_fallback_triggers_on_weak_kg_inconclusive():
    candidate = _llm_candidate_tree()
    with patch("backend.services.diagnosis_service.get_engine") as ge, patch("backend.services.diagnosis_service.diagnose_with_llm") as llm:
        ge.return_value.diagnose = MagicMock(return_value=_kg_inconclusive_low_confidence())
        llm.return_value = {"candidate": candidate}

        r = client.post("/api/diagnose", json={"symptom": "Gầm xe kêu hoặc rung không đều", "top_k": 5})

    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "llm_fallback"
    assert data["status"] == "need_more_info"
    assert data["mode"] == "fallback_question"
    assert data["next_question"]["question"]
    assert data["next_question"]["answer_options"] == ["Có", "Không", "Không rõ"]
    assert data["session_id"]


def test_llm_fallback_follow_up_question_is_answered_via_diagnose():
    candidate = _llm_candidate_tree()
    with patch("backend.services.diagnosis_service.get_engine") as ge, patch("backend.services.diagnosis_service.diagnose_with_llm") as llm, patch("backend.services.diagnosis_service.enqueue_llm_suggestion") as enqueue:
        ge.return_value.diagnose = MagicMock(return_value=_kg_inconclusive_low_confidence())
        llm.return_value = {"candidate": candidate}

        first = client.post("/api/diagnose", json={"symptom": "Gầm xe kêu hoặc rung không đều", "top_k": 5})
        sid = first.json()["session_id"]

        follow = client.post("/api/diagnose", json={"session_id": sid, "step_answer": "yes"})

    assert follow.status_code == 200
    data = follow.json()
    assert data["source"] == "llm_fallback"
    assert data["status"] == "suggested_diagnosis"
    assert data["mode"] == "candidate_suggestion"
    assert data["is_final"] is False
    assert data["results"]
    assert data["expert_review"]["candidate_ready"] is True
    enqueue.assert_called_once()


def test_llm_candidate_string_components_are_normalized():
    from backend.services.diagnosis_service import _result_node_to_diagnoses

    result_node = {
        "node_id": "r1",
        "type": "result",
        "fault": {
            "fault_id": "fault_a",
            "fault_name": "Fault A",
            "system": "suspension",
            "severity": "medium",
            "confidence": 0.5,
        },
        "components": ["cv_joint", {"component_id": "brake_pad", "name_vi": "Má phanh"}],
        "repair_steps": "Kiểm tra bộ phận liên quan.",
    }

    rows = _result_node_to_diagnoses(result_node)
    assert rows[0]["resolution"]["parts"] == ["cv_joint", "Má phanh"]
    assert rows[0]["resolution"]["procedure"] == "Kiểm tra bộ phận liên quan."


def test_session_follow_up_accepts_bool_and_unknown_string():
    with patch("backend.services.diagnosis_service.get_engine") as ge:
        ge.return_value.diagnose = MagicMock(return_value=_kg_need_more())
        first = client.post("/api/diagnose", json={"symptom": "xe khó nổ", "top_k": 5})
        sid = first.json()["session_id"]
        ge.return_value.diagnose = MagicMock(
            return_value={
                **_kg_need_more(),
                "status": "diagnosed",
                "is_final": True,
                "next_question": None,
                "results": [{"fault_id": "FLT_A", "fault_label_vi": "Lỗi A", "final_cf": 0.9}],
            }
        )
        r_true = client.post("/api/diagnose", json={"session_id": sid, "step_answer": True})
        assert r_true.status_code == 200
        first2 = client.post("/api/diagnose", json={"symptom": "other", "top_k": 3})
        sid2 = first2.json()["session_id"]
        r_unk = client.post("/api/diagnose", json={"session_id": sid2, "step_answer": "unknown"})
        assert r_unk.status_code == 200


def test_session_id_without_symptom_or_step_answer_422():
    r = client.post("/api/diagnose", json={"session_id": "not-a-real-session-id"})
    assert r.status_code == 422


def test_kg_down_returns_service_error():
    """Runtime raises 503 when KG is unavailable - no LLM fallback"""
    with patch("backend.services.diagnosis_service.get_engine", side_effect=RuntimeError("kg down")):
        r = client.post("/api/diagnose", json={"symptom": "Gầm xe kêu hoặc rung", "top_k": 5})
    assert r.status_code == 503
