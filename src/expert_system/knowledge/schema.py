"""
schema — Validation schemas and validators for the expert-system knowledge base.

Contains ExpertSystemValidator which checks rules, procedures,
orphans, and structural integrity of the staging knowledge data.
Also contains the ValidationReport dataclass and helper functions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.expert_system.knowledge.loader import KnowledgeBase


# ============================================================================
# Validation
# ============================================================================

@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class ExpertSystemValidator:
    """Validate the hierarchical expert-system Knowledge Base."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        self._duplicates(report)
        self._rule_references(report)
        self._procedures(report)
        self._orphans(report)
        return report

    def _duplicates(self, report: ValidationReport) -> None:
        self._duplicate_ids([rule.get("fault_id") for rule in self.kb.rules], "fault", report)
        symptom_refs = [
            symptom.get("symptom_id")
            for rule in self.kb.rules
            for symptom in rule.get("symptoms", [])
            if symptom.get("symptom_id")
        ]
        if len(set(self.kb.symptom_aliases)) != len(self.kb.symptom_aliases):
            report.errors.append("Duplicate symptom IDs found in symptom_aliases.json")
        self._duplicate_ids(symptom_refs, "rule symptom reference", report, errors=False)

    def _rule_references(self, report: ValidationReport) -> None:
        for rule in self.kb.rules:
            fault_id = rule.get("fault_id", "<missing>")
            if not rule.get("fault_id"):
                report.errors.append("Rule missing fault_id")
            if not rule.get("symptoms"):
                report.errors.append(f"{fault_id}: symptoms is required")
            for symptom in rule.get("symptoms", []):
                symptom_id = symptom.get("symptom_id")
                if symptom_id not in self.kb.symptom_aliases:
                    report.errors.append(f"{fault_id}: missing symptom reference {symptom_id}")
                if "cf" not in symptom:
                    report.errors.append(f"{fault_id}: symptom {symptom_id} missing CF")
            if not rule.get("resolution"):
                report.warnings.append(f"{fault_id}: missing resolution")
            if not rule.get("procedure") and not self.kb.procedure_trees.get(fault_id):
                report.warnings.append(f"{fault_id}: missing procedure")

    def _procedures(self, report: ValidationReport) -> None:
        terminals = {"DIAGNOSED", "REFUTED", None}
        technical_terms = (
            "measure",
            "inspect",
            "test",
            "check fuel",
            "check abs fuse",
            "check wiring",
            "check relay",
            "voltage",
            "resistance",
            "scanner",
            "multimeter",
            "đo ",
            "điện áp",
            "điện trở",
        )
        for rule in self.kb.rules:
            fault_id = rule.get("fault_id")
            stored_procedure = rule.get("procedure") or self.kb.procedure_trees.get(fault_id)
            if stored_procedure:
                self._procedure_links(fault_id, stored_procedure, terminals, report)

            runtime_procedure = self.kb.get_procedure_for_fault(fault_id)
            if not runtime_procedure:
                continue
            self._procedure_links(fault_id, runtime_procedure, terminals, report)
            for step_id, step in (runtime_procedure.get("steps") or {}).items():
                question = str(step.get("question") or "").lower()
                if question and any(term in question for term in technical_terms):
                    report.errors.append(f"{fault_id}: technical procedure leaked into user question {step_id}")
                if not step.get("symptom_id"):
                    report.warnings.append(f"{fault_id}: procedure step {step_id} missing symptom_id")

    def _procedure_links(
        self,
        fault_id: str,
        procedure: dict[str, Any],
        terminals: set[str | None],
        report: ValidationReport,
    ) -> None:
        steps = procedure.get("steps", {})
        entry = procedure.get("entry_step")
        if entry not in steps:
            report.errors.append(f"{fault_id}: invalid procedure entry_step {entry}")
        for step_id, step in steps.items():
            for branch in ("yes_next", "no_next"):
                target = step.get(branch)
                if target not in terminals and target not in steps:
                    report.errors.append(f"{fault_id}: invalid procedure link {step_id}.{branch} -> {target}")
        self._procedure_paths(fault_id, entry, steps, report)

    def _procedure_paths(
        self,
        fault_id: str,
        entry: str,
        steps: dict[str, dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        max_depth = 8
        if entry not in steps:
            return

        stack = [(entry, [])]
        while stack:
            step_id, path = stack.pop()
            if step_id in path:
                report.errors.append(f"{fault_id}: procedure cycle detected {' -> '.join(path + [step_id])}")
                continue
            if len(path) + 1 > max_depth:
                report.errors.append(f"{fault_id}: procedure max depth exceeds {max_depth}")
                continue
            step = steps.get(step_id)
            if not step:
                continue
            next_path = path + [step_id]
            for target in (step.get("yes_next"), step.get("no_next")):
                if target in {"DIAGNOSED", "REFUTED", None}:
                    continue
                stack.append((target, next_path))

    def _orphans(self, report: ValidationReport) -> None:
        referenced_symptoms = {
            symptom.get("symptom_id")
            for rule in self.kb.rules
            for symptom in rule.get("symptoms", [])
            if symptom.get("symptom_id")
        }
        for symptom_id in sorted(set(self.kb.symptom_aliases) - referenced_symptoms):
            report.warnings.append(f"Orphan symptom: {symptom_id}")
        for symptom_id in referenced_symptoms:
            if not self.kb.get_rules_for_symptom(symptom_id):
                report.warnings.append(f"Primary symptom has no candidate faults: {symptom_id}")

    def _duplicate_ids(
        self,
        ids: list[str | None],
        label: str,
        report: ValidationReport,
        *,
        errors: bool = True,
    ) -> None:
        seen = set()
        dupes = set()
        for item in ids:
            if not item:
                continue
            if item in seen:
                dupes.add(item)
            seen.add(item)
        for item in sorted(dupes):
            target = report.errors if errors else report.warnings
            target.append(f"Duplicate {label} id: {item}")


def validate_knowledge_base(kb: KnowledgeBase | None = None) -> ValidationReport:
    return ExpertSystemValidator(kb or KnowledgeBase.from_staging()).validate()


def print_report(report: ValidationReport) -> None:
    if report.errors:
        print("Validation errors:")
        for error in report.errors:
            print(f"- {error}")
    if report.warnings:
        print("Validation warnings:")
        for warning in report.warnings:
            print(f"- {warning}")
    if report.ok and not report.warnings:
        print("Validation passed: 0 errors, 0 warnings")
    elif report.ok:
        print(f"Validation passed: 0 errors, {len(report.warnings)} warnings")


def main() -> int:
    report = validate_knowledge_base()
    print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
