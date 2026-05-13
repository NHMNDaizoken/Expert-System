"""
Compatibility wrapper — re-exports from src.expert_system.knowledge.schema
and src.expert_system.runtime.result.

All logic has been moved to the new subpackages.
This file exists so that existing imports continue to work.
"""
from src.expert_system.runtime.result import (  # noqa: F401
    DiagnosisCandidate,
    DiagnosisResponse,
)
from src.expert_system.knowledge.schema import (  # noqa: F401
    ExpertSystemValidator,
    ValidationReport,
    main,
    print_report,
    validate_knowledge_base,
)
