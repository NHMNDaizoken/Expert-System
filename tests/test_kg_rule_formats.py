import json
import tempfile
import unittest
from pathlib import Path

from src.kg_validator import validate_all


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = ROOT / "data" / "staging" / "ontology.json"
SYMPTOM_ALIASES_PATH = ROOT / "data" / "staging" / "symptom_aliases.json"
RULES_PATH = ROOT / "data" / "staging" / "kg_rules_from_dataset.json"


class KGRuleFormatTest(unittest.TestCase):
    def test_validate_all_accepts_top_level_list(self):
        validate_all(ONTOLOGY_PATH, SYMPTOM_ALIASES_PATH, RULES_PATH)

    def test_validate_all_accepts_rules_wrapper(self):
        with RULES_PATH.open("r", encoding="utf-8") as f:
            rules = json.load(f)

        with tempfile.TemporaryDirectory() as tmp_dir:
            wrapped_rules_path = Path(tmp_dir) / "kg_rules_wrapped.json"
            with wrapped_rules_path.open("w", encoding="utf-8") as f:
                json.dump({"rules": rules}, f)

            validate_all(ONTOLOGY_PATH, SYMPTOM_ALIASES_PATH, wrapped_rules_path)


if __name__ == "__main__":
    unittest.main()
