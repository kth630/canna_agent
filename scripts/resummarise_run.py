"""Recompute a run's summary from its preserved transcripts.

Used when the aggregation rule changes after a run was recorded. The original
``summary.json`` and the transcripts are left untouched; the recomputed figures
are written to ``summary_recomputed.json`` beside them.

Order stability is recomputed over scored runs only, so a provider refusal no
longer makes a case look order-sensitive.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def summarise_transcript(path: Path) -> dict[str, object]:
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    scored = [r for r in records if r["score"] is not None]
    provider_failures = [r for r in records if r["response"]["outcome"] == "provider_error"]
    model_failures = [
        r for r in records if r["response"]["outcome"].startswith("model_")
    ]
    by_case: dict[str, list[bool]] = defaultdict(list)
    for record in scored:
        by_case[record["test_id"]].append(bool(record["score"]["case_pass"]))
    all_ids = {r["test_id"] for r in records}
    always = sorted(t for t, v in by_case.items() if all(v))
    never = sorted(t for t, v in by_case.items() if not any(v))
    unstable = sorted(set(by_case) - set(always) - set(never))
    latencies = [
        r["response"]["latency_ms"] for r in records if r["response"]["outcome"] != "provider_error"
    ]
    recalls = [r["score"]["requirement_recall"] for r in scored]
    return {
        "transcript": path.name,
        "runs": len(records),
        "cases": len(all_ids),
        "scored_runs": len(scored),
        "provider_failures": len(provider_failures),
        "provider_error_codes": sorted(
            {r["response"]["error_code"] for r in provider_failures if r["response"]["error_code"]}
        ),
        "model_response_failures": len(model_failures),
        "run_pass_rate": _ratio(sum(1 for r in scored if r["score"]["case_pass"]), len(scored)),
        "cases_with_at_least_one_scored_run": len(by_case),
        "case_pass_rate_all_scored_repeats": _ratio(len(always), len(by_case)),
        "ref_integrity_rate": _ratio(
            sum(1 for r in scored if r["score"]["ref_integrity"]), len(scored)
        ),
        "mean_requirement_recall": round(sum(recalls) / len(recalls), 4) if recalls else None,
        "latency_ms_mean": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "stable_pass_test_ids": always,
        "stable_fail_test_ids": never,
        "order_sensitive_test_ids": unstable,
        "never_scored_test_ids": sorted(all_ids - set(by_case)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for run_dir in args.run_dirs:
        payload = {
            "recomputed_from": "transcript_*.jsonl",
            "rule": "order stability counts scored runs only",
            "encodings": {
                path.stem.replace("transcript_", ""): summarise_transcript(path)
                for path in sorted(run_dir.glob("transcript_*.jsonl"))
            },
        }
        out = run_dir / "summary_recomputed.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n### {run_dir.name}")
        for name, stats in payload["encodings"].items():
            print(
                f"{name:13s} scored={stats['scored_runs']:2d}/{stats['runs']:2d} "
                f"prov_fail={stats['provider_failures']:2d} "
                f"run_pass={stats['run_pass_rate']} "
                f"all_repeat={stats['case_pass_rate_all_scored_repeats']} "
                f"ref={stats['ref_integrity_rate']} recall={stats['mean_requirement_recall']} "
                f"lat={stats['latency_ms_mean']}/{stats['latency_ms_max']}"
            )
            print(f"              order_sensitive={stats['order_sensitive_test_ids']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
