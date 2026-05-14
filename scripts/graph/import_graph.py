"""
Import automotive knowledge graph into Neo4j.

This script imports ontology, symptoms, faults, and repair procedures
into a Neo4j graph database for the automotive diagnostic expert system.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import _bootstrap  # type: ignore # noqa: F401
except ModuleNotFoundError:
    from scripts import _bootstrap  # type: ignore # noqa: F401
from src.expert_system.config import require_neo4j_config
from src.expert_system.knowledge.loader import extract_rules
from src.expert_system.utils.text import slugify
from scripts.validate.validate_knowledge import validate_all


ONTOLOGY_PATH = PROJECT_ROOT / "data" / "staging" / "ontology.json"
SYMPTOM_ALIASES_PATH = PROJECT_ROOT / "data" / "staging" / "symptom_aliases.json"
RULES_PATH = PROJECT_ROOT / "data" / "staging" / "kg_rules_from_dataset.json"
DECISION_TREES_STAGING = PROJECT_ROOT / "data" / "staging" / "decision_trees.json"


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
    tx.run("CREATE CONSTRAINT decision_tree_id IF NOT EXISTS FOR (n:DecisionTree) REQUIRE n.id IS UNIQUE")
    tx.run("CREATE CONSTRAINT question_id IF NOT EXISTS FOR (n:Question) REQUIRE n.id IS UNIQUE")
    tx.run("CREATE CONSTRAINT result_id IF NOT EXISTS FOR (n:Result) REQUIRE n.id IS UNIQUE")


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
            f.status = $status,
            f.causes = $causes,
            f.severity = $severity,
            f.safety_notes = $safety_notes,
            f.diagnostic_steps = $diagnostic_steps
        """,
        id=rule["fault_id"],
        name=rule["fault_name"],
        display_name=rule.get("display_name", rule["fault_name"]),
        label_vi=rule.get("label_vi", rule.get("display_name", rule["fault_name"])),
        system_id=rule["system_id"],
        subsystem_id=rule["subsystem_id"],
        status=rule.get("status", "pending_review"),
        causes=rule.get("causes", []),
        severity=rule.get("severity", "medium"),
        safety_notes=rule.get("safety_notes", []),
        diagnostic_steps=rule.get("diagnostic_steps", []),
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
            r.status = $status,
            r.repair_steps = $steps

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

def validate_decision_tree(tree_record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tree = tree_record.get("tree") or {}
    nodes = tree.get("nodes") or []
    node_map = {node.get("node_id"): node for node in nodes if isinstance(node, dict)}
    root_id = tree.get("root_node_id")
    if not root_id or root_id not in node_map:
        errors.append(f"{tree_record.get('candidate_id')}: root_node_id does not exist")
    for node_id, node in node_map.items():
        if node.get("type") == "question":
            for branch in ("yes_next", "no_next", "unknown_next"):
                target = node.get(branch)
                if not target or target not in node_map:
                    errors.append(f"{tree_record.get('candidate_id')}:{node_id}.{branch} has dangling target {target}")
        elif node.get("type") == "result":
            if not node.get("fault"):
                errors.append(f"{tree_record.get('candidate_id')}:{node_id} result is missing fault")
            if not node.get("repair_steps"):
                errors.append(f"{tree_record.get('candidate_id')}:{node_id} result is missing repair_steps")
        else:
            errors.append(f"{tree_record.get('candidate_id')}:{node_id} has invalid type")
    return errors

def validate_decision_trees(trees: list[dict[str, Any]]) -> None:
    errors = []
    for tree in trees:
        errors.extend(validate_decision_tree(tree))
    if errors:
        raise ValueError("Invalid decision tree import:\n" + "\n".join(errors))

def import_decision_tree_tx(tx, tree_record):
    candidate_id = tree_record.get("candidate_id")
    root_symptom = tree_record.get("root_symptom") or {}
    tree = tree_record.get("tree") or {}
    root_label = root_symptom.get("label_vi") or root_symptom.get("symptom_id") or candidate_id
    symptom_id = "SYM_" + slugify(root_label).upper()
    tree_id = f"DT_{candidate_id}"
    root_question_id = f"{tree_id}_{tree.get('root_node_id')}"

    tx.run(
        """
        MERGE (s:Symptom {id: $symptom_id})
        SET s.name = $symptom_name,
            s.display_name = $label,
            s.label_vi = $label,
            s.aliases = $aliases
        MERGE (dt:DecisionTree {id: $tree_id})
        SET dt.candidate_id = $candidate_id,
            dt.source = $source,
            dt.root_node_id = $root_node_id,
            dt.selected_paths = $selected_paths
        MERGE (s)-[:HAS_DECISION_TREE]->(dt)
        """,
        symptom_id=symptom_id,
        symptom_name=root_symptom.get("symptom_id") or symptom_id,
        label=root_label,
        aliases=root_symptom.get("aliases", []),
        tree_id=tree_id,
        candidate_id=candidate_id,
        source=tree_record.get("source", "expert_approved_llm_tree"),
        root_node_id=tree.get("root_node_id"),
        selected_paths=[str(path) for path in tree_record.get("selected_paths", [])],
    )

    for node in tree.get("nodes", []):
        node_graph_id = f"{tree_id}_{node.get('node_id')}"
        if node.get("type") == "question":
            tx.run(
                """
                MERGE (q:Question {id: $id})
                SET q.node_id = $node_id,
                    q.question = $question,
                    q.answer_type = $answer_type,
                    q.purpose = $purpose
                """,
                id=node_graph_id,
                node_id=node.get("node_id"),
                question=node.get("question"),
                answer_type=node.get("answer_type", "yes_no"),
                purpose=node.get("purpose"),
            )
        else:
            fault = node.get("fault") or {}
            repair_id = f"REP_{fault.get('fault_id') or node.get('node_id')}"
            tx.run(
                """
                MERGE (res:Result {id: $result_id})
                SET res.node_id = $node_id,
                    res.causes = $causes,
                    res.diagnostic_steps = $diagnostic_steps,
                    res.repair_steps = $repair_steps,
                    res.safety_notes = $safety_notes,
                    res.when_to_stop = $when_to_stop
                MERGE (f:Fault {id: $fault_id})
                SET f.name = $fault_name,
                    f.display_name = $fault_name,
                    f.label_vi = $fault_name,
                    f.system_id = $system,
                    f.severity = $severity,
                    f.confidence = $confidence,
                    f.causes = $causes,
                    f.diagnostic_steps = $diagnostic_steps,
                    f.safety_notes = $safety_notes
                MERGE (res)-[:DIAGNOSES]->(f)
                MERGE (f)-[:HAS_SYMPTOM]->(s:Symptom {id: $symptom_id})
                MERGE (r:Repair {id: $repair_id})
                SET r.name = $repair_name,
                    r.display_name = $repair_name,
                    r.label_vi = $repair_name,
                    r.steps = $repair_steps,
                    r.repair_steps = $repair_steps
                MERGE (f)-[:FIXED_BY]->(r)
                """,
                result_id=node_graph_id,
                node_id=node.get("node_id"),
                causes=node.get("causes", []),
                diagnostic_steps=node.get("diagnostic_steps", []),
                repair_steps=node.get("repair_steps", []),
                safety_notes=node.get("safety_notes", []),
                when_to_stop=node.get("when_to_stop", []),
                fault_id=fault.get("fault_id"),
                fault_name=fault.get("fault_name") or fault.get("fault_id"),
                system=fault.get("system", "unknown"),
                severity=fault.get("severity", "medium"),
                confidence=float(fault.get("confidence") or 0),
                symptom_id=symptom_id,
                repair_id=repair_id,
                repair_name=f"Quy trình sửa: {fault.get('fault_name') or fault.get('fault_id')}",
            )
            for component in node.get("components", []):
                component_id = component.get("component_id")
                if component_id:
                    tx.run(
                        """
                        MERGE (c:Component {id: $component_id})
                        SET c.name = $name, c.display_name = $name, c.label_vi = $name
                        WITH c
                        MATCH (f:Fault {id: $fault_id})
                        MERGE (f)-[:AFFECTS]->(c)
                        """,
                        component_id=component_id,
                        name=component.get("name_vi") or component_id,
                        fault_id=fault.get("fault_id"),
                    )

    tx.run(
        """
        MATCH (dt:DecisionTree {id: $tree_id})
        MATCH (q:Question {id: $root_question_id})
        MERGE (dt)-[:HAS_ROOT_QUESTION]->(q)
        """,
        tree_id=tree_id,
        root_question_id=root_question_id,
    )
    node_map = {node.get("node_id"): node for node in tree.get("nodes", [])}
    for node in tree.get("nodes", []):
        if node.get("type") != "question":
            continue
        source_id = f"{tree_id}_{node.get('node_id')}"
        for branch, rel_type in (("yes_next", "YES"), ("no_next", "NO"), ("unknown_next", "UNKNOWN")):
            target_node = node_map[node.get(branch)]
            target_id = f"{tree_id}_{target_node.get('node_id')}"
            tx.run(
                f"""
                MATCH (source:Question {{id: $source_id}})
                MATCH (target {{id: $target_id}})
                WHERE target:Question OR target:Result
                MERGE (source)-[:{rel_type}]->(target)
                """,
                source_id=source_id,
                target_id=target_id,
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


DECISION_TREES_STAGING = PROJECT_ROOT / "data" / "staging" / "decision_trees.json"


def import_knowledge_graph(args):
    ontology = load_json(args.ontology)
    symptom_aliases = load_json(args.symptom_aliases)
    data = load_json(args.path)
    rules = extract_rules(data)
    decision_trees: list[dict[str, Any]] = []
    if getattr(args, "import_decision_trees", False):
        dt_path = Path(args.decision_trees_path)
        if dt_path.exists():
            blob = load_json(dt_path)
            if isinstance(blob, dict) and isinstance(blob.get("trees"), list):
                decision_trees = [t for t in blob["trees"] if isinstance(t, dict)]
            elif isinstance(blob, list):
                decision_trees = [t for t in blob if isinstance(t, dict)]
        if decision_trees:
            validate_decision_trees(decision_trees)
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

            for tree in decision_trees:
                session.execute_write(import_decision_tree_tx, tree)

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
    parser.add_argument(
        "--import-decision-trees",
        action="store_true",
        help="Import optional LLM Yes/No tree nodes (DecisionTree/Question/Result) from staging decision_trees.json for debugging.",
    )
    parser.add_argument(
        "--decision-trees-path",
        type=Path,
        default=DECISION_TREES_STAGING,
        help="Path to decision_trees.json when --import-decision-trees is set.",
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
