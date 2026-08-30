"""Run the stage 1-A Runtime View retrieval probe and preserve its transcript.

Usage::

    python scripts/run_runtime_view_probe.py --split primary
    python scripts/run_runtime_view_probe.py --split unseen --repeats 3

The script owns fixture loading. ``canna.experiments.runtime_view_probe`` never
reads a fixture path, so nothing in the source tree depends on test material.

Everything the probe does is offline: no model call, no network, no source data.
Repeats exist to show that the candidate order and the retrieval decision do not
move between runs — only the request-scoped refs do.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from canna.experiments.runtime_view_probe.probe import ProbeCase, ProbeRecord, run_case, summarise
from canna.experiments.runtime_view_probe.registry import load_registry

FIXTURE_DIR = ROOT / "tests" / "fixtures"
DEFAULT_REGISTRY = FIXTURE_DIR / "runtime_view_registry.json"
DEFAULT_OUTPUT_DIR = ROOT / "provenance" / "experiments" / "stage_1_runtime_view"
SPLIT_FILES = {
    "primary": FIXTURE_DIR / "runtime_view_probe.jsonl",
    "unseen": FIXTURE_DIR / "runtime_view_probe_unseen.jsonl",
}


def read_jsonl(path: Path) -> Iterator[Mapping[str, object]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def case_of(record: Mapping[str, object]) -> ProbeCase:
    expected = record["expected_decision"]
    if not isinstance(expected, Mapping):
        raise TypeError(f"{record.get('test_id')} has no expected_decision object")
    budget = record.get("candidate_budget")
    return ProbeCase(
        case_key=str(record["test_id"]),
        question=str(record["question"]),
        required_candidate_ids=tuple(expected.get("required_candidate_ids", ())),
        required_neighbor_ids=tuple(expected.get("required_neighbor_ids", ())),
        candidate_budget=None if budget is None else int(budget),
    )


def order_is_stable(records: Sequence[ProbeRecord]) -> bool:
    return len({record.bundle.view.presentation_order() for record in records}) == 1


def refs_are_fresh(records: Sequence[ProbeRecord]) -> bool:
    seen: set[str] = set()
    for record in records:
        refs = set(record.bundle.view.refs())
        if refs & seen:
            return False
        seen |= refs
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=sorted(SPLIT_FILES), default="primary")
    parser.add_argument("--fixtures", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--label", default="")
    parser.add_argument("--dry-run", action="store_true", help="print the summary, write nothing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    registry = load_registry(json.loads(args.registry.read_text(encoding="utf-8")))
    fixtures = args.fixtures or SPLIT_FILES[args.split]
    cases = [case_of(record) for record in read_jsonl(fixtures)]

    per_case: dict[str, list[ProbeRecord]] = {}
    transcript: list[dict[str, object]] = []
    for repeat in range(max(1, args.repeats)):
        for case in cases:
            record = run_case(registry, case)
            per_case.setdefault(case.case_key, []).append(record)
            transcript.append({"repeat_index": repeat, **record.as_transcript_record()})

    first_pass = [records[0] for records in per_case.values()]
    summary = {
        "run": {
            "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "split": args.split,
            "label": args.label,
            "fixtures": fixtures.relative_to(ROOT).as_posix(),
            "registry": args.registry.relative_to(ROOT).as_posix(),
            "registry_id": registry.registry_id,
            "registry_authority": registry.authority,
            "repeats": max(1, args.repeats),
            "candidate_budget_default": registry.policy.candidate_budget,
            "neighbor_rules": list(registry.policy.neighbor_rules),
        },
        "determinism": {
            "cases_with_stable_order": sum(
                1 for records in per_case.values() if order_is_stable(records)
            ),
            "cases": len(per_case),
            "refs_never_reused_across_requests": refs_are_fresh(
                [record for records in per_case.values() for record in records]
            ),
        },
        "results": summarise(first_pass),
        "per_case": {
            key: {
                "question_recall": records[0].recall.recall,
                "per_family_recall": records[0].recall.per_family_recall(),
                "missing_required": [item.model_dump() for item in records[0].recall.missing],
                "neighbors_missing": list(records[0].recall.neighbors_missing),
                "status": records[0].outcome.status,
                "executable": records[0].outcome.executable,
                "failure_kinds": list(records[0].outcome.failure_kinds()),
                "candidate_count": records[0].bundle.metrics.candidate_count,
                "serialized_bytes": records[0].bundle.metrics.serialized_bytes,
                "total_latency_ms": round(
                    records[0].retrieval_latency_ms + records[0].view_latency_ms, 3
                ),
                "order_stable_across_repeats": order_is_stable(records),
            }
            for key, records in sorted(per_case.items())
        },
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"_{args.label}" if args.label else ""
    out_dir = args.out_dir / f"{stamp}_{args.split}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (out_dir / "transcript.jsonl").open("w", encoding="utf-8") as handle:
        for record in transcript:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {out_dir.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
