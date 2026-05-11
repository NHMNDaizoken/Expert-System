from typing import Any

from pydantic import BaseModel, Field


class DiagnoseRequest(BaseModel):
    session_id: str | None = None
    symptom: str | None = Field(default=None, min_length=1)
    step_answer: bool | None = None
    user_input: str | None = Field(default=None, min_length=1)
    text: str | None = Field(default=None, min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


class RuleDecisionRequest(BaseModel):
    cf: float | None = Field(default=None, ge=0, le=1)
    note: str | None = None


class ApiResponse(BaseModel):
    session_id: str | None = None
    status: str
    data: dict[str, Any] = Field(default_factory=dict)
