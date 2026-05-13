"""Wrapper — runs import_neo4j from the new scripts/graph/ location."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_neo4j import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
