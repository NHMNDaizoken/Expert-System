from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.core.dependencies import require_admin_api_key
from backend.schemas import ExpertReviewApproveRequest, ExpertReviewRejectRequest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUGGESTIONS_PATH = PROJECT_ROOT / "data" / "staging" / "llm_suggestions.jsonl"

router = APIRouter(
    prefix="/api/expert-review",
    tags=["expert-review"],
    dependencies=[Depends(require_admin_api_key)],
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _suggestion_id(record: dict[str, Any], line_index: int) -> str:
    key = f"{record.get('created_at', '')}|{record.get('user_input', '')}"
    if key != "|":
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return str(line_index)


def _read_suggestions() -> list[dict[str, Any]]:
    if not SUGGESTIONS_PATH.exists():
        return []

    records: list[dict[str, Any]] = []
    with SUGGESTIONS_PATH.open("r", encoding="utf-8") as file:
        for line_index, line in enumerate(file):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                record["id"] = _suggestion_id(record, line_index)
                record.setdefault("created_at", None)
                record.setdefault("reason", None)
                record.setdefault("user_input", "")
                record.setdefault("llm_output", {})
                record.setdefault("reviewed", False)
                record.setdefault("promoted_to_kb", False)
                record.setdefault("review_status", "pending")
                records.append(record)
    return records


def _write_suggestions(records: list[dict[str, Any]]) -> None:
    SUGGESTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=SUGGESTIONS_PATH.parent,
        delete=False,
        newline="\n",
    ) as temp_file:
        temp_path = Path(temp_file.name)
        for record in records:
            persisted = dict(record)
            persisted.pop("id", None)
            temp_file.write(json.dumps(persisted, ensure_ascii=False) + "\n")

    os.replace(temp_path, SUGGESTIONS_PATH)


def _pending_first(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            bool(record.get("reviewed")),
            record.get("created_at") or "",
        ),
    )


def _find_suggestion(records: list[dict[str, Any]], suggestion_id: str) -> dict[str, Any]:
    for record in records:
        if record.get("id") == suggestion_id:
            return record
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Suggestion was not found.",
    )


@router.get("/suggestions")
def list_suggestions():
    return {"suggestions": _pending_first(_read_suggestions())}


@router.get("/suggestions/{suggestion_id}")
def get_suggestion(suggestion_id: str):
    return _find_suggestion(_read_suggestions(), suggestion_id)


@router.post("/suggestions/{suggestion_id}/approve")
def approve_suggestion(suggestion_id: str, payload: ExpertReviewApproveRequest):
    if not payload.approved_payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="approved_payload must be a non-empty object.",
        )

    try:
        from backend.services.expert_review_promotion import promote_approved_payload
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Expert review promotion service is unavailable: {exc}",
        ) from exc

    records = _read_suggestions()
    record = _find_suggestion(records, suggestion_id)
    try:
        promote_approved_payload(payload.approved_payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    record["reviewed"] = True
    record["review_status"] = "approved"
    record["approved_at"] = _now_iso()
    record["approved_payload"] = payload.approved_payload
    record["promoted_to_kb"] = True
    _write_suggestions(records)
    return record


@router.post("/suggestions/{suggestion_id}/reject")
def reject_suggestion(suggestion_id: str, payload: ExpertReviewRejectRequest):
    records = _read_suggestions()
    record = _find_suggestion(records, suggestion_id)
    record["reviewed"] = True
    record["review_status"] = "rejected"
    record["rejected_at"] = _now_iso()
    record["reject_reason"] = payload.reason or payload.reject_reason
    record["promoted_to_kb"] = False
    _write_suggestions(records)
    return record


def _run_script(path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return {
            "script": str(path.relative_to(PROJECT_ROOT)),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except Exception as exc:
        return {
            "script": str(path.relative_to(PROJECT_ROOT)),
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "success": False,
        }


@router.post("/rebuild")
def rebuild_knowledge():
    scripts = [
        PROJECT_ROOT / "scripts" / "build" / "build_knowledge.py",
        PROJECT_ROOT / "scripts" / "graph" / "import_graph.py",
    ]
    runs = [_run_script(script) for script in scripts if script.exists()]
    return {
        "success": bool(runs) and all(run["success"] for run in runs),
        "stdout": "\n".join(run["stdout"] for run in runs),
        "stderr": "\n".join(run["stderr"] for run in runs),
        "runs": runs,
    }
