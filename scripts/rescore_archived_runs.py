"""Re-score preserved stage 0-A transcripts under the current pass criteria.

This separates two questions that a single pass rate cannot answer:

* how much of the change came from tightening the criteria, and
* how much came from changing the Runtime View and the prompt.

Archived runs predate the detail slots, so detail checks are switched off and
the report says so. Everything else in the current criteria — requirement
count, span verbatimness, span anchors, span distinctness, ref integrity and
dataset selection — is applied unchanged.

The archive is read only. Results are written to a new file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from canna.experiments.semantic_probe.model import QuestionSemantics
from canna.experiments.semantic_probe.probe import ProbeCase
from canna.experiments.semantic_probe.runtime_view import CandidateCatalog, rebuild_view
from canna.experiments.semantic_probe.scoring import score_result

DEFAULT_FIXTURE_DIR = ROOT / "tests" / "fixtures"
DEFAULT_CATALOG = DEFAULT_FIXTURE_DIR / "semantic_probe_catalog.json"
FIXTURE_FILES = (
    DEFAULT_FIXTURE_DIR / "semantic_grounding.jsonl",
    DEFAULT_FIXTURE_DIR / "semantic_grounding_regression.jsonl",
    DEFAULT_FIXTURE_DIR / "semantic_grounding_verification.jsonl",
)


def load_cases() -> dict[str, ProbeCase]:
    cases: dict[str, ProbeCase] = {}
    for path in FIXTURE_FILES:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                cases[str(record["test_id"])] = ProbeCase.from_fixture(record)
    return cases


def rescore_file(
    path: Path, catalog: CandidateCatalog, cases: Mapping[str, ProbeCase]
) -> dict[str, object]:
    total = 0
    scored = 0
    passed = 0
    unmatched: list[str] = []
    per_case: dict[str, list[bool]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        total += 1
        case = cases.get(str(record["test_id"]))
        decoded = record.get("decoded")
        if case is None:
            unmatched.append(str(record["test_id"]))
            continue
        if decoded is None:
            continue
        view = rebuild_view(catalog, record["ref_key_map"])
        semantics = QuestionSemantics.model_validate(decoded)
        score = score_result(
            str(record["question"]), view, semantics, case.expectation, check_details=False
        )
        scored += 1
        passed += 1 if score.case_pass else 0
        per_case[str(record["test_id"])].append(score.case_pass)
    return {
        "transcript": str(path.resolve().relative_to(ROOT)),
        "records": total,
        "rescored": scored,
        "passed": passed,
        "pass_rate": round(passed / scored, 4) if scored else None,
        "detail_checks": False,
        "fixtures_not_found": sorted(set(unmatched)),
        "failed_test_ids": sorted(
            test_id for test_id, results in per_case.items() if not all(results)
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    catalog = CandidateCatalog.from_mapping(json.loads(args.catalog.read_text(encoding="utf-8")))
    cases = load_cases()
    report = {
        "purpose": "archived stage 0-A runs re-scored under the current criteria",
        "detail_slot_checks": "disabled — the archived wire format had no detail slots",
        "runs": [],
    }
    for run_dir in args.run_dirs:
        for transcript in sorted(run_dir.glob("transcript_*.jsonl")):
            report["runs"].append(rescore_file(transcript, catalog, cases))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
