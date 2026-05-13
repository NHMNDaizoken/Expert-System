from dataclasses import dataclass, field
from typing import List, Any, Optional

@dataclass
class CandidateScore:
    fault_id: str
    score: float
    confidence: float
    breakdown: List[dict] = field(default_factory=list)

@dataclass
class QuestionScore:
    question_id: str
    information_gain: float
    entropy_reduction: float

@dataclass
class PolicyDecision:
    action: str
    reason: str
    confidence_threshold: float = 0.0

@dataclass
class InferenceContext:
    session_id: str
    tree_level: str
    active_hypotheses: List[str] = field(default_factory=list)

@dataclass
class DiagnosisTrace:
    events: List[Any] = field(default_factory=list)
    reasoning_summary: str = ""
