"""Run one purpose-based question fixture against one wire encoding.

Experiment only. The probe knows nothing about which questions exist. A caller
supplies fixture records and a candidate catalog; the probe mints
request-scoped refs, permutes the candidate order, calls the provider, decodes
with the encoding under test and scores the result.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .encodings import Encoding
from .model import QuestionSemantics, RuntimeView
from .provider import OUTCOME_OK, HcxSemanticProvider, ProviderResult
from .runtime_view import CandidateCatalog, RefMinter
from .scoring import Expectation, Score, score_result


@dataclass(frozen=True)
class ProbeCase:
    """A fixture record reduced to what the probe needs to execute it."""

    test_id: str
    capability_under_test: str
    question: str
    candidate_keys: tuple[str, ...]
    expectation: Expectation

    @classmethod
    def from_fixture(cls, record: Mapping[str, object]) -> ProbeCase:
        view_keys = record.get("runtime_view_candidate_keys")
        if not isinstance(view_keys, Sequence) or isinstance(view_keys, (str, bytes)):
            raise TypeError(f"{record.get('test_id')!r} needs runtime_view_candidate_keys")
        expected = record.get("expected_decision")
        if not isinstance(expected, Mapping):
            raise TypeError(f"{record.get('test_id')!r} needs a structured expected_decision")
        return cls(
            test_id=str(record["test_id"]),
            capability_under_test=str(record.get("capability_under_test", "")),
            question=str(record["question"]),
            candidate_keys=tuple(str(key) for key in view_keys),
            expectation=Expectation.from_mapping(expected),
        )


@dataclass(frozen=True)
class CaseRun:
    """One provider call plus its decoding and scoring."""

    case: ProbeCase
    encoding_name: str
    runtime_view: RuntimeView
    provider_result: ProviderResult
    semantics: QuestionSemantics | None
    score: Score | None
    order_seed: int | None = None
    repeat_index: int = 0

    @property
    def scored(self) -> bool:
        return self.score is not None

    @property
    def passed(self) -> bool:
        return self.score is not None and self.score.case_pass

    def as_record(self) -> dict[str, object]:
        """Full audit record: request view, raw response, decoding and score."""
        result = self.provider_result
        return {
            "test_id": self.case.test_id,
            "capability_under_test": self.case.capability_under_test,
            "encoding": self.encoding_name,
            "repeat_index": self.repeat_index,
            "order_seed": self.order_seed,
            "candidate_presentation_order": list(self.runtime_view.presentation_order),
            "question": self.case.question,
            "request": {
                "runtime_view": self.runtime_view.as_prompt_payload(),
                "request_bytes": result.request_bytes,
            },
            "ref_key_map": self.runtime_view.key_by_ref(),
            "response": {
                "outcome": result.outcome,
                "attempts": result.attempts,
                "latency_ms": round(result.latency_ms, 1),
                "raw_tool_calls": [dict(call) for call in result.raw_tool_calls],
                "response_text": result.response_text,
                "error_kind": result.error_kind,
                "error_code": result.error_code,
                "error_message": result.error_message,
            },
            "decoded": (
                self.semantics.model_dump(mode="json") if self.semantics is not None else None
            ),
            "score": self.score.as_dict() if self.score is not None else None,
        }


def run_case(
    case: ProbeCase,
    encoding: Encoding,
    catalog: CandidateCatalog,
    provider: HcxSemanticProvider,
    minter: RefMinter | None = None,
    order_seed: int | None = None,
    repeat_index: int = 0,
) -> CaseRun:
    runtime_view = catalog.build_view(case.candidate_keys, minter or RefMinter(), order_seed)
    result = provider.call(case.question, runtime_view, encoding)
    semantics: QuestionSemantics | None = None
    score: Score | None = None
    if result.outcome == OUTCOME_OK and result.arguments is not None:
        semantics = encoding.decode(result.arguments)
        score = score_result(case.question, runtime_view, semantics, case.expectation)
    return CaseRun(
        case=case,
        encoding_name=encoding.name,
        runtime_view=runtime_view,
        provider_result=result,
        semantics=semantics,
        score=score,
        order_seed=order_seed,
        repeat_index=repeat_index,
    )


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def summarise(runs: Sequence[CaseRun]) -> dict[str, object]:
    """Aggregate one encoding's runs, keeping provider and model failures apart."""
    provider_failures = [run for run in runs if run.provider_result.failed_at_provider]
    model_failures = [run for run in runs if run.provider_result.failed_at_model]
    scored = [run for run in runs if run.scored]
    latencies = [
        run.provider_result.latency_ms for run in runs if not run.provider_result.failed_at_provider
    ]
    passed = [run for run in scored if run.passed]
    ref_clean = [run for run in scored if run.score is not None and run.score.ref_integrity]
    recalls = [run.score.requirement_recall for run in scored if run.score is not None]
    precisions = [run.score.requirement_precision for run in scored if run.score is not None]

    # Order stability is a property of scored runs. A provider refusal says
    # nothing about whether candidate order changed the model's decision, so it
    # must not be counted as an unstable case.
    by_case: dict[str, list[CaseRun]] = defaultdict(list)
    for run in scored:
        by_case[run.case.test_id].append(run)
    all_case_ids = {run.case.test_id for run in runs}
    always_pass = sorted(
        test_id for test_id, group in by_case.items() if all(item.passed for item in group)
    )
    never_pass = sorted(
        test_id for test_id, group in by_case.items() if not any(item.passed for item in group)
    )
    unstable = sorted(set(by_case) - set(always_pass) - set(never_pass))
    unscored_cases = sorted(all_case_ids - set(by_case))

    return {
        "runs": len(runs),
        "cases": len(all_case_ids),
        "repeats_per_case": round(len(runs) / len(all_case_ids), 2) if all_case_ids else 0,
        "cases_with_at_least_one_scored_run": len(by_case),
        "provider_failures": len(provider_failures),
        "provider_error_codes": sorted(
            {
                run.provider_result.error_code
                for run in provider_failures
                if run.provider_result.error_code
            }
        ),
        "model_response_failures": len(model_failures),
        "scored_runs": len(scored),
        "run_pass_rate": _ratio(len(passed), len(scored)),
        "case_pass_rate_all_scored_repeats": _ratio(len(always_pass), len(by_case)),
        "scored_repeats_per_case": {
            test_id: len(group) for test_id, group in sorted(by_case.items())
        },
        "ref_integrity_rate": _ratio(len(ref_clean), len(scored)),
        "mean_requirement_recall": round(statistics.fmean(recalls), 4) if recalls else None,
        "mean_requirement_precision": (
            round(statistics.fmean(precisions), 4) if precisions else None
        ),
        "latency_ms_mean": round(statistics.fmean(latencies), 1) if latencies else None,
        "latency_ms_max": round(max(latencies), 1) if latencies else None,
        "request_bytes_mean": (
            round(statistics.fmean([float(run.provider_result.request_bytes) for run in runs]), 1)
            if runs
            else None
        ),
        "stable_pass_test_ids": always_pass,
        "stable_fail_test_ids": never_pass,
        "order_sensitive_test_ids": unstable,
        "never_scored_test_ids": unscored_cases,
    }
