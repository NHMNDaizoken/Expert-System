import json

from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routes import expert_review as expert_review_route


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-API-Key": settings.admin_api_key}


def _seed_suggestions(path):
    record = {
        "created_at": "2026-05-12T00:00:00+00:00",
        "reason": "seed-test",
        "user_input": "dong co bi rung",
        "llm_output": {"diagnoses": []},
        "reviewed": False,
        "promoted_to_kb": False,
        "review_status": "pending",
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_expert_review_requires_admin_key(tmp_path, monkeypatch):
    suggestions_path = tmp_path / "llm_suggestions.jsonl"
    _seed_suggestions(suggestions_path)
    monkeypatch.setattr(expert_review_route, "SUGGESTIONS_PATH", suggestions_path)

    response = client.get("/api/expert-review/suggestions")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing admin API key."


def test_expert_review_list_and_reject_flow(tmp_path, monkeypatch):
    suggestions_path = tmp_path / "llm_suggestions.jsonl"
    _seed_suggestions(suggestions_path)
    monkeypatch.setattr(expert_review_route, "SUGGESTIONS_PATH", suggestions_path)

    list_response = client.get(
        "/api/expert-review/suggestions",
        headers=_admin_headers(),
    )
    assert list_response.status_code == 200

    suggestions = list_response.json()["suggestions"]
    assert len(suggestions) == 1
    suggestion_id = suggestions[0]["id"]

    reject_response = client.post(
        f"/api/expert-review/suggestions/{suggestion_id}/reject",
        json={"reason": "du lieu chua dung format"},
        headers=_admin_headers(),
    )
    assert reject_response.status_code == 200

    payload = reject_response.json()
    assert payload["reviewed"] is True
    assert payload["review_status"] == "rejected"
    assert payload["reject_reason"] == "du lieu chua dung format"

    persisted_line = suggestions_path.read_text(encoding="utf-8").strip()
    persisted = json.loads(persisted_line)
    assert persisted["review_status"] == "rejected"
    assert persisted["reviewed"] is True
