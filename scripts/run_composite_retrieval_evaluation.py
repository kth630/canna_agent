"""Run the approved composite-question evaluation against one model index.

Question text is read locally and sent only to CLOVA Studio for embedding.  It
is never printed or copied into the JSON report.  Run this only after the user
approves the proposal and supply that approval as ``--approval-reference``.

The candidate-kind budgets are an experiment grid, not a product setting: they
are simulated offline over the merged candidate order and never written back to
the runtime retrieval configuration.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from canna.retrieval.composite import (
    evaluate_composite,
    load_composite_proposal,
)
from canna.retrieval.embedding import (
    MODEL_PROFILES,
    ClovaStudioEmbeddings,
    load_dotenv_if_present,
)
from canna.retrieval.index import comparison_index_path, load_index
from canna.retrieval.settings import RuleSettings
from canna.retrieval.vocabulary import load_vocabulary

DEFAULT_PROPOSAL = (
    ROOT
    / "provenance"
    / "workstreams"
    / "20260830_preintegration_parallel"
    / "f_ontology_registry_retriever"
    / "COMPOSITE_RETRIEVAL_PROPOSAL.jsonl"
)

# Experiment grid only. Each row is one hypothesis about how many seats each
# candidate kind should get, to be compared against the same merged order under
# a single global cap. No row is a recommendation.
DEFAULT_BUDGET_GRID = (
    {"dataset": 3, "field": 12, "predicate": 4, "identifier": 1},
    {"dataset": 4, "field": 10, "predicate": 5, "identifier": 1},
    {"dataset": 4, "field": 16, "predicate": 6, "identifier": 4},
    {"dataset": 6, "field": 20, "predicate": 8, "identifier": 6},
)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=sorted(MODEL_PROFILES))
    parser.add_argument("--index", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--questions", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, nargs="+", default=[5, 10, 20, 30])
    parser.add_argument(
        "--budget-grid",
        type=str,
        default=None,
        help="JSON list of {kind: seats} objects; omission uses the recorded experiment grid",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--min-interval", type=float, default=0.6)
    parser.add_argument(
        "--offline-validate-only",
        action="store_true",
        help="validate the proposal against the Registry without calling the provider",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    load_dotenv_if_present(ROOT)
    vocabulary = load_vocabulary(arguments.registry)
    metadata, cases = load_composite_proposal(
        arguments.questions,
        vocabulary,
        approval_reference=arguments.approval_reference,
    )
    if arguments.offline_validate_only:
        print(f"proposal validated: {len(cases)} cases (no provider call)")
        print(f"registry hash: {vocabulary.content_hash}")
        return 0

    budget_grid = (
        tuple(json.loads(arguments.budget_grid))
        if arguments.budget_grid
        else DEFAULT_BUDGET_GRID
    )
    index = load_index(arguments.index or comparison_index_path(arguments.model))
    provider = ClovaStudioEmbeddings(
        model=arguments.model,
        timeout=arguments.timeout,
        min_interval_seconds=arguments.min_interval,
    )
    report = evaluate_composite(
        vocabulary,
        index,
        provider,
        cases,
        rule_settings=RuleSettings(),
        top_ks=arguments.top_k,
        budget_grid=budget_grid,
    )
    envelope = {
        "experiment": "approved_composite_retrieval_evaluation",
        "generated_at": datetime.now(UTC).isoformat(),
        "proposal_id": metadata.get("proposal_id", ""),
        "approval_reference": metadata["approval_reference"],
        "proposal_status_at_run": metadata.get("approval_status", ""),
        "questions_sha256": metadata.get("questions_sha256", ""),
        "question_text_in_report": False,
        "report": report,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote composite evaluation report: {arguments.output}")
    print(f"model: {arguments.model}")
    print(f"registry hash: {vocabulary.content_hash}")
    print(f"cases: {len(cases)} (question text omitted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
