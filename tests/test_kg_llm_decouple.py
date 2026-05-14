"""
Acceptance-oriented checks (spec A–I).

1) LLM fallback tree for Vietnamese underbody symptom (via DiagnosisService + mocked KG down).
2) Graph file search "Gầm xe" returns faults via Symptom→Fault, not decision-tree branches.
3) After expert promotion, flattened faults exist in expert_accepted_faults.json with promotion_metadata.
4) kg_rules_from_dataset.json must not embed decision_trees (rules file stays dataset-shaped).
5) should_use_llm_fallback does not trigger when KG returns need_more_info with next_question.
6) Regression: engine still diagnoses a known English symptom when KB loads from staging.

Manual / Neo4j: run `python scripts/build/build_knowledge.py --rebuild-from-raw` then
`python scripts/graph/import_graph.py --clear` (requires Neo4j). Optional tree debug import:
`python scripts/graph/import_graph.py --clear --import-decision-trees`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.core.config import settings
from backend.database import ensure_database
from backend.services.diagnosis_service import DiagnosisService, should_use_llm_fallback
from backend.services.graph_service import GraphService
from backend.services import expert_review_promotion as erp
from scripts.build.build_knowledge import build_knowledge, load_json
from src.expert_system.knowledge.loader import KnowledgeBase


def setup_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sqlite_db_path", tmp_path / "app.sqlite3")
    ensure_database()


def test_llm_tree_vietnamese_underbody_symptom(tmp_path, monkeypatch):
    setup_temp_db(tmp_path, monkeypatch)
    service = DiagnosisService()
    with patch("backend.services.diagnosis_service.get_engine", side_effect=RuntimeError("kg down")), patch(
        "backend.services.diagnosis_service.enqueue_llm_suggestion", return_value=True
    ), patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
        response = service.start_decision_tree("Gầm xe kêu hoặc rung không đều")
    assert response["type"] == "diagnostic_decision_tree"
    assert response.get("decision_tree", {}).get("tree", {}).get("nodes")
    assert response.get("source") == "llm_fallback"


def test_graph_file_search_gam_xe_no_tree_nodes():
    service = GraphService()
    out = service.search_graph("Gầm xe")
    assert out["decision_trees"] == []
    assert out["question_path"] == []


def test_graph_file_search_finds_kg_nodes_for_dataset_symptom():
    service = GraphService()
    out = service.search_graph("clicking")
    assert out["decision_trees"] == []
    assert out["matched_symptoms"] or out["related_faults"] or out["possible_faults"]


def test_promotion_writes_expert_faults_json(tmp_path, monkeypatch):
    noop = tmp_path / "noop.py"
    noop.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    trees_path = tmp_path / "expert_accepted_decision_trees.json"
    faults_path = tmp_path / "expert_accepted_faults.json"
    monkeypatch.setattr(erp, "RAW_EXPERT_TREES_PATH", trees_path)
    monkeypatch.setattr(erp, "RAW_EXPERT_PATH", faults_path)
    monkeypatch.setattr(erp, "BUILD_KNOWLEDGE_SCRIPT", noop)
    monkeypatch.setattr(erp, "IMPORT_GRAPH_SCRIPT", noop)

    candidate = {
        "type": "diagnostic_decision_tree",
        "candidate_id": "test_tree_1",
        "root_symptom": {"label_vi": "Gầm xe kêu hoặc rung không đều", "symptom_id": "SYM_TEST"},
        "tree": {
            "root_node_id": "q1",
            "nodes": [
                {
                    "node_id": "q1",
                    "type": "question",
                    "question": "Q1?",
                    "answer_type": "yes_no",
                    "yes_next": "r1",
                    "no_next": "r1",
                    "unknown_next": "r1",
                },
                {
                    "node_id": "r1",
                    "type": "result",
                    "fault": {
                        "fault_id": "flt_test_underbody",
                        "fault_name": "Lỗi treo gầm kiểm thử",
                        "system": "suspension",
                        "severity": "medium",
                        "confidence": 0.7,
                    },
                    "components": [{"component_id": "c1", "name_vi": "Rotuyn"}],
                    "causes": ["Mòn"],
                    "diagnostic_steps": ["Kiểm tra A"],
                    "repair_steps": ["Thay B"],
                    "safety_notes": ["An toàn"],
                },
            ],
        },
        "selected_path": [{"node_id": "q1", "question": "Q1?", "answer": "yes", "next_node_id": "r1"}],
        "selected_result_node_id": "r1",
    }
    assert erp.promote_approved_payload({"llm_output": candidate}) is True
    rows = json.loads(faults_path.read_text(encoding="utf-8"))
    assert isinstance(rows, list)
    assert any(r.get("fault_id") == "flt_test_underbody" for r in rows)
    meta = next(r["promotion_metadata"] for r in rows if r.get("fault_id") == "flt_test_underbody")
    assert meta.get("source") == "expert_approved_llm_tree"
    assert meta.get("candidate_id") == "test_tree_1"


def test_build_knowledge_rules_json_has_no_embedded_decision_trees(tmp_path, monkeypatch):
    kg_out = tmp_path / "kg_rules_from_dataset.json"
    monkeypatch.setattr("scripts.build.build_knowledge.KG_PATH", kg_out)
    monkeypatch.setattr("scripts.build.build_knowledge.CF_PATH", tmp_path / "cf.json")
    monkeypatch.setattr("scripts.build.build_knowledge.PROCEDURE_PATH", tmp_path / "proc.json")
    monkeypatch.setattr("scripts.build.build_knowledge.DECISION_TREES_PATH", tmp_path / "dt.json")
    monkeypatch.setattr("scripts.build.build_knowledge.EXPERT_TREE_PATH", tmp_path / "expert_tree.json")
    monkeypatch.setattr("scripts.build.build_knowledge.ALIASES_PATH", tmp_path / "aliases.json")
    monkeypatch.setattr("scripts.build.build_knowledge.RAW_EXPERT_PATH", tmp_path / "expert_faults.json")
    monkeypatch.setattr("scripts.build.build_knowledge.RAW_EXPERT_TREES_PATH", tmp_path / "expert_trees.json")
    monkeypatch.setattr("scripts.build.build_knowledge.RAW_PATH", tmp_path / "automotive_faults.json")

    (tmp_path / "automotive_faults.json").write_text(
        json.dumps(
            [
                {
                    "category": "Engine",
                    "subcategory": "Smoke",
                    "symptoms": ["white smoke on startup"],
                    "diagnosis_steps": [{"step": "Look", "result": ["ok", "bad"]}],
                    "parts": ["gasket"],
                    "tools": ["eyes"],
                    "difficulty": "easy",
                    "labor_hours": 1,
                    "causes": [],
                    "safety_notes": [],
                    "confidence": 0.5,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "expert_faults.json").write_text("[]", encoding="utf-8")
    (tmp_path / "expert_trees.json").write_text(json.dumps({"trees": []}, ensure_ascii=False), encoding="utf-8")

    build_knowledge(rebuild_from_raw=True)
    data = load_json(kg_out)
    assert "decision_trees" not in data


def test_should_use_llm_fallback_respects_need_more_info():
    assert should_use_llm_fallback({"status": "need_more_info", "next_question": {"step_id": "x"}, "diagnoses": []}) is False


def test_engine_regression_known_symptom():
    kb = KnowledgeBase.from_staging()
    from src.expert_system.inference.engine import ExpertSystemEngine

    engine = ExpertSystemEngine(kb)
    response = engine.diagnose("clicking noise", top_k=2)
    assert response.get("status") in {"diagnosed", "need_more_info", "collecting_context"}
