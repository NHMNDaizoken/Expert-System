"""
dev_checks — Manual development checks for normalizer, rules, inference, and neo4j.

Run from project root:
    python scripts/dev/dev_checks.py [command] [args]

Commands:
    normalizer <text>   Test symptom normalization
    rules <symptom_id>  Show matching rules for a symptom
    inference <text>    Run inference on a symptom description
    neo4j               Check Neo4j connectivity
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_normalizer(text: str) -> None:
    from src.expert_system.inference.fuzzy import SymptomMatcher
    from src.expert_system.knowledge.loader import KnowledgeBase

    kb = KnowledgeBase.from_staging()
    matcher = SymptomMatcher(kb.symptom_aliases)
    matches = matcher.match(text)
    print(f"Input: {text}")
    print(f"Matches ({len(matches)}):")
    for match in matches:
        print(f"  {match['symptom_id']} (score={match.get('score', '?')})")


def check_rules(symptom_id: str) -> None:
    from src.expert_system.knowledge.loader import KnowledgeBase

    kb = KnowledgeBase.from_staging()
    found = [
        rule for rule in kb.rules
        if any(s["symptom_id"] == symptom_id for s in rule.get("symptoms", []))
    ]
    print(f"Rules matching {symptom_id}: {len(found)}")
    for rule in found:
        print(f"  {rule['fault_id']} — {rule.get('display_name', rule.get('fault_name', '?'))}")


def check_inference(text: str) -> None:
    from src.expert_system.inference.engine import ExpertSystemEngine

    engine = ExpertSystemEngine.from_staging()
    result = engine.diagnose(text, top_k=5)
    print(f"Input: {text}")
    print(f"Status: {result.get('status')}")
    for diagnosis in result.get("diagnoses", []):
        print(f"  {diagnosis.get('fault_id')} CF={diagnosis.get('final_cf', '?')}")


def check_neo4j() -> None:
    from src.expert_system.config import require_neo4j_config
    from neo4j import GraphDatabase

    uri, user, password = require_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS count").single()
            print(f"Neo4j connected: {result['count']} nodes")
    finally:
        driver.close()


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0

    command = args[0].lower()
    if command == "normalizer" and len(args) >= 2:
        check_normalizer(" ".join(args[1:]))
    elif command == "rules" and len(args) >= 2:
        check_rules(args[1])
    elif command == "inference" and len(args) >= 2:
        check_inference(" ".join(args[1:]))
    elif command == "neo4j":
        check_neo4j()
    else:
        print(f"Unknown command or missing arguments: {command}")
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
