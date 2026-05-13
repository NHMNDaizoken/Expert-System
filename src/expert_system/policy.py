"""
Compatibility wrapper — re-exports from src.expert_system.inference.policy.

All logic has been moved to src/expert_system/inference/policy.py.
This file exists so that existing imports continue to work.
"""
from src.expert_system.inference.policy import apply_response_policy  # noqa: F401
