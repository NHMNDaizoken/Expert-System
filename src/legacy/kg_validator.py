import json
from pathlib import Path


class KGValidationError(Exception):
    pass


ALLOWED_STATUS = {"approved", "pending_review", "rejected"}


def load_json(path: str | Path):
    path = Path(path)
    if not path.exists():
        raise KGValidationError(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_rules(data: list[dict] | dict) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "rules" in data:
        return extract_rules(data["rules"])
    return []


def build_ontology_index(ontology: dict) -> dict:
    systems = {}
    subsystems = {}
    components = {}
    subsystem_to_system = {}
    component_to_subsystem = {}

    for system in ontology.get("vehicle_systems", []):
        system_id = system.get("id")
        if not system_id:
            raise KGValidationError("VehicleSystem missing id")

        systems[system_id] = system

        for subsystem in system.get("subsystems", []):
            subsystem_id = subsystem.get("id")
            if not subsystem_id:
                raise KGValidationError(f"Subsystem missing id in system {system_id}")

            subsystems[subsystem_id] = subsystem
            subsystem_to_system[subsystem_id] = system_id

            for component in subsystem.get("components", []):
                component_id = component.get("id")
                if not component_id:
                    raise KGValidationError(
                        f"Component missing id in subsystem {subsystem_id}"
                    )

                components[component_id] = component
                component_to_subsystem[component_id] = subsystem_id

    return {
        "systems": systems,
        "subsystems": subsystems,
        "components": components,
        "subsystem_to_system": subsystem_to_system,
        "component_to_subsystem": component_to_subsystem,
    }


def validate_ontology(ontology: dict) -> dict:
    index = build_ontology_index(ontology)

    if not index["systems"]:
        raise KGValidationError("ontology.json must contain at least one VehicleSystem")

    return index


def validate_symptom_aliases(symptom_aliases: dict) -> dict:
    if not symptom_aliases:
        raise KGValidationError("symptom_aliases.json is empty")

    for symptom_id, item in symptom_aliases.items():
        if not symptom_id.startswith("SYM_"):
            raise KGValidationError(f"Invalid symptom id: {symptom_id}")

        if not item.get("name"):
            raise KGValidationError(f"Symptom {symptom_id} missing name")

        aliases = item.get("aliases", [])
        if not isinstance(aliases, list) or not aliases:
            raise KGValidationError(f"Symptom {symptom_id} must have aliases list")

    return symptom_aliases


def validate_rules(
    rules: list[dict],
    ontology_index: dict,
    symptom_index: dict,
) -> None:
    seen_faults = set()

    for rule in rules:
        fault_id = rule.get("fault_id")

        if not fault_id:
            raise KGValidationError("Rule missing fault_id")

        if fault_id in seen_faults:
            raise KGValidationError(f"Duplicate fault_id: {fault_id}")

        seen_faults.add(fault_id)

        status = rule.get("status", "pending_review")
        if status not in ALLOWED_STATUS:
            raise KGValidationError(f"{fault_id}: invalid status {status}")

        system_id = rule.get("system_id")
        subsystem_id = rule.get("subsystem_id")

        if system_id not in ontology_index["systems"]:
            raise KGValidationError(f"{fault_id}: unknown system_id {system_id}")

        if subsystem_id not in ontology_index["subsystems"]:
            raise KGValidationError(f"{fault_id}: unknown subsystem_id {subsystem_id}")

        expected_system_id = ontology_index["subsystem_to_system"].get(subsystem_id)
        if expected_system_id != system_id:
            raise KGValidationError(
                f"{fault_id}: subsystem {subsystem_id} does not belong to {system_id}"
            )

        affected_components = rule.get("affected_components", [])
        if not affected_components:
            raise KGValidationError(f"{fault_id}: affected_components is required")

        for component_id in affected_components:
            if component_id not in ontology_index["components"]:
                raise KGValidationError(
                    f"{fault_id}: unknown component_id {component_id}"
                )

            expected_subsystem_id = ontology_index["component_to_subsystem"].get(
                component_id
            )
            if expected_subsystem_id != subsystem_id:
                raise KGValidationError(
                    f"{fault_id}: component {component_id} does not belong to {subsystem_id}"
                )

        symptoms = rule.get("symptoms", [])
        if not symptoms:
            raise KGValidationError(f"{fault_id}: symptoms is required")

        for symptom in symptoms:
            symptom_id = symptom.get("symptom_id")
            if symptom_id not in symptom_index:
                raise KGValidationError(f"{fault_id}: unknown symptom_id {symptom_id}")

            cf = symptom.get("cf")
            if not isinstance(cf, int | float):
                raise KGValidationError(f"{fault_id}: cf must be number")

            if cf < 0 or cf > 1:
                raise KGValidationError(f"{fault_id}: cf must be between 0 and 1")

            priority = symptom.get("priority", 2)
            if not isinstance(priority, int):
                raise KGValidationError(f"{fault_id}: priority must be integer")

        repairs = rule.get("repairs", [])
        if not repairs:
            raise KGValidationError(f"{fault_id}: repairs is required")

        for repair in repairs:
            if not repair.get("repair_id"):
                raise KGValidationError(f"{fault_id}: repair missing repair_id")

            if not repair.get("repair_name"):
                raise KGValidationError(f"{fault_id}: repair missing repair_name")


def validate_all(
    ontology_path: str,
    symptom_aliases_path: str,
    rules_path: str,
) -> None:
    ontology = load_json(ontology_path)
    symptom_aliases = load_json(symptom_aliases_path)
    rules = extract_rules(load_json(rules_path))

    ontology_index = validate_ontology(ontology)
    symptom_index = validate_symptom_aliases(symptom_aliases)
    validate_rules(rules, ontology_index, symptom_index)
