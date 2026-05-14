"""Tests for LLM fallback → KB patch → expert promotion → normal KG flow."""
import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.expert_system.llm_fallback import (
    diagnose_with_llm,
    validate_llm_kb_patch,
    validate_procedure_tree,
    build_kb_context,
    _offline_response,
)
from backend.services.diagnosis_service import (
    llm_response,
    _extract_patch_next_question,
    should_use_llm_fallback,
)
from backend.services.expert_review_promotion import (
    promote_llm_kb_patch,
    promote_approved_payload,
    _check_alias_conflicts,
)


# ---------------------------------------------------------------------------
# Sample llm_kb_patch fixture
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 1. Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_patch_passes(self):
        ok, errors = validate_llm_kb_patch(SAMPLE_PATCH)
        assert ok, f"Expected valid but got errors: {errors}"

    def test_missing_review_type(self):
        bad = {**SAMPLE_PATCH, "review_type": "wrong"}
        ok, errors = validate_llm_kb_patch(bad)
        assert not ok
        assert any("review_type" in e for e in errors)

    def test_high_cf_rejected(self):
        bad = copy.deepcopy(SAMPLE_PATCH)
        bad["candidate_faults"][0]["cf"] = 0.9
        ok, errors = validate_llm_kb_patch(bad)
        assert not ok
        assert any("exceeds" in e for e in errors)

    def test_missing_entry_step_in_procedure(self):
        bad = copy.deepcopy(SAMPLE_PATCH)
        del bad["procedure_trees"]["FAULT_ENGINE_MOUNT_WORN"]["entry_step"]
        ok, errors = validate_procedure_tree(bad["procedure_trees"]["FAULT_ENGINE_MOUNT_WORN"])
        assert not ok

    def test_broken_step_link(self):
        bad_tree = {
            "entry_step": "s1",
            "steps": {
                "s1": {"id": "s1", "question": "Q?", "yes_next": "missing", "no_next": "REFUTED"}
            },
        }
        ok, errors = validate_procedure_tree(bad_tree)
        assert not ok
        assert any("missing" in e for e in errors)


# ---------------------------------------------------------------------------
# 2. Offline fallback tests
# ---------------------------------------------------------------------------

class TestLLMFallback:
    def test_diagnose_with_llm_without_api_key(self):
        """Without API key, should return an error or status indicating missing key."""
        # Mocking _has_api_key to return False if needed, or assuming it's False in CI
        with patch("src.expert_system.llm_fallback._has_api_key", return_value=False):
            result = diagnose_with_llm("xe bị rung mạnh", session={})
            assert result["status"] == "error"
            assert "API Key" in result["error"]

    @patch("src.expert_system.llm_fallback._get_model")
    def test_diagnose_with_llm_flow(self, mock_get_model):
        """Test the flow where LLM asks a question first."""
        mock_model = mock_get_model.return_value
        mock_model.generate_content.return_value.text = json.dumps({
            "next_question": "Tiếng kêu xuất hiện khi nào?"
        })
        
        with patch("src.expert_system.llm_fallback._has_api_key", return_value=True):
            result = diagnose_with_llm("xe kêu to", session={"asked_questions": []})
            assert result["status"] == "need_more_info"
            assert "next_question" in result["next_question"]
            assert result["asked_question_text"] == "Tiếng kêu xuất hiện khi nào?"


# ---------------------------------------------------------------------------
# 3. diagnosis_service fallback response tests
# ---------------------------------------------------------------------------

class TestDiagnosisServiceFallback:
    def test_llm_response_has_empty_official_fields(self):
        resp = llm_response("xe bị rung mạnh")
        assert resp["diagnoses"] == []
        assert resp["results"] == []
        assert resp["candidate_faults"] == []
        assert resp["current_hypotheses"] == []
        assert resp["is_final"] is False
        assert resp["status"] == "need_more_info"
        assert resp["source"] == "llm_fallback"

    def test_llm_response_has_patch_suggestion(self):
        # We need to mock diagnose_with_llm to return a pending_expert_review status
        with patch("backend.services.diagnosis_service.diagnose_with_llm") as mock_fallback:
            mock_fallback.return_value = {
                "status": "pending_expert_review",
                "candidate": {"faults": []},
                "llm_candidate_generated": True
            }
            resp = llm_response("xe bị rung mạnh")
            assert "llm_patch_suggestion" in resp
            assert resp["llm_candidate_generated"] is True
            assert resp["status"] == "pending_expert_review"

    def test_llm_response_has_next_question(self):
        with patch("backend.services.diagnosis_service.diagnose_with_llm") as mock_fallback:
            mock_fallback.return_value = {
                "status": "need_more_info",
                "next_question": {"question": "Tiếng kêu ở đâu?"},
                "asked_question_text": "Tiếng kêu ở đâu?"
            }
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


# ---------------------------------------------------------------------------
# 4. Expert review promotion tests
# ---------------------------------------------------------------------------

class TestPromotion:
    def _make_temp_staging(self, tmp_path):
        """Create temp staging dir with empty KB files and patch module paths."""
        staging = tmp_path / "data" / "staging"
        staging.mkdir(parents=True)
        (staging / "symptom_aliases.json").write_text("{}", encoding="utf-8")
        (staging / "kg_rules_from_dataset.json").write_text(
            json.dumps({"meta": {}, "rules": []}), encoding="utf-8"
        )
        (staging / "procedure_trees.json").write_text("{}", encoding="utf-8")
        (staging / "expert_tree.json").write_text(
            json.dumps({"meta": {}, "systems": {}}), encoding="utf-8"
        )
        return staging

    def test_promote_llm_kb_patch_writes_all_files(self, tmp_path):
        staging = self._make_temp_staging(tmp_path)
        import backend.services.expert_review_promotion as mod

        original_paths = (mod.ALIASES_PATH, mod.RULES_PATH, mod.PROCEDURES_PATH, mod.EXPERT_TREE_PATH)
        mod.ALIASES_PATH = staging / "symptom_aliases.json"
        mod.RULES_PATH = staging / "kg_rules_from_dataset.json"
        mod.PROCEDURES_PATH = staging / "procedure_trees.json"
        mod.EXPERT_TREE_PATH = staging / "expert_tree.json"

        try:
            result = promote_llm_kb_patch(SAMPLE_PATCH)
            assert result["imported"] is True
            assert result["errors"] == []

            # Verify aliases
            aliases = json.loads((staging / "symptom_aliases.json").read_text(encoding="utf-8"))
            assert "SYM_ENGINE_ROUGH_IDLE" in aliases
            assert "máy rung khi garanti" in aliases["SYM_ENGINE_ROUGH_IDLE"]["aliases"]

            # Verify rules
            rules_doc = json.loads((staging / "kg_rules_from_dataset.json").read_text(encoding="utf-8"))
            rules = rules_doc["rules"]
            assert any(r["fault_id"] == "FAULT_ENGINE_MOUNT_WORN" for r in rules)

            # Verify procedure trees
            procs = json.loads((staging / "procedure_trees.json").read_text(encoding="utf-8"))
            assert "FAULT_ENGINE_MOUNT_WORN" in procs

            # Verify expert tree
            etree = json.loads((staging / "expert_tree.json").read_text(encoding="utf-8"))
            sys_engine = etree.get("systems", {}).get("SYS_ENGINE", {})
            assert "SYM_ENGINE_ROUGH_IDLE" in sys_engine.get("primary_symptoms", {})
        finally:
            mod.ALIASES_PATH, mod.RULES_PATH, mod.PROCEDURES_PATH, mod.EXPERT_TREE_PATH = original_paths

    def test_duplicate_fault_blocked_without_overwrite(self, tmp_path):
        staging = self._make_temp_staging(tmp_path)
        import backend.services.expert_review_promotion as mod

        original_paths = (mod.ALIASES_PATH, mod.RULES_PATH, mod.PROCEDURES_PATH, mod.EXPERT_TREE_PATH)
        mod.ALIASES_PATH = staging / "symptom_aliases.json"
        mod.RULES_PATH = staging / "kg_rules_from_dataset.json"
        mod.PROCEDURES_PATH = staging / "procedure_trees.json"
        mod.EXPERT_TREE_PATH = staging / "expert_tree.json"

        try:
            # First import succeeds
            result1 = promote_llm_kb_patch(SAMPLE_PATCH)
            assert result1["imported"] is True

            # Second import blocked
            result2 = promote_llm_kb_patch(SAMPLE_PATCH)
            assert result2["imported"] is False
            assert any("already exists" in e for e in result2["errors"])

            # With overwrite allowed
            result3 = promote_llm_kb_patch(SAMPLE_PATCH, allow_overwrite=True)
            assert result3["imported"] is True
        finally:
            mod.ALIASES_PATH, mod.RULES_PATH, mod.PROCEDURES_PATH, mod.EXPERT_TREE_PATH = original_paths

    def test_alias_conflict_blocked(self):
        aliases = {
            "SYM_OTHER": {
                "symptom_id": "SYM_OTHER",
                "aliases": ["máy rung khi garanti"],
            }
        }
        errors = _check_alias_conflicts(aliases, "SYM_ENGINE_ROUGH_IDLE", ["máy rung khi garanti"])
        assert len(errors) == 1
        assert "already mapped" in errors[0]

    def test_promote_via_main_function_routes_correctly(self, tmp_path):
        staging = self._make_temp_staging(tmp_path)
        import backend.services.expert_review_promotion as mod

        original_paths = (mod.ALIASES_PATH, mod.RULES_PATH, mod.PROCEDURES_PATH, mod.EXPERT_TREE_PATH)
        mod.ALIASES_PATH = staging / "symptom_aliases.json"
        mod.RULES_PATH = staging / "kg_rules_from_dataset.json"
        mod.PROCEDURES_PATH = staging / "procedure_trees.json"
        mod.EXPERT_TREE_PATH = staging / "expert_tree.json"

        try:
            result = promote_approved_payload(SAMPLE_PATCH)
            assert result is True
        finally:
            mod.ALIASES_PATH, mod.RULES_PATH, mod.PROCEDURES_PATH, mod.EXPERT_TREE_PATH = original_paths


# ---------------------------------------------------------------------------
# 5. KB context loader test
# ---------------------------------------------------------------------------

class TestKBContext:
    def test_build_kb_context_returns_expected_keys(self):
        ctx = build_kb_context("xe bị rung mạnh")
        assert "existing_symptom_ids" in ctx
        assert "existing_fault_ids" in ctx
        assert "nearby_aliases" in ctx
        assert "inferred_system" in ctx
        assert "sample_procedure_tree" in ctx
