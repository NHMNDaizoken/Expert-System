"""
Cleanup script — run once to delete stale files and __pycache__ directories.

Run from project root:
    python scripts/dev/cleanup_stale_files.py
"""
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FILES_TO_DELETE = [
    PROJECT_ROOT / "scripts" / "graph" / "import_neo4j.py",
    PROJECT_ROOT / "backend" / "config.py",
    PROJECT_ROOT / "backend" / "dependencies.py",
]


def main():
    # Delete stale files
    for path in FILES_TO_DELETE:
        if path.exists():
            path.unlink()
            print(f"Deleted: {path.relative_to(PROJECT_ROOT)}")
        else:
            print(f"Already gone: {path.relative_to(PROJECT_ROOT)}")

    # Delete __pycache__ directories
    deleted_count = 0
    for pycache in PROJECT_ROOT.rglob("__pycache__"):
        if pycache.is_dir() and ".venv" not in str(pycache):
            shutil.rmtree(pycache)
            print(f"Deleted: {pycache.relative_to(PROJECT_ROOT)}")
            deleted_count += 1
    if deleted_count == 0:
        print("No __pycache__ directories found outside .venv")

    # Delete .pyc files
    for pyc in PROJECT_ROOT.rglob("*.pyc"):
        if ".venv" not in str(pyc):
            pyc.unlink()
            print(f"Deleted: {pyc.relative_to(PROJECT_ROOT)}")

    print("\nCleanup complete.")


if __name__ == "__main__":
    main()
