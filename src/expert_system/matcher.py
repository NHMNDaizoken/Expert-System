"""
Compatibility wrapper — re-exports from src.expert_system.inference.fuzzy.

All logic has been moved to src/expert_system/inference/fuzzy.py.
This file exists so that existing imports continue to work.
"""
from src.expert_system.inference.fuzzy import (  # noqa: F401
    MATCH_THRESHOLD,
    SymptomMatcher,
)
