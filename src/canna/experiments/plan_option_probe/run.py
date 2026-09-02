"""Run the probe and write one aggregate report.

Offline only: no provider call, no embedding index, no database, no write
outside the report path this is given.

This module is experiment-only. It is not imported by any serving path,
it calls no provider, index or database, and nothing it produces is a
product contract.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from . import measure, real_view
from .corpus import SPLIT_HOLDOUT, SPLIT_PRIMARY, load_cases
from .options import OptionGenerationPolicy
from .sources import load_view_source


def _distribution(values: list[int]) -> dict[str, int]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": ordered[len(ordered) // 2],
        "max": ordered[-1],
        "sum": sum(ordered),
    }


def build_report(root: Path, split: str, with_real: bool) -> dict[str, object]:
    cases = load_cases(root, split=None if split == "all" else split)
    report = measure.run(root, cases, split)

    option_counts: list[int] = []
    raw_counts: list[int] = []
    plan_counts: list[int] = []
    for case in report.cases:
        option_counts.extend(case.requirement_option_counts)
        raw_counts.extend(case.raw_counts)
        plan_counts.append(case.plan_count)

    scale: dict[str, dict[str, int]] = {}
    for count in (2, 4, 8, 16):
        byte_values = [
            entry[1]
            for case in report.cases
            for entry in case.scale_estimates
            if entry[0] == count
        ]
        token_values = [
            entry[2]
            for case in report.cases
            for entry in case.scale_estimates
            if entry[0] == count
        ]
        scale[str(count)] = {
            "bytes": _distribution(byte_values),
            "estimated_tokens": _distribution(token_values),
        }

    policy = OptionGenerationPolicy()
    payload: dict[str, object] = {
        "experiment": "plan_option_offline_falsification",
        "split": split,
        "external_calls": {"hcx": 0, "embedding": 0, "database": 0},
        "policy": {
            "version": policy.policy_version,
            "max_requirements": policy.max_requirements,
            "max_options_per_requirement": policy.max_options_per_requirement,
            "join_beam": policy.join_beam,
            "max_plan_options": policy.max_plan_options,
        },
        "totals": report.totals,
        "pass": report.passed,
        "generation_status": dict(
            Counter(case.generation_status for case in report.cases)
        ),
        "blocking_reasons": dict(
            Counter(
                reason for case in report.cases for reason in case.blocking_reasons
            )
        ),
        "canonicalisation_codes": dict(
            Counter(
                code for case in report.cases for code in case.canonicalisation_codes
            )
        ),
        "non_requirement_reasons": dict(
            Counter(
                reason
                for case in report.cases
                for reason in case.non_requirement_reasons
            )
        ),
        "failures": dict(
            Counter(name for case in report.cases for name in case.failures)
        ),
        "distributions": {
            "requirement_options_per_requirement": _distribution(option_counts),
            "raw_candidates_per_requirement": _distribution(raw_counts),
            "plan_options_per_question": _distribution(plan_counts),
            "requirement_frames_per_question": _distribution(
                [case.frames_produced for case in report.cases]
            ),
        },
        "cap_boundary": {
            "at_or_over_option_cap": sum(
                1
                for value in option_counts
                if value >= policy.max_options_per_requirement
            ),
            "at_or_over_plan_cap": sum(
                1 for value in plan_counts if value >= policy.max_plan_options
            ),
            "at_or_over_requirement_cap": sum(
                1
                for case in report.cases
                if case.frames_produced >= policy.max_requirements
            ),
            "cases_with_lossy_discard": sum(
                1 for case in report.cases if case.lossy_discards
            ),
        },
        "prompt_budget_estimate": scale,
        "modifier_residue_cases": sum(
            1 for case in report.cases if case.modifier_residue
        ),
        "per_case": [
            {
                "test_id": case.test_id,
                "split": case.split,
                "capability": case.capability,
                "frames_expected": list(case.frames_expected),
                "frames_produced": case.frames_produced,
                "generation_status": case.generation_status,
                "plan_options": case.plan_count,
                "selectable": case.selectable_count,
                "requirement_options": list(case.requirement_option_counts),
                "lossy_discards": case.lossy_discards,
                "failures": list(case.failures),
                "blocking_reasons": list(case.blocking_reasons),
                "canonicalisation_codes": list(case.canonicalisation_codes),
            }
            for case in report.cases
        ],
    }

    if with_real:
        sources = {
            name: load_view_source(root / "tests" / "fixtures" / name)
            for name in {case.view_source for case in cases}
        }
        real = real_view.run(root, cases, sources)
        required = Counter()
        recalled = Counter()
        for item in real:
            required.update(item.required_by_kind)
            recalled.update(item.recalled_by_kind)
        payload["real_registry_anchor_availability"] = {
            "required_by_kind": dict(required),
            "recalled_by_kind": dict(recalled),
            "candidates_offered": _distribution(
                [item.candidates_offered for item in real]
            ),
            "cases_with_a_missing_anchor": sum(
                1
                for item in real
                if any(
                    item.recalled_by_kind.get(kind, 0) < value
                    for kind, value in item.required_by_kind.items()
                )
            ),
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split", choices=(SPLIT_PRIMARY, SPLIT_HOLDOUT, "all"), default=SPLIT_PRIMARY
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="")
    parser.add_argument("--with-real-registry", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    payload = build_report(root, args.split, args.with_real_registry)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
