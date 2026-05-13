# Expert System — Source Code Structure

This package contains the **runtime inference logic** for the car diagnostic expert system.

## Module Layout

```
src/expert_system/
├── inference/          # Core reasoning algorithms
│   ├── engine.py       # Main orchestrator (ExpertSystemEngine)
│   ├── certainty.py    # MYCIN-style CF scoring and fault ranking
│   ├── fuzzy.py        # Fuzzy symptom matching (SymptomMatcher)
│   ├── question.py     # Information-gain question selection
│   ├── procedure.py    # Procedure tree navigation (ProcedureRunner)
│   └── policy.py       # Final decision policies
│
├── knowledge/          # Knowledge base management
│   ├── loader.py       # KnowledgeBase class (reads staging data)
│   ├── schema.py       # Validation (ExpertSystemValidator)
│   └── aliases.py      # Symptom alias utilities (placeholder)
│
├── runtime/            # Session state and result models
│   ├── state.py        # WorkingMemory (diagnosis session state)
│   ├── result.py       # DiagnosisResponse TypedDict
│   └── trace.py        # ExplanationBuilder (reasoning traces)
│
├── utils/              # Generic helpers
│   ├── text.py         # slugify and text normalization
│   └── scoring.py      # CF combination formula, confidence labels
│
├── hierarchy.py        # 6-level hierarchy tree builder
├── llm_fallback.py     # LLM fallback when KB has no match
│
└── (compatibility wrappers)
    ├── engine.py        # Re-exports from inference/engine.py
    ├── matcher.py       # Re-exports from inference/fuzzy.py
    ├── procedure.py     # Re-exports from inference/procedure.py
    ├── policy.py        # Re-exports from inference/policy.py
    ├── knowledge_base.py # Re-exports from knowledge/loader.py
    └── schemas.py       # Re-exports from knowledge/schema.py + runtime/result.py
```

## Key Concepts

- **Inference logic** lives in `inference/`. The engine orchestrates; each algorithm has its own module.
- **Fuzzy matching** (`fuzzy.py`) normalizes user text to KB symptom IDs using rapidfuzz.
- **Certainty factor scoring** (`certainty.py`) ranks faults using MYCIN-style CF combination.
- **Question selection** (`question.py`) picks the next symptom to ask via entropy-based information gain.
- **Procedure trees** (`procedure.py`) navigate fault-specific step-by-step diagnostic flows.
- **Policy** (`policy.py`) enforces final decision rules on the response payload.
- **Compatibility wrappers** at the root level ensure that old import paths (used by backend/tests) still work.

## Rules

- Do NOT put build/validation scripts here. Those belong in `scripts/`.
- Do NOT import from `src/legacy/` in runtime code.
- Keep this package free of side effects (no file writes, no API calls except in `llm_fallback.py`).
