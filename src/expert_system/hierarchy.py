"""
Compatibility wrapper — re-exports from src.expert_system.knowledge.hierarchy.

All logic has been moved to src/expert_system/knowledge/hierarchy.py.
This file exists so that existing imports continue to work.
"""
from src.expert_system.knowledge.hierarchy import (  # noqa: F401
    LEVELS,
    SYSTEM_ROOTS,
    HierarchyNode,
    build_hierarchy,
    normalize_id,
    symptom_name,
)
