"""Run a question-free threshold/top-k sweep over the local Registry index.

The JSON result is written to stdout so it can be reviewed before selected
metrics are recorded in provenance.  This command makes no external API calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from canna.retrieval.evaluation import cross_form_sweep
from canna.retrieval.index import DEFAULT_INDEX_PATH, assert_usable, load_index
from canna.retrieval.vocabulary import load_vocabulary


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    )
    parser.add_argument("--top-k", type=int, nargs="+", default=[1, 3, 5, 10, 20, 50])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    vocabulary = load_vocabulary(arguments.registry)
    index = load_index(arguments.index)
    assert_usable(index, vocabulary, index.identity)
    report = cross_form_sweep(
        vocabulary,
        index,
        thresholds=arguments.thresholds,
        top_ks=arguments.top_k,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
