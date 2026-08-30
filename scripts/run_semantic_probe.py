"""Run the stage 0-A semantic grounding probe and preserve redacted transcripts.

Usage::

    python scripts/run_semantic_probe.py --split primary --repeats 3
    python scripts/run_semantic_probe.py --split verification --encodings nested

The script owns fixture loading. ``canna.experiments.semantic_probe`` never
reads a fixture path, so nothing in the source tree depends on test material.

Candidate ordering: repeat 0 always uses the order the fixture authored, and
each further repeat shuffles the candidate list with a seed derived from
``--order-seed``, the test id and the repeat index. The seed and the resulting
order are written into every transcript record, so any run can be replayed.
"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from canna.experiments.semantic_probe.encodings import ENCODINGS
from canna.experiments.semantic_probe.probe import ProbeCase, run_case, summarise
from canna.experiments.semantic_probe.provider import API_KEY_ENV, HcxSemanticProvider
from canna.experiments.semantic_probe.runtime_view import CandidateCatalog, RefMinter
from canna.experiments.semantic_probe.transcript import write_records

DEFAULT_FIXTURE_DIR = ROOT / "tests" / "fixtures"
DEFAULT_CATALOG = DEFAULT_FIXTURE_DIR / "semantic_probe_catalog.json"
DEFAULT_OUTPUT_DIR = ROOT / "provenance" / "experiments" / "stage_0a_semantic_grounding"
SPLIT_FILES = {
    "primary": DEFAULT_FIXTURE_DIR / "semantic_grounding.jsonl",
    "regression": DEFAULT_FIXTURE_DIR / "semantic_grounding_regression.jsonl",
    "verification": DEFAULT_FIXTURE_DIR / "semantic_grounding_verification.jsonl",
}


def read_jsonl(path: Path) -> Iterator[Mapping[str, object]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path, override=False)


def order_seed_for(base_seed: int, test_id: str, repeat_index: int) -> int | None:
    """Derive a reproducible candidate order for one repeat.

    Repeat 0 keeps the authored order so a permuted run can be compared against
    the arrangement the fixture was written in.
    """
    if repeat_index == 0:
        return None
    return (base_seed * 1_000_003 + zlib.crc32(test_id.encode("utf-8")) + repeat_index) % (2**31)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=sorted(SPLIT_FILES), default="primary")
    parser.add_argument("--fixtures", type=Path, default=None)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--encodings", nargs="*", default=sorted(ENCODINGS))
    parser.add_argument("--timeout", type=int, default=40)
    parser.add_argument("--repeats", type=int, default=1, help="candidate orderings per case")
    parser.add_argument("--order-seed", type=int, default=20260830)
    parser.add_argument("--limit", type=int, default=0, help="run only the first N fixtures")
    parser.add_argument("--only", nargs="*", default=[], help="run only these test ids")
    parser.add_argument("--label", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env(ROOT / ".env")
    if not HcxSemanticProvider.credentials_available():
        print(f"missing {API_KEY_ENV}; nothing was called", file=sys.stderr)
        return 2

    fixture_path = args.fixtures or SPLIT_FILES[args.split]
    catalog = CandidateCatalog.from_mapping(json.loads(args.catalog.read_text(encoding="utf-8")))
    cases = [ProbeCase.from_fixture(record) for record in read_jsonl(fixture_path)]
    if args.only:
        selected = set(args.only)
        cases = [case for case in cases if case.test_id in selected]
    if args.limit:
        cases = cases[: args.limit]
    provider = HcxSemanticProvider(timeout=args.timeout)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.out_dir / f"{stamp}_{args.split}{('_' + args.label) if args.label else ''}"
    summaries: dict[str, object] = {}
    for encoding_name in args.encodings:
        encoding = ENCODINGS[encoding_name]
        runs = []
        for repeat_index in range(max(1, args.repeats)):
            for case in cases:
                seed = order_seed_for(args.order_seed, case.test_id, repeat_index)
                run = run_case(case, encoding, catalog, provider, RefMinter(), seed, repeat_index)
                runs.append(run)
                if run.passed:
                    status = "pass"
                elif run.score is not None:
                    status = "FAIL"
                else:
                    status = run.provider_result.outcome
                print(
                    f"[{encoding_name}#{repeat_index}] {case.test_id}: {status} "
                    f"({run.provider_result.latency_ms:.0f} ms)"
                )
        write_records(run_dir / f"transcript_{encoding_name}.jsonl", (r.as_record() for r in runs))
        summaries[encoding_name] = summarise(runs)

    summary_payload = {
        "stage": "0-A",
        "split": args.split,
        "fixture_file": str(fixture_path.relative_to(ROOT)),
        "catalog_file": str(args.catalog.relative_to(ROOT)),
        "case_count": len(cases),
        "repeats": max(1, args.repeats),
        "order_seed_base": args.order_seed,
        "order_rule": "repeat 0 uses the authored order; later repeats shuffle with "
        "(base_seed * 1000003 + crc32(test_id) + repeat_index) % 2**31",
        "started_utc": stamp,
        "encodings": summaries,
    }
    summary_path = run_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
    print(f"\nwritten: {run_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
