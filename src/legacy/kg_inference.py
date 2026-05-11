from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT
from src.expert_system.engine import ExpertSystemEngine, load_cf_map
from src.expert_system.knowledge_base import KnowledgeBase, extract_rules, load_json
from src.expert_system.matcher import MATCH_THRESHOLD, SymptomMatcher


DEFAULT_ALIAS_PATH = PROJECT_ROOT / "data" / "staging" / "symptom_aliases.json"
DEFAULT_RULES_PATH = PROJECT_ROOT / "data" / "staging" / "kg_rules_from_dataset.json"


class KGInference:
    """Compatibility facade for the hierarchical ExpertSystemEngine."""

    def __init__(
        self,
        matcher: SymptomMatcher,
        rules: list[dict[str, Any]] | None = None,
        driver: Any | None = None,
    ):
        self.matcher = matcher
        self.rules = rules or []
        self.cf_map = load_cf_map(self.rules)
        self.driver = driver
        self.kb = KnowledgeBase.from_data(symptom_aliases=matcher.symptoms, rules=self.rules)
        self.engine = ExpertSystemEngine(self.kb)

    @classmethod
    def from_files(
        cls,
        aliases_path: str | Path = DEFAULT_ALIAS_PATH,
        rules_path: str | Path = DEFAULT_RULES_PATH,
    ) -> "KGInference":
        aliases = load_json(aliases_path)
        rules = extract_rules(load_json(rules_path))
        return cls(SymptomMatcher(aliases), rules=rules)

    @classmethod
    def from_neo4j(
        cls,
        aliases_path: str | Path = DEFAULT_ALIAS_PATH,
    ) -> "KGInference":
        # Runtime diagnosis is staging-file authoritative in this refactor.
        # Neo4j remains available for graph/import workflows.
        return cls.from_files(aliases_path=aliases_path)

    def close(self) -> None:
        if self.driver is not None:
            self.driver.close()

    def diagnose(
        self,
        text: str,
        top_k: int = 5,
        confirmed_symptoms: list[str] | None = None,
        rejected_symptoms: list[str] | None = None,
        session: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.engine.diagnose(
            text,
            top_k=top_k,
            confirmed_symptoms=confirmed_symptoms,
            rejected_symptoms=rejected_symptoms,
            session=session,
        )
