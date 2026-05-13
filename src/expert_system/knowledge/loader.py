"""
loader — Read-only access layer over the staging expert-system data.

Provides the KnowledgeBase class that loads ontology, symptom aliases,
rules, CF data, procedure trees, and translations from the staging
directory. Also provides helper functions load_json and extract_rules.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import re
from typing import Any

from src.expert_system.config import PROJECT_ROOT
from src.expert_system.utils.text import slugify


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
        translations: dict[str, str] | None = None,
    ):
        self.ontology = ontology or {"vehicle_systems": []}
        self.symptom_aliases = symptom_aliases or {}
        self.rules = rules or []
        self.cf_dynamic = cf_dynamic or {}
        self.procedure_trees = procedure_trees or {}
        self.translations = translations or {}

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
            translations=load_json(base / "vi_translations.json") if (base / "vi_translations.json").exists() else {},
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
        if rule.get("symptoms"):
            return self._symptom_procedure(rule)
        procedure = rule.get("procedure") or self.procedure_trees.get(fault_id)
        return self._localized_procedure(procedure) if procedure else None

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
        return self.vi_text(symptom.get("label_vi") or symptom.get("display_name") or symptom.get("name") or symptom_id)

    def label_for_fault(self, rule: dict[str, Any], fallback: str | None = None) -> str:
        return self.vi_text(
            rule.get("label_vi")
            or rule.get("display_name")
            or rule.get("fault_label")
            or rule.get("fault_name")
            or fallback
            or rule.get("fault_id")
        )

    def system_label(self, system_id: str | None) -> str | None:
        if not system_id:
            return None
        system = self.systems.get(system_id) or {}
        return self.vi_text(system.get("label_vi") or system.get("display_name") or system.get("name") or system_id)

    def vi_text(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return text
        formatted = self._format_action_label(text)
        if formatted != text:
            return formatted
        return self.translations.get(slugify(text), text)

    def symptom_question(self, symptom_id: str) -> str:
        label = self.label_for_symptom(symptom_id)
        searchable = f"{symptom_id} {label}".lower()
        patterns = [
            (("hard start", "difficulty starting", "khó nổ", "khó khởi động"), "Xe có khó nổ máy không?"),
            (("cold", "trời lạnh", "máy nguội"), "Xe có khó nổ khi máy nguội hoặc trời lạnh không?"),
            (("white smoke", "khói trắng"), "Khi khởi động, xe có khói trắng bất thường không?"),
            (("rough idle", "garanti", "rung giật", "không đều"), "Khi chạy garanti, động cơ có rung hoặc không đều không?"),
            (("check engine", "đèn báo lỗi động cơ"), "Đèn báo lỗi động cơ có sáng không?"),
            (("abs warning", "đèn abs"), "Đèn cảnh báo ABS có sáng không?"),
            (("grinding", "tiếng nghiến", "tiếng mài"), "Xe có phát ra tiếng nghiến hoặc tiếng mài bất thường không?"),
            (("vibration", "rung"), "Xe có bị rung bất thường khi vận hành không?"),
            (("low voltage", "điện áp thấp", "voltage"), "Đèn hoặc thiết bị điện trên xe có yếu bất thường không?"),
            (("noise", "tiếng ồn", "kêu"), "Xe có tiếng ồn bất thường không?"),
            (("leak", "rò rỉ", "chảy"), "Bạn có thấy dấu hiệu rò rỉ bất thường không?"),
            (("smell", "mùi"), "Bạn có ngửi thấy mùi bất thường khi xe hoạt động không?"),
            (("warning light", "đèn cảnh báo"), "Có đèn cảnh báo nào sáng trên bảng đồng hồ không?"),
        ]
        for keywords, question in patterns:
            if any(keyword in searchable for keyword in keywords):
                return question
        return f"Xe có dấu hiệu {label.lower()} không?"

    def _localized_procedure(self, procedure: dict[str, Any]) -> dict[str, Any]:
        localized = {**procedure, "steps": {}}
        for step_id, step in (procedure.get("steps") or {}).items():
            question = step.get("question")
            instruction = step.get("instruction")
            results = step.get("results") or []
            localized["steps"][step_id] = {
                **step,
                "question": self._as_question_vi(question or instruction),
                "symptom_id": step.get("symptom_id"),
                "symptom_label": self.vi_text(step.get("symptom_label")) if step.get("symptom_label") else None,
                "instruction": self.vi_text(instruction) if instruction else instruction,
                "results": [self.vi_text(result) for result in results],
            }
        return localized

    def _symptom_procedure(self, rule: dict[str, Any]) -> dict[str, Any]:
        fault_id = rule.get("fault_id")
        steps = {}
        step_ids = []
        for index, symptom in enumerate(rule.get("symptoms") or [], start=1):
            symptom_id = symptom.get("symptom_id")
            if not symptom_id:
                continue
            step_id = f"{str(fault_id).lower()}_symptom_{index}"
            step_ids.append(step_id)
            steps[step_id] = {
                "id": step_id,
                "symptom_id": symptom_id,
                "symptom_label": self.label_for_symptom(symptom_id),
                "question": self.symptom_question(symptom_id),
                "is_question": True,
                "yes_next": None,
                "no_next": "REFUTED",
                "instruction": None,
                "results": [],
            }

        for index, step_id in enumerate(step_ids):
            steps[step_id]["yes_next"] = step_ids[index + 1] if index + 1 < len(step_ids) else "DIAGNOSED"

        if not step_ids:
            return rule.get("procedure") or {}

        return {
            "fault_id": fault_id,
            "fault_name": rule.get("fault_name"),
            "entry_step": step_ids[0],
            "steps": steps,
            "source": "symptoms",
        }

    def _as_question_vi(self, value: Any) -> str:
        text = self.vi_text(value)
        if not text:
            return text
        if text.endswith("?"):
            text = text[:-1].strip()
        return f"{text}?"

    def _format_action_label(self, text: str) -> str:
        patterns = [
            (r"^Diagnosis for (.+)$", "Kiểm tra"),
            (r"^Repair for (.+)$", "Sửa chữa"),
            (r"^Replace (.+)$", "Thay"),
            (r"^Inspect (.+)$", "Kiểm tra"),
            (r"^Clean (.+)$", "Vệ sinh"),
            (r"^Test (.+)$", "Kiểm tra"),
            (r"^Adjust (.+)$", "Điều chỉnh"),
        ]
        for pattern, verb in patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if match:
                target = self.translations.get(slugify(match.group(1)), match.group(1).strip())
                return f"{verb} {target}"
        return text

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
