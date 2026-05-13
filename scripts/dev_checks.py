import argparse
from pprint import pprint

try:
    import _bootstrap  # type: ignore # noqa: F401
except ModuleNotFoundError:
    from scripts import _bootstrap  # type: ignore # noqa: F401
from src.expert_system.knowledge.loader import DEFAULT_STAGING_DIR, extract_rules, load_json
from src.expert_system.inference.fuzzy import SymptomMatcher
from src.expert_system.inference.engine import ExpertSystemEngine


DEFAULT_INPUTS = [
    "ABS warning light on",
    "brake pedal pulsation",
    "random unknown symptom",
]


def _file_engine():
    return ExpertSystemEngine.from_staging()


def check_neo4j(_args):
    from neo4j import GraphDatabase
    from src.config import require_neo4j_config

    uri, user, password = require_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            result = session.run("RETURN 'connected' AS msg")
            print(result.single()["msg"])
    finally:
        driver.close()


def check_normalizer(args):
    matcher = SymptomMatcher(load_json(DEFAULT_STAGING_DIR / "symptom_aliases.json"))

    for text in args.inputs:
        print("\nInput:", text)
        print("Matches:")
        pprint(matcher.match(text))


def check_rules(args):
    rules = extract_rules(load_json(DEFAULT_STAGING_DIR / "kg_rules_from_dataset.json"))
    matching_rules = [
        {
            "fault_id": rule.get("fault_id"),
            "fault_name": rule.get("fault_name"),
            "display_name": rule.get("display_name"),
            "matched_symptoms": [
                symptom
                for symptom in rule.get("symptoms", [])
                if symptom.get("symptom_id") == args.symptom_id
            ],
            "repairs": rule.get("repairs", []),
            "affected_components": rule.get("affected_components", []),
        }
        for rule in rules
        if any(
            symptom.get("symptom_id") == args.symptom_id
            for symptom in rule.get("symptoms", [])
        )
    ]

    print(f"Rules containing {args.symptom_id}:")
    pprint(matching_rules)


def check_inference(args):
    engine = KGInference.from_neo4j() if args.neo4j else _file_engine()

    try:
        for text in args.inputs:
            print("\n==============================")
            print("Input:", text)
            pprint(engine.diagnose(text, top_k=args.top_k))
    finally:
        engine.close()


def build_parser():
    parser = argparse.ArgumentParser(description="Manual development checks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    neo4j_parser = subparsers.add_parser("neo4j")
    neo4j_parser.set_defaults(func=check_neo4j)

    normalizer_parser = subparsers.add_parser(
        "normalizer",
        help="Show symptom matching using the current KGInference matcher.",
    )
    normalizer_parser.add_argument("inputs", nargs="*", default=DEFAULT_INPUTS)
    normalizer_parser.set_defaults(func=check_normalizer)

    rules_parser = subparsers.add_parser(
        "rules",
        help="Show staging rules linked to one symptom id.",
    )
    rules_parser.add_argument("symptom_id", nargs="?", default="SYM_ABS_WARNING_LIGHT_ON")
    rules_parser.set_defaults(func=check_rules)

    inference_parser = subparsers.add_parser(
        "inference",
        help="Run the current KGInference engine.",
    )
    inference_parser.add_argument("inputs", nargs="*", default=DEFAULT_INPUTS)
    inference_parser.add_argument("--top-k", type=int, default=5)
    inference_parser.add_argument(
        "--neo4j",
        action="store_true",
        help="Use Neo4j instead of staging JSON files.",
    )
    inference_parser.set_defaults(func=check_inference)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
