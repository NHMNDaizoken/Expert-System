import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


def require_neo4j_config():
    missing = [
        name
        for name, value in {
            "NEO4J_URI": NEO4J_URI,
            "NEO4J_USER": NEO4J_USER,
            "NEO4J_PASSWORD": NEO4J_PASSWORD,
        }.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing Neo4j environment variable(s): "
            + ", ".join(missing)
        )

    return NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
