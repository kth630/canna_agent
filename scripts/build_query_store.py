"""CLI: rebuild the query store and its Data Catalog from the immutable sources.

    uv run python scripts/build_query_store.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from canna.store.build import build


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=None, help="alternate store path")
    parser.add_argument("--catalog", type=Path, default=None, help="alternate data catalog path")
    arguments = parser.parse_args()
    summary = build(store_path=arguments.store, catalog_path=arguments.catalog)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
