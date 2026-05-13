from typing import List, Any, Optional
from pydantic import BaseModel, Field

class TraceEvent(BaseModel):
    event_type: str
    message: str
    data: dict = Field(default_factory=dict)

class FuzzyTrace(BaseModel):
    input_text: str
    matched_symptoms: List[dict] = Field(default_factory=list)

class CFTrace(BaseModel):
    fault_id: str
    initial_cf: float
    contributions: List[dict] = Field(default_factory=list)
    final_cf: float = 0.0

class QuestionTrace(BaseModel):
    question_id: str
    mode: str
    score: float = 0.0

class PolicyTrace(BaseModel):
    original_status: str
    new_status: str
    reason: str

class RejectedCandidateTrace(BaseModel):
    fault_id: str
    reason: str
