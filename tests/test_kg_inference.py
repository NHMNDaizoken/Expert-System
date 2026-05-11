import unittest

from src.kg_inference import KGInference, SymptomMatcher, extract_rules


ALIASES = {
    "SYM_CLICKING_SOUND": {
        "name": "clicking_sound",
        "display_name": "Clicking Sound",
        "aliases": ["clicking noise", "clicking sound when starting"],
    },
    "SYM_DIM_LIGHTS": {
        "name": "dim_lights",
        "display_name": "Dim Lights",
        "aliases": ["dim headlights", "dashboard lights dim"],
    },
}

RULES = [
    {
        "fault_id": "FLT_WEAK_BATTERY",
        "fault_name": "weak_battery",
        "display_name": "Weak Battery",
        "system_id": "SYS_ELECTRICAL",
        "affected_components": ["CMP_BATTERY"],
        "symptoms": [
            {"symptom_id": "SYM_CLICKING_SOUND", "cf": 0.6, "priority": 2},
            {"symptom_id": "SYM_DIM_LIGHTS", "cf": 0.9, "priority": 1},
        ],
        "repairs": [
            {
                "repair_id": "REP_REPLACE_BATTERY",
                "repair_name": "replace_battery",
            }
        ],
    },
    {
        "fault_id": "FLT_STARTER",
        "fault_name": "starter",
        "display_name": "Starter",
        "system_id": "SYS_ELECTRICAL",
        "affected_components": ["CMP_STARTER"],
        "symptoms": [
            {"symptom_id": "SYM_CLICKING_SOUND", "cf": 0.7, "priority": 1},
        ],
        "repairs": [],
    },
]


class KGInferenceTest(unittest.TestCase):
    def test_extract_rules_accepts_list_and_wrapped_rules(self):
        self.assertEqual(extract_rules(RULES), RULES)
        self.assertEqual(extract_rules({"rules": RULES}), RULES)

    def test_diagnose_matches_multiple_symptoms_and_keeps_hypotheses_until_clear(self):
        inference = KGInference(SymptomMatcher(ALIASES), rules=RULES)

        response = inference.diagnose(
            "clicking noise when starting and dim headlights",
            top_k=2,
        )

        self.assertEqual(response["status"], "need_more_info")
        self.assertFalse(response["is_final"])
        self.assertEqual(
            {symptom["symptom_id"] for symptom in response["matched_symptoms"]},
            {"SYM_CLICKING_SOUND", "SYM_DIM_LIGHTS"},
        )
        self.assertEqual(response["diagnoses"][0]["fault_id"], "FLT_WEAK_BATTERY")

    def test_diagnose_returns_next_question_for_ambiguous_faults(self):
        inference = KGInference(SymptomMatcher(ALIASES), rules=RULES)

        response = inference.diagnose("clicking noise when starting", top_k=2)

        self.assertEqual(response["status"], "need_more_info")
        self.assertFalse(response["is_final"])
        self.assertEqual(
            response["next_question"]["symptom_id"],
            "SYM_DIM_LIGHTS",
        )
        self.assertEqual(response["current_hypotheses"][0]["fault_id"], "FLT_STARTER")


if __name__ == "__main__":
    unittest.main()
