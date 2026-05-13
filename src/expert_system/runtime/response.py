from typing import Any, List, Optional
from pydantic import BaseModel

class DiagnosisCandidate(BaseModel):
    fault_id: str
    fault_name: str
    fault_label: str
    system: Optional[str] = None
    final_cf: float
    confidence: float
    confidence_label: str

class QuestionResponse(BaseModel):
    question: str
    step_id: Optional[str] = None
    symptom: Optional[str] = None
    symptom_id: Optional[str] = None
    label: Optional[str] = None
    mode: str
    results: List[Any] = []
    fault_preview: Optional[dict] = None
    explanation: Optional[str] = None

class DiagnosisResponse(BaseModel):
    api_version: str = "v1"
    matched_symptoms: List[dict] = []
    diagnoses: List[dict] = []
    results: List[dict] = []
    current_hypotheses: List[dict] = []
    candidate_faults: List[DiagnosisCandidate] = []
    next_question: Optional[QuestionResponse] = None
    reasoning_trace: dict = {}
    status: str
    is_final: bool
    tree_level: str
    explanation_summary: str
    source: str
    procedure_terminal: Optional[str] = None
    resolution: Optional[dict] = None
    confirmed_symptoms: Optional[List[str]] = None
    rejected_symptoms: Optional[List[str]] = None
    detected_systems: Optional[List[str]] = None
    primary_symptom: Optional[str] = None
    confirmed_context: Optional[List[str]] = None
    rejected_context: Optional[List[str]] = None
    active_fault_path: Optional[List[dict]] = None
