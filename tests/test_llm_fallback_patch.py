"""Tests for LLM fallback integration with DiagnosisService (unified diagnose contract)."""
import json
from pathlib import Path
from unittest.mock import patch

from src.expert_system.llm_fallback import diagnose_with_llm, validate_decision_tree
from backend.services.diagnosis_service import (
    llm_response,
    _extract_patch_next_question,
)


SAMPLE_PATCH = {
    "review_type": "llm_kb_patch",
    "needs_expert_review": True,
    "source": "llm_fallback",
    "user_input": "máy rung khi garanti",
    "suggested_mapping": {
        "system_id": "SYS_ENGINE",
        "primary_symptom_id": "SYM_ENGINE_ROUGH_IDLE",
        "primary_symptom_label": "Engine rough idle",
        "aliases": ["máy rung khi garanti", "động cơ rung lúc đứng yên"],
    },
    "candidate_faults": [
        {
            "fault_id": "FAULT_ENGINE_MOUNT_WORN",
            "fault_name": "engine_mount_worn",
            "fault_label": "Engine mount worn",
            "cf": 0.35,
            "symptoms": [
                {"symptom_id": "SYM_ENGINE_ROUGH_IDLE", "cf": 0.35, "priority": 1}
            ],
            "resolution": {
                "parts": ["engine mount"],
                "tools": [],
                "procedure": "Inspect engine mounts for cracks.",
                "difficulty": "expert_review_required",
                "labor_hours": None,
            },
        }
    ],
    "procedure_trees": {
        "FAULT_ENGINE_MOUNT_WORN": {
            "fault_id": "FAULT_ENGINE_MOUNT_WORN",
            "fault_name": "engine_mount_worn",
            "entry_step": "engine_mount_worn_s1",
            "steps": {
                "engine_mount_worn_s1": {
                    "id": "engine_mount_worn_s1",
                    "symptom_id": "SYM_ENGINE_VIBRATION_IDLE",
                    "symptom_label": "Vibration at idle",
                    "question": "Does the vehicle vibrate strongly when idling?",
                    "is_question": True,
                    "yes_next": "engine_mount_worn_s2",
                    "no_next": "REFUTED",
                    "results": [],
                },
                "engine_mount_worn_s2": {
                    "id": "engine_mount_worn_s2",
                    "symptom_id": "SYM_ENGINE_MOUNT_DAMAGE",
                    "symptom_label": "Engine mount damage",
                    "question": "Are the engine mounts cracked or damaged?",
                    "is_question": True,
                    "yes_next": "DIAGNOSED",
                    "no_next": "REFUTED",
                    "results": [],
                },
            },
        }
    },
    "review_notes": {
        "reason": "Generated because no existing symptom matched.",
        "confidence_limit": "LLM suggestion only.",
    },
}


class TestLLMFallback:
    def test_diagnose_with_llm_without_api_key_returns_tree_candidate(self):
        with patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
            result = diagnose_with_llm("xe bị rung mạnh", session={})
        assert result["status"] == "pending_expert_review"
        assert result.get("candidate", {}).get("tree", {}).get("nodes")
        ok, _errors = validate_decision_tree(result["candidate"])
        assert ok


class TestDiagnosisServiceFallback:
    def test_llm_response_has_empty_official_fields(self):
        with patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
            resp = llm_response("xe bị rung mạnh")
        assert resp["diagnoses"] == []
        assert resp["results"] == []
        assert resp["candidate_faults"] == []
        assert resp["current_hypotheses"] == []
        assert resp["is_final"] is False
        assert resp["status"] == "need_more_info"
        assert resp["source"] == "llm_fallback"
        assert resp.get("next_question", {}).get("question")

    def test_llm_response_with_candidate_skips_llm_call(self):
        with patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
            cand = diagnose_with_llm("test", session={})["candidate"]
        with patch("backend.services.diagnosis_service.diagnose_with_llm") as mock_dm:
            resp = llm_response("ignored", session={}, candidate=cand, reason="test")
            mock_dm.assert_not_called()
        assert resp["status"] == "need_more_info"
        assert resp["next_question"]["question"]

    def test_llm_response_has_next_question_when_mock_returns_minimal_tree(self):
        fake_tree = {
            "type": "diagnostic_decision_tree",
            "candidate_id": "t1",
            "tree": {
                "root_node_id": "q1",
                "nodes": [
                    {
                        "node_id": "q1",
                        "type": "question",
                        "question": "Tiếng kêu ở đâu?",
                        "answer_type": "yes_no",
                        "yes_next": "r1",
                        "no_next": "r1",
                        "unknown_next": "r1",
                    },
                    {
                        "node_id": "r1",
                        "type": "result",
                        "fault": {"fault_id": "f1", "fault_name": "F", "confidence": 0.5},
                        "components": [],
                        "causes": [],
                        "diagnostic_steps": ["a"],
                        "repair_steps": ["b"],
                        "safety_notes": [],
                        "when_to_stop": [],
                    },
                    {
                        "node_id": "r2",
                        "type": "result",
                        "fault": {"fault_id": "f2", "fault_name": "F2", "confidence": 0.4},
                        "components": [],
                        "causes": [],
                        "diagnostic_steps": ["a"],
                        "repair_steps": ["b"],
                        "safety_notes": [],
                        "when_to_stop": [],
                    },
                    {
                        "node_id": "r3",
                        "type": "result",
                        "fault": {"fault_id": "f3", "fault_name": "F3", "confidence": 0.3},
                        "components": [],
                        "causes": [],
                        "diagnostic_steps": ["a"],
                        "repair_steps": ["b"],
                        "safety_notes": [],
                        "when_to_stop": [],
                    },
                ],
            },
        }
        with patch("backend.services.diagnosis_service.diagnose_with_llm") as mock_dm:
            mock_dm.return_value = {"candidate": fake_tree, "status": "pending_expert_review"}
            resp = llm_response("xe kêu to")
        nq = resp.get("next_question")
        assert nq is not None
        assert nq["question"] == "Tiếng kêu ở đâu?"
        assert resp["status"] == "need_more_info"

    def test_extract_patch_next_question(self):
        q = _extract_patch_next_question(SAMPLE_PATCH)
        assert q is not None
        assert q["question"] == "Does the vehicle vibrate strongly when idling?"
        assert q["answer_type"] == "yes_no"
        assert q["source"] == "llm_fallback_procedure_tree"
        assert q["fault_id"] == "FAULT_ENGINE_MOUNT_WORN"
        assert q["step_id"] == "engine_mount_worn_s1"

    def test_extract_patch_next_question_empty(self):
        assert _extract_patch_next_question({}) is None
        assert _extract_patch_next_question({"procedure_trees": {}, "candidate_faults": []}) is None

