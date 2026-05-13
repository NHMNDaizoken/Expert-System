"""
Compatibility wrapper — re-exports from src.expert_system.knowledge.loader.

All logic has been moved to src/expert_system/knowledge/loader.py.
This file exists so that existing imports continue to work.
"""
from src.expert_system.knowledge.loader import (  # noqa: F401
    DEFAULT_STAGING_DIR,
    KnowledgeBase,
    extract_rules,
    load_json,
    slugify,
)
