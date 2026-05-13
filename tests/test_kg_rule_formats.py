import json
import tempfile
import unittest
from pathlib import Path

from src.expert_system.knowledge.loader import KnowledgeBase, load_json, extract_rules
from src.expert_system.knowledge.schema import ExpertSystemValidator


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = ROOT / "data" / "staging" / "ontology.json"
SYMPTOM_ALIASES_PATH = ROOT / "data" / "staging" / "symptom_aliases.json"
RULES_PATH = ROOT / "data" / "staging" / "kg_rules_from_dataset.json"


class KGRuleFormatTest(unittest.TestCase):
    def test_extract_rules_accepts_list_and_wrapped_rules(self):
        # Restore test for extract_rules utility function
        rules = [{"id": "R1"}]
        self.assertEqual(extract_rules(rules), rules)
        self.assertEqual(extract_rules({"rules": rules}), rules)

    def test_validate_all_accepts_top_level_list(self):
        ontology = load_json(ONTOLOGY_PATH)
        aliases = load_json(SYMPTOM_ALIASES_PATH)
        rules = extract_rules(load_json(RULES_PATH))
        kb = KnowledgeBase(ontology=ontology, symptom_aliases=aliases, rules=rules)
        report = ExpertSystemValidator(kb).validate()
        self.assertTrue(report.ok)

    def test_validate_all_accepts_rules_wrapper(self):
        with RULES_PATH.open("r", encoding="utf-8") as f:
            rules_raw = json.load(f)

        with tempfile.TemporaryDirectory() as tmp_dir:
            wrapped_rules_path = Path(tmp_dir) / "kg_rules_wrapped.json"
            with wrapped_rules_path.open("w", encoding="utf-8") as f:
                json.dump({"rules": rules_raw}, f)

            ontology = load_json(ONTOLOGY_PATH)
            aliases = load_json(SYMPTOM_ALIASES_PATH)
            rules = extract_rules(load_json(wrapped_rules_path))
            kb = KnowledgeBase(ontology=ontology, symptom_aliases=aliases, rules=rules)
            report = ExpertSystemValidator(kb).validate()
            self.assertTrue(report.ok)


if __name__ == "__main__":
    unittest.main()
