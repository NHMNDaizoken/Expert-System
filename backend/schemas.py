from typing import Any

from pydantic import BaseModel, Field, model_validator


class DiagnoseRequest(BaseModel):
    session_id: str | None = None
    symptom: str | None = Field(default=None, min_length=1)
    step_answer: Any | None = None
    user_input: str | None = Field(default=None, min_length=1)
    text: str | None = Field(default=None, min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def session_requires_symptom_or_step_answer(self):
        if not self.session_id:
            return self
        fields = getattr(self, "model_fields_set", set()) or set()
        has_symptom = bool(
            (self.symptom or "").strip()
            or (self.user_input or "").strip()
            or (self.text or "").strip()
        )
        if "step_answer" in fields or has_symptom:
            return self
        raise ValueError("Khi dùng session_id, hãy gửi symptom hoặc step_answer.")


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


class DiagnosisStartRequest(BaseModel):
    description: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class DiagnosisTreeAnswerRequest(BaseModel):
    session_id: str
    node_id: str
    answer: str


class RuleDecisionRequest(BaseModel):
    cf: float | None = Field(default=None, ge=0, le=1)
    note: str | None = None


class ExpertReviewApproveRequest(BaseModel):
    approved_payload: dict[str, Any]


class ExpertReviewRejectRequest(BaseModel):
    reason: str | None = None
    reject_reason: str | None = None


class ApiResponse(BaseModel):
    session_id: str | None = None
    status: str
    data: dict[str, Any] = Field(default_factory=dict)
