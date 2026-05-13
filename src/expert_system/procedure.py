"""
Compatibility wrapper — re-exports from src.expert_system.inference.procedure.

All logic has been moved to src/expert_system/inference/procedure.py.
This file exists so that existing imports continue to work.
"""
from src.expert_system.inference.procedure import (  # noqa: F401
    MAX_QUESTION_DEPTH,
    TERMINALS,
    ProcedureReasoner,
    ProcedureRunner,
    get_next_from_tree,
)
