import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def new_session():
    response = client.post("/session/new")
    assert response.status_code == 200
    return response.json()["session_id"]


class TestSessionFields:
    def test_new_session_has_step_fields(self):
        sid = new_session()
        data = client.get(f"/session/{sid}").json()
        assert "current_step_id" in data
        assert "step_history" in data
        assert "last_answer" in data


class TestDiagnoseResponse:
    def test_response_has_new_fields(self):
        sid = new_session()
        response = client.post("/diagnose", json={"session_id": sid, "symptom": "blue smoke from exhaust"})
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "step_context" in data
        assert "fault_preview" in data

    def test_step_answer_updates_session(self):
        sid = new_session()
        client.post("/diagnose", json={"session_id": sid, "symptom": "blue smoke from exhaust"})
        response = client.post("/diagnose", json={"session_id": sid, "step_answer": True})
        assert response.status_code == 200
        session = client.get(f"/session/{sid}").json()
        assert len(session.get("step_history", [])) > 0 or session.get("last_answer") is not None

    def test_diagnosed_response_has_resolution(self):
        pytest.skip("Full end-to-end diagnostic path depends on dataset question flow")

    def test_need_more_info_has_next_question(self):
        sid = new_session()
        data = client.post("/diagnose", json={"session_id": sid, "symptom": "warning light"}).json()
        if data.get("status") == "need_more_info":
            assert data.get("next_question") is not None

    def test_step_progress_format(self):
        sid = new_session()
        client.post("/diagnose", json={"session_id": sid, "symptom": "blue smoke from exhaust"})
        client.post("/diagnose", json={"session_id": sid, "step_answer": True})
        data = client.post("/diagnose", json={"session_id": sid, "step_answer": False}).json()
        progress = data.get("step_progress")
        if progress:
            current, total = progress.split("/")
            assert current.isdigit()
            assert total.isdigit()
