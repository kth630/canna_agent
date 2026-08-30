"""CLI: generate the Semantic Registry from the ontology and the Execution Registry
from the Data Catalog, failing when the two disagree.

    uv run python scripts/build_registries.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from canna.registry.execution import RegistryMismatch, write_execution_registry
from canna.registry.semantic import write_registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic-only", action="store_true", help="skip the Execution Registry")
    arguments = parser.parse_args()

    semantic = write_registry()
    summary: dict[str, object] = {"semantic_registry": semantic["counts"]}
    if not arguments.semantic_only:
        try:
            execution = write_execution_registry()
        except RegistryMismatch as error:
            print(json.dumps({"status": "mismatch", "detail": str(error)}, ensure_ascii=False))
            return 1
        summary["execution_registry"] = execution["counts"]
        summary["hash_mismatches"] = execution["data_catalog"]["hash_mismatches"]
    summary["status"] = "ok"
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
