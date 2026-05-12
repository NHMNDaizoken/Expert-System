"""
Import automotive knowledge graph into Neo4j.

This script imports ontology, symptoms, faults, and repair procedures
into a Neo4j graph database for the automotive diagnostic expert system.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    import _bootstrap  # type: ignore # noqa: F401
except ModuleNotFoundError:
    from scripts import _bootstrap  # type: ignore # noqa: F401
from src.config import require_neo4j_config
from src.legacy.kg_validator import extract_rules, validate_all


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = PROJECT_ROOT / "data" / "staging" / "ontology.json"
SYMPTOM_ALIASES_PATH = PROJECT_ROOT / "data" / "staging" / "symptom_aliases.json"
RULES_PATH = PROJECT_ROOT / "data" / "staging" / "kg_rules_from_dataset.json"


def load_json(path: str | Path) -> Any:
    import json

    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def get_driver():
    from neo4j import GraphDatabase

    uri, user, password = require_neo4j_config()
    return GraphDatabase.driver(uri, auth=(user, password))


def create_constraints_tx(tx):
    tx.run("CREATE CONSTRAINT vehicle_system_id IF NOT EXISTS FOR (n:VehicleSystem) REQUIRE n.id IS UNIQUE")
    tx.run("CREATE CONSTRAINT subsystem_id IF NOT EXISTS FOR (n:Subsystem) REQUIRE n.id IS UNIQUE")
    tx.run("CREATE CONSTRAINT component_id IF NOT EXISTS FOR (n:Component) REQUIRE n.id IS UNIQUE")
    tx.run("CREATE CONSTRAINT fault_id IF NOT EXISTS FOR (n:Fault) REQUIRE n.id IS UNIQUE")
    tx.run("CREATE CONSTRAINT symptom_id IF NOT EXISTS FOR (n:Symptom) REQUIRE n.id IS UNIQUE")
    tx.run("CREATE CONSTRAINT repair_id IF NOT EXISTS FOR (n:Repair) REQUIRE n.id IS UNIQUE")


def clear_database_tx(tx):
    tx.run("MATCH (n) DETACH DELETE n")


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
                label_vi=subsystem.get("label_vi", subsystem.get("display_name", subsystem["name"])),
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
                    label_vi=component.get("label_vi", component.get("display_name", component["name"])),
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
            label_vi=symptom.get("label_vi", symptom.get("display_name", symptom["name"])),
            aliases=symptom.get("aliases", []),
        )


def create_fault_tx(tx, rule):
    tx.run(
        """
        MERGE (f:Fault {id: $id})
        SET f.name = $name,
            f.display_name = $display_name,
            f.label_vi = $label_vi,
            f.system_id = $system_id,
            f.subsystem_id = $subsystem_id,
            f.status = $status
        """,
        id=rule["fault_id"],
        name=rule["fault_name"],
        display_name=rule.get("display_name", rule["fault_name"]),
        label_vi=rule.get("label_vi", rule.get("display_name", rule["fault_name"])),
        system_id=rule["system_id"],
        subsystem_id=rule["subsystem_id"],
        status=rule.get("status", "pending_review"),
    )


def create_affects_edge_tx(tx, rule, component_id):
    tx.run(
        """
        MATCH (f:Fault {id: $fault_id})
        MATCH (c:Component {id: $component_id})
        MERGE (f)-[r:AFFECTS]->(c)
        SET r.status = $status
        """,
        fault_id=rule["fault_id"],
        component_id=component_id,
        status=rule.get("status", "pending_review"),
    )


def create_symptom_edge_tx(tx, rule, symptom, symptom_aliases):
    symptom_id = symptom["symptom_id"]
    symptom_data = symptom_aliases[symptom_id]
    tx.run(
        """
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
        """,
        fault_id=rule["fault_id"],
        symptom_id=symptom_id,
        symptom_name=symptom_data["name"],
        display_name=symptom_data.get("display_name", symptom_data["name"]),
        label_vi=symptom_data.get("label_vi", symptom_data.get("display_name", symptom_data["name"])),
        aliases=symptom_data.get("aliases", []),
        cf=float(symptom["cf"]),
        priority=int(symptom.get("priority", 2)),
        status=rule.get("status", "pending_review"),
    )


def create_repair_edge_tx(tx, rule, repair):
    repair_name = repair.get("repair_name") or repair.get("name")
    tx.run(
        """
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
        """,
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


def import_rules(args):
    validate_all(str(args.ontology), str(args.symptom_aliases), str(args.path))

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
                    session.execute_write(create_symptom_edge_tx, rule, symptom, symptom_aliases)

                for repair in rule.get("repairs", []):
                    session.execute_write(create_repair_edge_tx, rule, repair)

            session.execute_write(generate_related_faults_tx)
    finally:
        driver.close()

    print(f"Imported {len(rules)} rules into Neo4j")


def import_knowledge_graph(args):
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
                    session.execute_write(create_symptom_edge_tx, rule, symptom, symptom_aliases)

                for repair in rule.get("repairs", []):
                    session.execute_write(create_repair_edge_tx, rule, repair)

            session.execute_write(generate_related_faults_tx)
    finally:
        driver.close()

    print("Rebuilt ontology-driven KG successfully")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import automotive knowledge graph into Neo4j.")
    parser.add_argument("--path", type=Path, default=RULES_PATH, help="Knowledge rules path")
    parser.add_argument("--ontology", type=Path, default=ONTOLOGY_PATH, help="Vehicle ontology path")
    parser.add_argument("--symptom-aliases", type=Path, default=SYMPTOM_ALIASES_PATH, help="Symptom aliases path")
    parser.add_argument("--clear", action="store_true", help="Clear database before import")
    parser.add_argument(
        "--mode",
        choices=("rules", "graph"),
        default="graph",
        help="Import just the rules graph or rebuild ontology + symptoms + rules.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.mode == "rules":
        import_rules(args)
    else:
        import_knowledge_graph(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
