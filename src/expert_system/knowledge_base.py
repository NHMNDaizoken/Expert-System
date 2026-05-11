from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import re
from typing import Any

from src.config import PROJECT_ROOT


DEFAULT_STAGING_DIR = PROJECT_ROOT / "data" / "staging"


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def extract_rules(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "rules" in data:
        return extract_rules(data["rules"])
    return []


class KnowledgeBase:
    """Read-only access layer over the staging expert-system data."""

    def __init__(
        self,
        *,
        ontology: dict[str, Any] | None = None,
        symptom_aliases: dict[str, dict[str, Any]] | None = None,
        rules: list[dict[str, Any]] | None = None,
        cf_dynamic: dict[str, Any] | None = None,
        procedure_trees: dict[str, Any] | None = None,
    ):
        self.ontology = ontology or {"vehicle_systems": []}
        self.symptom_aliases = symptom_aliases or {}
        self.rules = rules or []
        self.cf_dynamic = cf_dynamic or {}
        self.procedure_trees = procedure_trees or {}

        self.systems = self._index_systems(self.ontology)
        self.faults = {rule.get("fault_id"): rule for rule in self.rules if rule.get("fault_id")}
        self.rules_by_symptom = self._index_rules_by_symptom(self.rules)
        self.rules_by_system_symptom = self._index_rules_by_system_symptom(self.rules)
        self.cf_map = self._build_cf_map()

    @classmethod
    def from_staging(cls, staging_dir: str | Path = DEFAULT_STAGING_DIR) -> "KnowledgeBase":
        base = Path(staging_dir)
        return cls(
            ontology=load_json(base / "ontology.json"),
            symptom_aliases=load_json(base / "symptom_aliases.json"),
            rules=extract_rules(load_json(base / "kg_rules_from_dataset.json")),
            cf_dynamic=load_json(base / "cf_dynamic.json"),
            procedure_trees=load_json(base / "procedure_trees.json"),
        )

    @classmethod
    def from_data(
        cls,
        *,
        symptom_aliases: dict[str, dict[str, Any]],
        rules: list[dict[str, Any]],
        ontology: dict[str, Any] | None = None,
    ) -> "KnowledgeBase":
        return cls(ontology=ontology, symptom_aliases=symptom_aliases, rules=rules)

    def get_systems(self) -> list[dict[str, Any]]:
        return list(self.systems.values())

    def get_symptom(self, symptom_id: str) -> dict[str, Any] | None:
        return self.symptom_aliases.get(symptom_id)

    def get_fault(self, fault_id: str) -> dict[str, Any] | None:
        return self.faults.get(fault_id)

    def get_rules_for_symptom(self, symptom_id: str) -> list[dict[str, Any]]:
        return self.rules_by_symptom.get(symptom_id, [])

    def get_procedure_for_fault(self, fault_id: str) -> dict[str, Any] | None:
        rule = self.get_fault(fault_id) or {}
        return rule.get("procedure") or self.procedure_trees.get(fault_id)

    def get_candidate_faults(self, system_id: str | None, symptom_id: str) -> list[dict[str, Any]]:
        explicit = self._explicit_candidate_faults(symptom_id)
        if explicit:
            return explicit

        if system_id:
            candidates = self.rules_by_system_symptom.get((system_id, symptom_id), [])
            if candidates:
                return self._expand_ambiguous_candidates(symptom_id, candidates)
        return self._expand_ambiguous_candidates(symptom_id, self.get_rules_for_symptom(symptom_id))

    def rules_for_symptoms(self, symptom_ids: list[str]) -> list[dict[str, Any]]:
        seen = set()
        rules = []
        for symptom_id in symptom_ids:
            for rule in self.get_rules_for_symptom(symptom_id):
                fault_id = rule.get("fault_id")
                if fault_id and fault_id not in seen:
                    seen.add(fault_id)
                    rules.append(rule)
        return rules

    def label_for_symptom(self, symptom_id: str) -> str:
        symptom = self.get_symptom(symptom_id) or {}
        return symptom.get("display_name") or symptom.get("name") or symptom_id

    def system_label(self, system_id: str | None) -> str | None:
        if not system_id:
            return None
        system = self.systems.get(system_id) or {}
        return system.get("display_name") or system.get("name") or system_id

    def _build_cf_map(self) -> dict[str, dict[str, float]]:
        dynamic = self.cf_dynamic.get("symptoms") if isinstance(self.cf_dynamic, dict) else None
        if isinstance(dynamic, dict) and dynamic:
            return {
                symptom_id: {fault_id: float(cf) for fault_id, cf in faults.items()}
                for symptom_id, faults in dynamic.items()
                if isinstance(faults, dict)
            }

        cf_map: dict[str, dict[str, float]] = {}
        for rule in self.rules:
            fault_id = rule.get("fault_id")
            for symptom in rule.get("symptoms", []):
                symptom_id = symptom.get("symptom_id")
                if symptom_id and fault_id:
                    cf_map.setdefault(symptom_id, {})[fault_id] = float(symptom.get("cf", 0.5))
        return cf_map

    def _explicit_candidate_faults(self, symptom_id: str) -> list[dict[str, Any]]:
        fault_ids = []
        for rule in self.get_rules_for_symptom(symptom_id):
            for fault_id in rule.get("candidate_fault_ids") or []:
                if fault_id not in fault_ids:
                    fault_ids.append(fault_id)
        return [
            {**self.faults[fault_id], "candidate_reason": "primary_symptom_candidate_set"}
            for fault_id in fault_ids
            if fault_id in self.faults
        ]

    def _expand_ambiguous_candidates(
        self,
        symptom_id: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(candidates) != 1:
            return candidates

        seed = {**candidates[0], "candidate_reason": "matched_primary_symptom"}
        tokens = self._symptom_tokens(symptom_id)
        if not tokens:
            return candidates

        seen = {seed.get("fault_id")}
        expanded = [seed]
        for rule in self.rules:
            fault_id = rule.get("fault_id")
            if not fault_id or fault_id in seen:
                continue
            if seed.get("system_id") and rule.get("system_id") != seed.get("system_id"):
                continue
            searchable = " ".join(
                str(value or "")
                for value in [
                    rule.get("fault_name"),
                    rule.get("display_name"),
                    rule.get("system"),
                    rule.get("system_id"),
                    rule.get("subsystem"),
                    rule.get("subsystem_id"),
                    *(self.label_for_symptom(item.get("symptom_id")) for item in rule.get("symptoms", [])),
                ]
            ).lower()
            if any(token in searchable for token in tokens):
                expanded.append({**rule, "candidate_reason": "related_primary_symptom"})
                seen.add(fault_id)
        return expanded

    def _symptom_tokens(self, symptom_id: str) -> set[str]:
        symptom = self.get_symptom(symptom_id) or {}
        text = " ".join(
            str(part or "")
            for part in [
                symptom_id,
                symptom.get("name"),
                symptom.get("display_name"),
                *(symptom.get("aliases") or []),
            ]
        )
        stopwords = {"light", "warning", "stays", "from", "with", "when", "while", "on", "off", "the", "and"}
        return {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9]+", text)
            if len(token) >= 3 and token.lower() not in stopwords and not token.upper().startswith("SYM")
        }

    def _index_systems(self, ontology: dict[str, Any]) -> dict[str, dict[str, Any]]:
        systems = {}
        for system in ontology.get("vehicle_systems", []):
            system_id = system.get("id")
            if system_id:
                systems[system_id] = system
        for rule in self.rules:
            system_id = rule.get("system_id") or rule.get("system")
            if system_id and system_id not in systems:
                systems[system_id] = {
                    "id": system_id,
                    "name": system_id.lower(),
                    "display_name": system_id,
                }
        return systems

    @staticmethod
    def _index_rules_by_symptom(rules: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rule in rules:
            for symptom in rule.get("symptoms", []):
                symptom_id = symptom.get("symptom_id")
                if symptom_id:
                    index[symptom_id].append(rule)
        return dict(index)

    @staticmethod
    def _index_rules_by_system_symptom(
        rules: list[dict[str, Any]],
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for rule in rules:
            system_id = rule.get("system_id") or rule.get("system")
            if not system_id:
                continue
            for symptom in rule.get("symptoms", []):
                symptom_id = symptom.get("symptom_id")
                if symptom_id:
                    index[(system_id, symptom_id)].append(rule)
        return dict(index)
