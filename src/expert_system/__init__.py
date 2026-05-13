"""
expert_system — Car diagnostic expert system core package.

Re-exports the main public API classes from the new modular structure
for backward compatibility.
"""
from src.expert_system.inference.engine import ExpertSystemEngine  # noqa: F401
from src.expert_system.knowledge.loader import KnowledgeBase  # noqa: F401
from src.expert_system.runtime.state import WorkingMemory  # noqa: F401
from src.expert_system.inference.fuzzy import SymptomMatcher  # noqa: F401
from src.expert_system.inference.procedure import ProcedureRunner  # noqa: F401
from src.expert_system.inference.policy import apply_response_policy  # noqa: F401

__all__ = ["ExpertSystemEngine", "KnowledgeBase", "WorkingMemory", "SymptomMatcher", "ProcedureRunner", "apply_response_policy"]
