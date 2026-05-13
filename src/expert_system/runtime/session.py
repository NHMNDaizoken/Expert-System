from dataclasses import dataclass, field
from typing import List, Any, Optional

@dataclass
class SessionState:
    confirmed_symptoms: List[str] = field(default_factory=list)
    rejected_symptoms: List[str] = field(default_factory=list)
    asked_questions: List[str] = field(default_factory=list)
    candidate_scores: List[Any] = field(default_factory=list)
    reasoning_trace: Optional[dict] = None
    
    def to_dict(self):
        return {
            "confirmed_symptoms": self.confirmed_symptoms,
            "rejected_symptoms": self.rejected_symptoms,
            "asked_questions": self.asked_questions,
            "candidate_scores": self.candidate_scores,
            "reasoning_trace": self.reasoning_trace,
        }
