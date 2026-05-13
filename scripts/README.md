# Scripts — Build, Validation, Evaluation, and Developer Tools

This directory contains scripts for building, validating, evaluating, and
maintaining the expert-system knowledge base. These are **not** runtime
inference code — they are developer/CI tools.

## Structure

```
scripts/
├── build/                    # Knowledge base construction
│   ├── build_knowledge.py    # Build all staging artifacts from raw data
│   ├── translate_vi.py       # Translate English terms to Vietnamese via Gemini
│   └── rebuild_hierarchy.py  # Rebuild the 6-level expert tree
│
├── validate/                 # Knowledge base validation
│   └── validate_knowledge.py # Validate staging data integrity
│
├── evaluate/                 # Diagnostic evaluation
│   └── evaluate_diagnosis.py # Run test cases and measure accuracy
│
├── graph/                    # Neo4j graph import
│   ├── import_graph.py       # Import knowledge graph into Neo4j
│   └── import_neo4j.py       # Shortcut entry point for Neo4j import
│
├── dev/                      # Developer utilities
│   ├── dev_checks.py         # Manual development checks (normalizer, rules, inference)
│   ├── check_imports.py      # Verify old/new import paths work correctly
│   └── smoke_test.py         # Quick sanity check of the engine
│
├── (original scripts)        # Original scripts remain at scripts/ root
│   ├── build_knowledge.py
│   ├── translate_vi.py
│   ├── rebuild_hierarchy.py
│   ├── validate_knowledge.py
│   ├── evaluate_diagnosis.py
│   ├── import_graph.py
│   ├── import_neo4j.py
│   └── dev_checks.py
│
└── _bootstrap.py             # Adds project root to sys.path
```

## Running Scripts

All scripts can be run from the project root:

```bash
# New organized paths
python scripts/build/build_knowledge.py
python scripts/validate/validate_knowledge.py
python scripts/evaluate/evaluate_diagnosis.py
python scripts/graph/import_graph.py
python scripts/dev/check_imports.py
python scripts/dev/smoke_test.py

# Original paths also still work
python scripts/build_knowledge.py
python scripts/validate_knowledge.py
```

## Rules

- Scripts must NOT contain runtime inference logic.
- Runtime inference logic lives in `src/expert_system/`.
- Scripts in subdirectories are thin wrappers that bootstrap and delegate to the originals.
- Original scripts at the root level are preserved for backward compatibility.
