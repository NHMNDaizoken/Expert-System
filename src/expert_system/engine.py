"""
Compatibility wrapper — re-exports from the new modular structure.

All logic has been moved to src/expert_system/inference/engine.py
and src/expert_system/runtime/state.py.
This file exists so that existing imports continue to work.
"""
from src.expert_system.inference.engine import (  # noqa: F401
    ExpertSystemEngine,
    InferenceEngine,
    load_cf_map,
    rank_faults,
)
from src.expert_system.runtime.state import WorkingMemory  # noqa: F401
from src.expert_system.runtime.trace import ExplanationBuilder  # noqa: F401
