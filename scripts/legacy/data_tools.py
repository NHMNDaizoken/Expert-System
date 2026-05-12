import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402
from src.legacy.kg_validator import KGValidationError, validate_all

RAW_PATH = Path("data/raw/automotive_faults.json")
GENERATED_RULES_PATH = Path("data/staging/kg_rules_from_dataset.json")
ONTOLOGY_PATH = Path("data/staging/ontology.json")
SYMPTOM_ALIASES_PATH = Path("data/staging/symptom_aliases.json")


def load_json(path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def extract_rules(data):
    if isinstance(data, list):
        return data
    return data.get("rules", [])


def slugify(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def make_id(prefix, text):
    return f"{prefix}_{slugify(text).upper()}"


def inspect_dataset(args):
    data = load_json(args.path)

    print("TYPE:", type(data))

    if isinstance(data, list):
        print("TOTAL:", len(data))
        if data:
            print(json.dumps(data[0], indent=2, ensure_ascii=False))
    elif isinstance(data, dict):
        print("KEYS:", data.keys())
        print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])


def list_categories(args):
    data = load_json(args.path)
    counter = Counter(record.get("category", "MISSING") for record in data)

    for category, count in counter.most_common():
        print(f"{category}: {count}")


def normalize_category(category):
    category = category.lower().strip()

    if "electrical system" in category:
        return {
            "system_id": "SYS_ELECTRICAL",
            "subsystem_id": "SUB_STARTING",
            "affected_components": ["CMP_STARTER_MOTOR"],
        }

    return {
        "system_id": "SYS_ELECTRICAL",
        "subsystem_id": "SUB_STARTING",
        "affected_components": ["CMP_STARTER_MOTOR"],
    }


def build_rules(args):
    raw = load_json(args.input)
    symptom_aliases = {}
    rules = []

    for i, record in enumerate(raw, start=1):
        category = record.get("category", "")
        subcategory = record.get("subcategory", "")
        symptoms = record.get("symptoms", [])
        diagnosis_steps = record.get("diagnosis_steps", [])

        if not subcategory:
            continue

        fault_name = slugify(subcategory)
        fault_id = f"FLT_{i:03d}"
        ontology_map = normalize_category(category)

        symptom_refs = []

        for j, symptom_text in enumerate(symptoms, start=1):
            symptom_name = slugify(symptom_text)
            symptom_id = make_id("SYM", symptom_name)

            symptom_aliases.setdefault(
                symptom_id,
                {
                    "name": symptom_name,
                    "display_name": symptom_text,
                    "label_vi": symptom_text,
                    "aliases": [symptom_text],
                },
            )

            symptom_refs.append(
                {
                    "symptom_id": symptom_id,
                    "cf": 0.7,
                    "priority": j,
                }
            )

        repair_steps = []

        for diag in diagnosis_steps:
            step_text = diag.get("step")
            if step_text:
                repair_steps.append(step_text)

            for result in diag.get("result", []):
                repair_steps.append(f"Possible result: {result}")

        repairs = []

        if repair_steps:
            repairs.append(
                {
                    "repair_id": f"REP_{i:03d}",
                    "repair_name": f"diagnose_{fault_name}",
                    "display_name": f"Diagnosis for {subcategory}",
                    "label_vi": f"Diagnosis for {subcategory}",
                    "steps": repair_steps,
                }
            )

        rules.append(
            {
                "fault_id": fault_id,
                "fault_name": fault_name,
                "display_name": subcategory,
                "label_vi": subcategory,
                "system_id": ontology_map["system_id"],
                "subsystem_id": ontology_map["subsystem_id"],
                "affected_components": ontology_map["affected_components"],
                "symptoms": symptom_refs,
                "repairs": repairs,
                "status": "pending_review",
            }
        )

    kg = {
        "meta": {
            "version": "2.0",
            "domain": "car_diagnostic",
            "source": "automotive_faults_dataset",
            "total_rules": len(rules),
            "graph_type": "ontology_driven",
        },
        "rules": rules,
    }

    save_json(args.output, kg)
    save_json(args.symptom_aliases, symptom_aliases)

    print(f"Generated {len(rules)} ontology-driven rules")
    print(f"Saved rules to: {args.output}")
    print(f"Saved symptom aliases to: {args.symptom_aliases}")


def approve_rules(args):
    data = load_json(args.path)
    rules = extract_rules(data)

    for rule in rules:
        rule["status"] = "approved"

    save_json(args.path, data)
    print(f"All rules set to approved in {args.path}")


def validate_rules(args):
    try:
        validate_all(args.ontology, args.symptom_aliases, args.path)
    except KGValidationError as error:
        print("Validation failed")
        print("-", error)
        return 1

    print("Validation passed: 0 errors")
    return 0


def get_driver():
    from neo4j import GraphDatabase
    from src.config import require_neo4j_config

    uri, user, password = require_neo4j_config()
    return GraphDatabase.driver(uri, auth=(user, password))


def clear_database_tx(tx):
    tx.run("MATCH (n) DETACH DELETE n")


def create_constraints_tx(tx):
    tx.run(
        "CREATE CONSTRAINT vehicle_system_id IF NOT EXISTS "
        "FOR (n:VehicleSystem) REQUIRE n.id IS UNIQUE"
    )
    tx.run(
        "CREATE CONSTRAINT subsystem_id IF NOT EXISTS "
        "FOR (n:Subsystem) REQUIRE n.id IS UNIQUE"
    )
    tx.run(
        "CREATE CONSTRAINT component_id IF NOT EXISTS "
        "FOR (n:Component) REQUIRE n.id IS UNIQUE"
    )
    tx.run(
        "CREATE CONSTRAINT fault_id IF NOT EXISTS "
        "FOR (n:Fault) REQUIRE n.id IS UNIQUE"
    )
    tx.run(
        "CREATE CONSTRAINT symptom_id IF NOT EXISTS "
        "FOR (n:Symptom) REQUIRE n.id IS UNIQUE"
    )
    tx.run(
        "CREATE CONSTRAINT repair_id IF NOT EXISTS "
        "FOR (n:Repair) REQUIRE n.id IS UNIQUE"
    )


def import_ontology_tx(tx, ontology):
    for system in ontology.get("vehicle_systems", []):
        tx.run(
            """
            MERGE (vs:VehicleSystem {id: $id})
            SET vs.name = $name,
                vs.display_name = $display_name,
                vs.label_vi = $label_vi
            """,
            id=system["id"],
            name=system["name"],
            display_name=system.get("display_name", system["name"]),
            label_vi=system.get("label_vi", system.get("display_name", system["name"])),
        )

        for subsystem in system.get("subsystems", []):
            tx.run(
                """
                MATCH (vs:VehicleSystem {id: $system_id})
                MERGE (sub:Subsystem {id: $subsystem_id})
                SET sub.name = $subsystem_name,
                    sub.display_name = $display_name,
                    sub.label_vi = $label_vi
                MERGE (sub)-[:PART_OF]->(vs)
                """,
                system_id=system["id"],
                subsystem_id=subsystem["id"],
                subsystem_name=subsystem["name"],
                display_name=subsystem.get("display_name", subsystem["name"]),
                label_vi=subsystem.get(
                    "label_vi",
                    subsystem.get("display_name", subsystem["name"]),
                ),
            )

            for component in subsystem.get("components", []):
                tx.run(
                    """
                    MATCH (sub:Subsystem {id: $subsystem_id})
                    MERGE (c:Component {id: $component_id})
                    SET c.name = $component_name,
                        c.display_name = $display_name,
                        c.label_vi = $label_vi,
                        c.aliases = $aliases
                    MERGE (c)-[:PART_OF]->(sub)
                    """,
                    subsystem_id=subsystem["id"],
                    component_id=component["id"],
                    component_name=component["name"],
                    display_name=component.get("display_name", component["name"]),
                    label_vi=component.get(
                        "label_vi",
                        component.get("display_name", component["name"]),
                    ),
                    aliases=component.get("aliases", []),
                )


def import_symptoms_tx(tx, symptom_aliases):
    for symptom_id, symptom in symptom_aliases.items():
        tx.run(
            """
            MERGE (s:Symptom {id: $id})
            SET s.name = $name,
                s.display_name = $display_name,
                s.label_vi = $label_vi,
                s.aliases = $aliases
            """,
            id=symptom_id,
            name=symptom["name"],
            display_name=symptom.get("display_name", symptom["name"]),
            label_vi=symptom.get(
                "label_vi",
                symptom.get("display_name", symptom["name"]),
            ),
            aliases=symptom.get("aliases", []),
        )


def create_fault_tx(tx, rule):
    query = """
    MERGE (f:Fault {id: $id})
    SET f.name = $name,
        f.display_name = $display_name,
        f.label_vi = $label_vi,
        f.system_id = $system_id,
        f.subsystem_id = $subsystem_id,
        f.status = $status
    """
    tx.run(
        query,
        id=rule["fault_id"],
        name=rule["fault_name"],
        display_name=rule.get("display_name", rule["fault_name"]),
        label_vi=rule.get("label_vi", rule.get("display_name", rule["fault_name"])),
        system_id=rule["system_id"],
        subsystem_id=rule["subsystem_id"],
        status=rule.get("status", "pending_review"),
    )


def create_affects_edge_tx(tx, rule, component_id):
    query = """
    MATCH (f:Fault {id: $fault_id})
    MATCH (c:Component {id: $component_id})
    MERGE (f)-[r:AFFECTS]->(c)
    SET r.status = $status
    """
    tx.run(
        query,
        fault_id=rule["fault_id"],
        component_id=component_id,
        status=rule.get("status", "pending_review"),
    )


def create_symptom_edge_tx(tx, rule, symptom, symptom_aliases):
    symptom_id = symptom["symptom_id"]
    symptom_data = symptom_aliases[symptom_id]

    query = """
    MERGE (s:Symptom {id: $symptom_id})
    SET s.name = $symptom_name,
        s.display_name = $display_name,
        s.label_vi = $label_vi,
        s.aliases = $aliases

    WITH s
    MATCH (f:Fault {id: $fault_id})
    MERGE (f)-[r:HAS_SYMPTOM]->(s)
    SET r.cf = $cf,
        r.priority = $priority,
        r.status = $status
    """

    tx.run(
        query,
        fault_id=rule["fault_id"],
        symptom_id=symptom_id,
        symptom_name=symptom_data["name"],
        display_name=symptom_data.get("display_name", symptom_data["name"]),
        label_vi=symptom_data.get(
            "label_vi",
            symptom_data.get("display_name", symptom_data["name"]),
        ),
        aliases=symptom_data.get("aliases", []),
        cf=float(symptom["cf"]),
        priority=int(symptom.get("priority", 2)),
        status=rule.get("status", "pending_review"),
    )


def create_repair_edge_tx(tx, rule, repair):
    repair_name = repair.get("repair_name") or repair.get("name")

    query = """
    MERGE (r:Repair {id: $repair_id})
    SET r.name = $repair_name,
        r.display_name = $display_name,
        r.label_vi = $label_vi,
        r.steps = $steps,
        r.status = $status

    WITH r
    MATCH (f:Fault {id: $fault_id})
    MERGE (f)-[rel:FIXED_BY]->(r)
    SET rel.status = $status
    """

    tx.run(
        query,
        fault_id=rule["fault_id"],
        repair_id=repair["repair_id"],
        repair_name=repair_name,
        display_name=repair.get("display_name", repair_name),
        label_vi=repair.get("label_vi", repair.get("display_name", repair_name)),
        steps=repair.get("steps", []),
        status=rule.get("status", "pending_review"),
    )


def generate_related_faults_tx(tx):
    tx.run(
        """
        MATCH (f1:Fault)-[:HAS_SYMPTOM]->(s:Symptom)<-[:HAS_SYMPTOM]-(f2:Fault)
        WHERE f1.id < f2.id
        MERGE (f1)-[r:RELATED_TO {reason: 'shared_symptom'}]->(f2)
        SET r.via = s.id
        """
    )

    tx.run(
        """
        MATCH (f1:Fault)-[:AFFECTS]->(c:Component)<-[:AFFECTS]-(f2:Fault)
        WHERE f1.id < f2.id
        MERGE (f1)-[r:RELATED_TO {reason: 'same_component'}]->(f2)
        SET r.via = c.id
        """
    )


def import_ontology(args):
    ontology = load_json(args.path)
    driver = get_driver()

    try:
        with driver.session() as session:
            session.execute_write(create_constraints_tx)
            session.execute_write(import_ontology_tx, ontology)
    finally:
        driver.close()

    print(f"Imported ontology from {args.path}")


def import_symptoms(args):
    symptom_aliases = load_json(args.path)
    driver = get_driver()

    try:
        with driver.session() as session:
            session.execute_write(create_constraints_tx)
            session.execute_write(import_symptoms_tx, symptom_aliases)
    finally:
        driver.close()

    print(f"Imported symptoms from {args.path}")


def import_rules(args):
    validation_result = validate_rules(args)
    if validation_result != 0:
        return validation_result

    data = load_json(args.path)
    symptom_aliases = load_json(args.symptom_aliases)
    rules = extract_rules(data)
    driver = get_driver()

    try:
        with driver.session() as session:
            session.execute_write(create_constraints_tx)

            if args.clear:
                session.execute_write(clear_database_tx)
                session.execute_write(create_constraints_tx)

            for rule in rules:
                session.execute_write(create_fault_tx, rule)

                for component_id in rule.get("affected_components", []):
                    session.execute_write(create_affects_edge_tx, rule, component_id)

                for symptom in rule.get("symptoms", []):
                    session.execute_write(
                        create_symptom_edge_tx,
                        rule,
                        symptom,
                        symptom_aliases,
                    )

                for repair in rule.get("repairs", []):
                    session.execute_write(create_repair_edge_tx, rule, repair)
    finally:
        driver.close()

    print(f"Imported {len(rules)} rules into Neo4j")


def generate_related_faults(args):
    driver = get_driver()

    try:
        with driver.session() as session:
            session.execute_write(generate_related_faults_tx)
    finally:
        driver.close()

    print("Generated RELATED_TO edges")


def rebuild_graph(args):
    validation_result = validate_rules(args)
    if validation_result != 0:
        return validation_result

    ontology = load_json(args.ontology)
    symptom_aliases = load_json(args.symptom_aliases)
    data = load_json(args.path)
    rules = extract_rules(data)

    driver = get_driver()

    try:
        with driver.session() as session:
            if args.clear:
                session.execute_write(clear_database_tx)

            session.execute_write(create_constraints_tx)
            session.execute_write(import_ontology_tx, ontology)
            session.execute_write(import_symptoms_tx, symptom_aliases)

            for rule in rules:
                session.execute_write(create_fault_tx, rule)

                for component_id in rule.get("affected_components", []):
                    session.execute_write(create_affects_edge_tx, rule, component_id)

                for symptom in rule.get("symptoms", []):
                    session.execute_write(
                        create_symptom_edge_tx,
                        rule,
                        symptom,
                        symptom_aliases,
                    )

                for repair in rule.get("repairs", []):
                    session.execute_write(create_repair_edge_tx, rule, repair)

            session.execute_write(generate_related_faults_tx)
    finally:
        driver.close()

    print("Rebuilt ontology-driven KG successfully")
    print(f"Imported ontology: {args.ontology}")
    print(f"Imported symptoms: {args.symptom_aliases}")
    print(f"Imported rules: {len(rules)}")


def build_parser():
    parser = argparse.ArgumentParser(description="Dataset and KG utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("path", nargs="?", type=Path, default=RAW_PATH)
    inspect_parser.set_defaults(func=inspect_dataset)

    categories_parser = subparsers.add_parser("categories")
    categories_parser.add_argument("path", nargs="?", type=Path, default=RAW_PATH)
    categories_parser.set_defaults(func=list_categories)

    build_parser_ = subparsers.add_parser("build")
    build_parser_.add_argument("--input", type=Path, default=RAW_PATH)
    build_parser_.add_argument("--output", type=Path, default=GENERATED_RULES_PATH)
    build_parser_.add_argument(
        "--symptom-aliases",
        type=Path,
        default=SYMPTOM_ALIASES_PATH,
    )
    build_parser_.set_defaults(func=build_rules)

    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("path", nargs="?", type=Path, default=GENERATED_RULES_PATH)
    approve_parser.set_defaults(func=approve_rules)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument("--ontology", type=Path, default=ONTOLOGY_PATH)
    validate_parser.add_argument(
        "--symptom-aliases",
        type=Path,
        default=SYMPTOM_ALIASES_PATH,
    )
    validate_parser.set_defaults(func=validate_rules)

    ontology_parser = subparsers.add_parser("import-ontology")
    ontology_parser.add_argument("path", nargs="?", type=Path, default=ONTOLOGY_PATH)
    ontology_parser.set_defaults(func=import_ontology)

    symptoms_parser = subparsers.add_parser("import-symptoms")
    symptoms_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=SYMPTOM_ALIASES_PATH,
    )
    symptoms_parser.set_defaults(func=import_symptoms)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("path", type=Path)
    import_parser.add_argument("--ontology", type=Path, default=ONTOLOGY_PATH)
    import_parser.add_argument(
        "--symptom-aliases",
        type=Path,
        default=SYMPTOM_ALIASES_PATH,
    )
    import_parser.add_argument("--clear", action="store_true")
    import_parser.set_defaults(func=import_rules)

    related_parser = subparsers.add_parser("generate-related")
    related_parser.set_defaults(func=generate_related_faults)

    rebuild_parser = subparsers.add_parser("rebuild")
    rebuild_parser.add_argument("path", nargs="?", type=Path, default=GENERATED_RULES_PATH)
    rebuild_parser.add_argument("--ontology", type=Path, default=ONTOLOGY_PATH)
    rebuild_parser.add_argument(
        "--symptom-aliases",
        type=Path,
        default=SYMPTOM_ALIASES_PATH,
    )
    rebuild_parser.add_argument("--clear", action="store_true")
    rebuild_parser.set_defaults(func=rebuild_graph)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    return result or 0


if __name__ == "__main__":
    sys.exit(main())
