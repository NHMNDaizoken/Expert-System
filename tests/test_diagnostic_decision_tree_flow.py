from pathlib import Path
from unittest.mock import patch

from backend.core.config import settings
from backend.database import ensure_database
from backend.services.diagnosis_service import DiagnosisService


def setup_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sqlite_db_path", tmp_path / "app.sqlite3")
    ensure_database()


def test_start_generates_complete_tree_once(tmp_path, monkeypatch):
    setup_temp_db(tmp_path, monkeypatch)
    service = DiagnosisService()

    with patch("backend.services.diagnosis_service.get_engine", side_effect=RuntimeError("kg down")), patch("backend.services.diagnosis_service.enqueue_llm_suggestion", return_value=True), patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
        response = service.start_decision_tree("Gầm xe kêu hoặc rung không đều")

    session = service.sessions.get(response["session_id"])
    tree = session["decision_tree"]["tree"]
    result_leaves = [node for node in tree["nodes"] if node["type"] == "result"]

    assert response["type"] == "diagnostic_decision_tree"
    assert response["current_node"]["answer_type"] == "yes_no"
    assert response.get("decision_tree", {}).get("tree", {}).get("nodes")
    assert response.get("source") == "llm_fallback"
    assert len(result_leaves) >= 3
    assert session["candidate_id"] == response["candidate_id"]


def test_answer_follows_pre_generated_tree_without_llm(tmp_path, monkeypatch):
    setup_temp_db(tmp_path, monkeypatch)
    service = DiagnosisService()

    with patch("backend.services.diagnosis_service.get_engine", side_effect=RuntimeError("kg down")), patch("backend.services.diagnosis_service.enqueue_llm_suggestion", return_value=True), patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
        started = service.start_decision_tree("Gầm xe kêu hoặc rung không đều")

    with patch("backend.services.diagnosis_service.diagnose_with_llm", side_effect=AssertionError("LLM must not be called")):
        response = service.answer_decision_tree(started["session_id"], "q1", "yes")

    assert response["type"] == "question"
    assert response["current_node"]["node_id"] == "q2"
    assert response["answers"][0]["answer"] == "yes"


def test_result_returns_selected_path_and_full_tree(tmp_path, monkeypatch):
    setup_temp_db(tmp_path, monkeypatch)
    service = DiagnosisService()

    with patch("backend.services.diagnosis_service.get_engine", side_effect=RuntimeError("kg down")), patch("backend.services.diagnosis_service.enqueue_llm_suggestion", return_value=True), patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
        started = service.start_decision_tree("Gầm xe kêu hoặc rung không đều")

    service.answer_decision_tree(started["session_id"], "q1", "yes")
    result = service.answer_decision_tree(started["session_id"], "q2", "no")

    assert result["type"] == "result"
    assert result["result_node"]["type"] == "result"
    assert result["selected_path"][-1]["next_node_id"] == result["result_node"]["node_id"]
    assert result["full_tree"]["root_node_id"] == "q1"
    assert result["expert_review"]["candidate_ready"] is True
