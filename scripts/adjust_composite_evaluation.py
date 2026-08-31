"""Re-score a stored composite report against a gold audit, without any call.

The original report is read, never rewritten.  The adjusted numbers are written
to a separate file that names the audit it applied, so both the published
measurement and its correction remain inspectable side by side.

A verification pass first re-scores the unaudited gold from the stored candidate
lists and compares it against the report's own numbers.  If the reconstruction
does not reproduce what was published, the adjustment is refused rather than
reported.
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

from canna.retrieval.composite import CompositeError, load_composite_proposal
from canna.retrieval.composite_audit import (
    apply_audit,
    entity_mention_counts,
    load_audit,
    rescore,
    restorable_top_k,
    restore_prepared,
)
from canna.retrieval.vocabulary import load_vocabulary

WORKSTREAM = (
    ROOT
    / "provenance"
    / "workstreams"
    / "20260830_preintegration_parallel"
    / "f_ontology_registry_retriever"
)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--questions", type=Path, default=WORKSTREAM / "COMPOSITE_RETRIEVAL_PROPOSAL.jsonl"
    )
    parser.add_argument(
        "--audit", type=Path, default=WORKSTREAM / "COMPOSITE_RETRIEVAL_GOLD_AUDIT_20260831.json"
    )
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, nargs="+", default=[5, 10, 20])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    vocabulary = load_vocabulary(arguments.registry)
    metadata, cases = load_composite_proposal(
        arguments.questions, vocabulary, approval_reference=arguments.approval_reference
    )
    envelope = json.loads(arguments.report.read_text(encoding="utf-8"))
    report = envelope["report"]
    if report["registry_content_hash"] != vocabulary.content_hash:
        raise CompositeError("the stored report was produced against another Registry hash")
    if envelope.get("questions_sha256") != metadata.get("questions_sha256"):
        raise CompositeError("the stored report was produced from another question set")

    depth = restorable_top_k(report)
    ks = tuple(value for value in sorted(set(arguments.top_k)) if value <= depth)
    if not ks:
        raise CompositeError(f"the stored report supports no requested top-k (depth {depth})")

    restored = restore_prepared(vocabulary, report, cases)
    verification = rescore(vocabulary, restored, top_ks=ks)
    published = {
        row["top_k"]: row["merged"]["all_required_recall"]
        for row in report["path_recall_by_kind"]
        if row["top_k"] in ks
    }
    reconstructed = {
        row["top_k"]: row["merged"]["all_required_recall"]
        for row in verification["path_recall_by_kind"]
    }
    if published != reconstructed:
        raise CompositeError(
            "offline reconstruction does not reproduce the published numbers: "
            f"published={published} reconstructed={reconstructed}"
        )

    audit = load_audit(arguments.audit)
    kept, ledger = apply_audit(vocabulary, restored, audit)
    adjusted = rescore(vocabulary, kept, top_ks=ks)
    output = {
        "experiment": "composite_retrieval_gold_adjusted_rescore",
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "offline rescore of stored candidate lists; no embedding call was made",
        "source_report": str(arguments.report.as_posix()),
        "audit_id": audit.get("audit_id", ""),
        "proposal_id": metadata.get("proposal_id", ""),
        "approval_reference": metadata["approval_reference"],
        "registry_content_hash": vocabulary.content_hash,
        "questions_sha256": metadata.get("questions_sha256", ""),
        "question_text_in_report": False,
        "restorable_top_k": depth,
        "reconstruction_matches_published": True,
        "reconstruction_check": {"published": published, "reconstructed": reconstructed},
        "audit_ledger": ledger,
        "scored_case_count": len(kept),
        "excluded_case_ids": [row["case_id"] for row in ledger if not row["scored"]],
        "entity_mentions_scored": entity_mention_counts(kept),
        "entity_mentions_all_cases": entity_mention_counts(restored),
        "withdrawn_claims": audit.get("withdrawn_claims", []),
        "withdrawn_claim_basis": audit.get("withdrawn_claim_basis", ""),
        "adjusted": adjusted,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote adjusted rescore: {arguments.output}")
    print(f"reconstruction matched published merged recall at top-k {list(ks)}")
    print(f"scored cases: {len(kept)} (excluded: {output['excluded_case_ids']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
