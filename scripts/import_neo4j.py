from __future__ import annotations

try:
    from import_graph import main
except ModuleNotFoundError:
    from scripts.import_graph import main


if __name__ == "__main__":
    raise SystemExit(main())
