"""CLI: project a bounded ABox sample from the query store and validate it with SHACL.

    uv run python scripts/project_abox.py

The sample is evidence that the store's rows can be expressed as instances of the
submission ontology.  It is not the runtime query path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from canna.graph.project import OUTPUT_PATH, project


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--subjects-per-family", type=int, default=8)
    parser.add_argument("--observations-per-subject", type=int, default=6)
    parser.add_argument("--no-validate", action="store_true")
    arguments = parser.parse_args()

    graph, counts = project(
        output=arguments.output,
        subjects_per_family=arguments.subjects_per_family,
        observations_per_subject=arguments.observations_per_subject,
    )
    summary: dict[str, object] = {"triples": len(graph), "instances": counts}
    if not arguments.no_validate:
        from pyshacl import validate
        from rdflib import Graph

        shapes = Graph()
        for path in sorted((Path(__file__).resolve().parents[1] / "ontology").glob("*.ttl")):
            shapes.parse(path, format="turtle")
        conforms, _, report = validate(
            data_graph=graph, shacl_graph=shapes, ont_graph=shapes,
            inference="rdfs", advanced=True,
        )
        summary["shacl_conforms"] = conforms
        if not conforms:
            summary["shacl_report"] = report
    summary["status"] = "ok" if summary.get("shacl_conforms", True) else "shacl_violation"
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
