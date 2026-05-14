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
    with patch("backend.services.diagnosis_service.get_engine") as ge:
        ge.return_value.diagnose = MagicMock(return_value=_kg_need_more())
        with patch("backend.services.diagnosis_service.diagnose_with_llm") as llm:
            r = client.post("/api/diagnose", json={"symptom": "xe khó nổ", "top_k": 5})
            llm.assert_not_called()
    assert r.status_code == 200
    assert r.json()["source"] == "knowledge_graph"


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


def test_llm_fallback_shapes_need_more_then_diagnosed_via_unified_endpoint():
    with patch("backend.services.diagnosis_service.get_engine", side_effect=RuntimeError("kg down")):
        with patch("backend.services.diagnosis_service.enqueue_llm_suggestion", return_value=True):
            with patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
                first = client.post("/api/diagnose", json={"symptom": "Gầm xe kêu hoặc rung", "top_k": 5})
    assert first.status_code == 200
    data = first.json()
    assert data["status"] == "need_more_info"
    assert data["source"] == "llm_fallback"
    assert "decision_tree" not in data
    assert data.get("next_question", {}).get("question")
    sid = data["session_id"]

    second = client.post("/api/diagnose", json={"session_id": sid, "step_answer": True})
    assert second.status_code == 200
    body = second.json()
    assert body["status"] in {"need_more_info", "diagnosed"}
    assert body["source"] == "llm_fallback"
    assert "decision_tree" not in body
