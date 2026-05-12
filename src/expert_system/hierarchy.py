from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LEVELS = {
    1: "system",
    2: "primary_symptom",
    3: "secondary_context",
    4: "possible_faults",
    5: "diagnosis_procedures",
    6: "confirmation_resolution",
}

SYSTEM_ROOTS = [
    "engine",
    "brake",
    "electrical",
    "transmission",
    "cooling_system",
    "fuel_system",
    "suspension",
]

@dataclass
class HierarchyNode:
    id: str
    level: int
    type: str
    name: str
    children: list["HierarchyNode"] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level,
            "type": self.type,
            "name": self.name,
            "data": self.data,
            "children": [child.to_dict() for child in self.children],
        }


def normalize_id(value: str) -> str:
    return "_".join(str(value).strip().lower().replace("/", " ").replace("-", " ").split())


def symptom_name(symptom: dict[str, Any] | None, fallback: str) -> str:
    symptom = symptom or {}
    return symptom.get("display_name") or symptom.get("name") or fallback


def build_hierarchy(
    *,
    ontology: dict[str, Any],
    symptom_aliases: dict[str, Any],
    rules: list[dict[str, Any]],
    procedure_trees: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the 6-level automotive diagnosis hierarchy.

    Level 1: Vehicle system/root node
    Level 2: Primary symptom
    Level 3: Secondary symptoms and context
    Level 4: Possible faults ranked by confidence
    Level 5: Step-by-step diagnosis procedure
    Level 6: Confirmation tests, parts and resolution
    """
    procedure_trees = procedure_trees or {}
    root = HierarchyNode("vehicle_diagnosis", 0, "root", "Triệu chứng chính / Hệ thống xe")

    systems: dict[str, HierarchyNode] = {}
    for item in ontology.get("vehicle_systems", []):
        system_id = normalize_id(item.get("id") or item.get("name") or "unknown")
        node = HierarchyNode(
            id=system_id,
            level=1,
            type=LEVELS[1],
            name=item.get("display_name") or item.get("name") or system_id,
            data={"source": "ontology", **item},
        )
        systems[system_id] = node
        root.children.append(node)

    for default_system in SYSTEM_ROOTS:
        systems.setdefault(
            default_system,
            HierarchyNode(default_system, 1, LEVELS[1], default_system.replace("_", " ").title()),
        )
        if systems[default_system] not in root.children:
            root.children.append(systems[default_system])

    primary_index: dict[tuple[str, str], HierarchyNode] = {}
    context_index: dict[tuple[str, str, str], HierarchyNode] = {}

    for rule in rules:
        system_id = normalize_id(rule.get("system_id") or rule.get("system") or "unknown")
        system_node = systems.setdefault(
            system_id,
            HierarchyNode(system_id, 1, LEVELS[1], system_id.replace("_", " ").title()),
        )
        if system_node not in root.children:
            root.children.append(system_node)

        symptoms = rule.get("symptoms") or []
        if not symptoms:
            continue

        primary = symptoms[0]
        primary_id = primary.get("symptom_id") or normalize_id(symptom_name(primary, "unknown_symptom"))
        primary_key = (system_id, primary_id)
        if primary_key not in primary_index:
            primary_node = HierarchyNode(
                id=f"{system_id}:{primary_id}",
                level=2,
                type=LEVELS[2],
                name=symptom_name(symptom_aliases.get(primary_id), primary_id),
                data={"symptom_id": primary_id, "cf": primary.get("cf", 0.5)},
            )
            primary_index[primary_key] = primary_node
            system_node.children.append(primary_node)
        else:
            primary_node = primary_index[primary_key]

        secondary_ids = [s.get("symptom_id") for s in symptoms[1:] if s.get("symptom_id")]
        context_id = "+".join(secondary_ids) if secondary_ids else "no_extra_context"
        context_key = (system_id, primary_id, context_id)
        if context_key not in context_index:
            context_label = " + ".join(symptom_name(symptom_aliases.get(sid), sid) for sid in secondary_ids) or "Chưa có triệu chứng phụ"
            context_node = HierarchyNode(
                id=f"{system_id}:{primary_id}:{context_id}",
                level=3,
                type=LEVELS[3],
                name=context_label,
                data={"secondary_symptom_ids": secondary_ids, "conditions": rule.get("conditions", [])},
            )
            context_index[context_key] = context_node
            primary_node.children.append(context_node)
        else:
            context_node = context_index[context_key]

        fault_id = rule.get("fault_id") or normalize_id(rule.get("fault_name") or "unknown_fault")
        fault_node = HierarchyNode(
            id=f"fault:{fault_id}",
            level=4,
            type=LEVELS[4],
            name=rule.get("fault_name") or rule.get("display_name") or fault_id,
            data={
                "fault_id": fault_id,
                "confidence": rule.get("confidence") or rule.get("cf") or max([float(s.get("cf", 0.5)) for s in symptoms] or [0.5]),
                "rank_basis": "dynamic_cf_and_matched_symptoms",
            },
        )

        procedure = rule.get("procedure") or procedure_trees.get(fault_id) or {}
        steps = procedure.get("steps") or rule.get("diagnosis_steps") or []
        procedure_node = HierarchyNode(
            id=f"procedure:{fault_id}",
            level=5,
            type=LEVELS[5],
            name="Step-by-step diagnosis",
            data={"steps": steps},
        )

        resolution_node = HierarchyNode(
            id=f"resolution:{fault_id}",
            level=6,
            type=LEVELS[6],
            name="Confirmation tests + Parts + Resolution",
            data={
                "confirmation_tests": procedure.get("confirmation_tests") or rule.get("confirmation_tests") or [],
                "parts": rule.get("parts") or rule.get("parts_to_replace") or [],
                "resolution": rule.get("repair") or rule.get("resolution") or procedure.get("resolution"),
            },
        )
        procedure_node.children.append(resolution_node)
        fault_node.children.append(procedure_node)
        context_node.children.append(fault_node)

    for node in context_index.values():
        node.children.sort(key=lambda child: child.data.get("confidence", 0), reverse=True)

    return root.to_dict()
