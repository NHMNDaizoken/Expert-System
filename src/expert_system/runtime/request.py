from typing import Any, Optional
from pydantic import BaseModel, Field

class DiagnosisRequest(BaseModel):
    api_version: str = "v1"
    symptom: Optional[str] = None
    user_input: Optional[str] = None
    text: Optional[str] = None
    top_k: int = 5
    session_id: Optional[str] = None
    step_answer: Optional[bool] = None

class AnswerRequest(BaseModel):
    session_id: str
    answer: str
