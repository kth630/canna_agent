"""Scoring one run, and the failure taxonomy it reports.

Every number here is an aggregate. No question text, no per-request reference
and no stable semantic identifier reaches the report: a case contributes its
test identifier, its counts and its failure codes, and nothing else. That is
the reporting boundary the task set, and it is also what makes the report safe
to keep in provenance.

The pass conditions are the seven the task named. Each one is counted
separately so that a run that fails one of them cannot be reported as a partial
success of the others.

This module is experiment-only. It is not imported by any serving path,
it calls no provider, index or database, and nothing it produces is a
product contract.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from canna.runtime_view.contract import STATUS_MAPPED

from . import options as opt
from . import presentation
from .corpus import Case, expected_kinds, gold_detail_slots, gold_span_anchors
from .ledger import (
    ROLE_AGGREGATION_FUNCTION,
    ROLE_COMPARISON_OPERATOR,
    ROLE_CONDITION_VALUE,
    ROLE_LIMIT,
    ROLE_ORDER_DIRECTION,
    ROLE_RELATIONSHIP,
    ROLE_UNRESOLVED_MODIFIER,
    SpanLedger,
    build_ledger,
)
from .sources import ViewSource, load_view_source

FAILURE_ANCHOR_KEY_MISSING = "required_candidate_key_not_recalled"
FAILURE_SPAN_ANCHOR_MISSING = "required_span_anchor_not_covered"
FAILURE_OPERATION_ANCHOR_MISSING = "required_operation_slot_not_recognised"
FAILURE_FRAME_COUNT = "requirement_frame_count_mismatch"
FAILURE_FRAME_KIND = "requirement_frame_kind_mismatch"
FAILURE_NON_REQUIREMENT = "content_span_classified_as_non_requirement"
FAILURE_UNPROVIDED_COMBINATION = "option_used_a_candidate_the_view_did_not_bind"
FAILURE_STATE_COLLAPSE = "semantic_canonicalisation_execution_states_collapsed"
FAILURE_LOSSY_TRUNCATION = "lossy_truncation_reported_as_success"
FAILURE_PAYLOAD_LEAK = "plan_payload_leaked_a_forbidden_value"

# Which ledger role answers which gold detail slot.
_SLOT_ROLES = {
    "condition": (ROLE_COMPARISON_OPERATOR, ROLE_CONDITION_VALUE),
    "order": (ROLE_ORDER_DIRECTION,),
    "limit": (ROLE_LIMIT,),
    "aggregation": (ROLE_AGGREGATION_FUNCTION,),
    "relationship": (ROLE_RELATIONSHIP,),
}


@dataclass
class CaseResult:
    test_id: str
    split: str
    capability: str
    frames_expected: tuple[int, ...]
    frames_produced: int
    generation_status: str
    plan_count: int
    selectable_count: int
    requirement_option_counts: tuple[int, ...]
    raw_counts: tuple[int, ...]
    pruned_counts: tuple[int, ...]
    partial_plans: int
    plans_before_cap: int
    lossy_discards: int
    payload_bytes: int
    payload_tokens: int
    scale_estimates: tuple[tuple[int, int, int], ...]
    failures: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    canonicalisation_codes: tuple[str, ...]
    non_requirement_reasons: tuple[str, ...]
    modifier_residue: int
    required_keys: int
    keys_without_a_span: int


@dataclass
class RunReport:
    split: str
    cases: tuple[CaseResult, ...]
    totals: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(case.failures for case in self.cases)


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def _covered_by_a_frame(ledger: SpanLedger, question: str, anchor: str) -> bool:
    needle = _normalise(anchor)
    start = question.find(needle)
    while start != -1:
        end = start + len(needle)
        if any(frame.start <= start and end <= frame.end for frame in ledger.frames):
            return True
        start = question.find(needle, start + 1)
    return False


def _recalled_keys(ledger: SpanLedger) -> set[str]:
    return {key for span in ledger.spans for key in span.candidate_keys}


def _option_keys(result: opt.PlanOptionSet) -> set[str]:
    """References the generator actually put in an option.

    Not every required anchor is written in the question. A target named only by
    one of its products -- "this ETF's holdings" -- is derived from the entity's
    own dataset membership, and demanding a span for it would score a correct
    derivation as a miss. Recall is therefore measured over what the generator
    produced, with span coverage reported separately.
    """
    keys: set[str] = set()
    for options in result.requirement_options.values():
        for option in options:
            keys.update(option.target_keys)
            keys.update(option.output_field_keys)
            keys.update(option.comparison_operand_keys)
            keys.update(
                item
                for item in (
                    option.ordering_field_key,
                    option.aggregation_field_key,
                    option.relationship_key,
                    option.relationship_anchor_key,
                )
                if item
            )
            keys.update(item.field_key for item in option.conditions)
    return keys


def _non_requirement_swallowed(
    ledger: SpanLedger, question: str, anchors: Sequence[str]
) -> tuple[str, ...]:
    """A gold anchor must never end up classified as a function word."""
    swallowed: list[str] = []
    for anchor in anchors:
        needle = _normalise(anchor)
        start = question.find(needle)
        if start == -1:
            continue
        end = start + len(needle)
        overlap = [
            item
            for item in ledger.non_requirement
            if item.start < end and start < item.end
        ]
        content = [item for item in overlap if item.end - item.start > 1]
        if content and not any(
            span.start < end and start < span.end for span in ledger.spans
        ):
            swallowed.append(FAILURE_NON_REQUIREMENT)
    return tuple(dict.fromkeys(swallowed))


def _unprovided_combination(
    result: opt.PlanOptionSet, source: ViewSource
) -> bool:
    """Every reference an option uses has to exist and be bound to its target."""
    for options in result.requirement_options.values():
        for option in options:
            for target_key in option.target_keys:
                if source.get(target_key) is None:
                    return True
            for key in (
                *option.output_field_keys,
                option.ordering_field_key,
                option.aggregation_field_key,
            ):
                if not key:
                    continue
                candidate = source.get(key)
                if candidate is None:
                    return True
                if option.target_keys and not set(candidate.dataset_keys) & set(
                    option.target_keys
                ):
                    return True
            for condition in option.conditions:
                candidate = source.get(condition.field_key)
                if candidate is None:
                    return True
                if option.target_keys and not set(candidate.dataset_keys) & set(
                    option.target_keys
                ):
                    return True
    return False


def _states_collapsed(result: opt.PlanOptionSet) -> bool:
    """A selectable option must not be claiming execution readiness."""
    for options in result.requirement_options.values():
        for option in options:
            if option.semantic_status == STATUS_MAPPED and option.execution_readiness not in (
                opt.READINESS_BLOCKED,
                opt.READINESS_NOT_EVALUATED,
            ):
                return True
            if (
                option.canonicalization_status == opt.CANONICALIZATION_READY
                and option.canonicalization_failures
            ):
                return True
    return False


def run_case(root: Path, case: Case, source: ViewSource) -> CaseResult:
    question = _normalise(case.question)
    ledger = build_ledger(case.question, source)
    result = opt.generate(question, ledger, source)

    failures: list[str] = []

    span_keys = _recalled_keys(ledger)
    recalled = span_keys | _option_keys(result)
    required = set(case.required_keys) - {""}
    if required - recalled:
        failures.append(FAILURE_ANCHOR_KEY_MISSING)
    span_only_missing = len(required - span_keys)

    anchors = gold_span_anchors(case)
    if any(not _covered_by_a_frame(ledger, question, item) for item in anchors):
        failures.append(FAILURE_SPAN_ANCHOR_MISSING)
    failures.extend(_non_requirement_swallowed(ledger, question, anchors))

    roles_present = {role for span in ledger.spans for role in span.roles}
    for slot in gold_detail_slots(case):
        wanted = _SLOT_ROLES.get(slot, ())
        if wanted and not set(wanted) & roles_present:
            failures.append(FAILURE_OPERATION_ANCHOR_MISSING)
            break

    produced = len(ledger.frames)
    if produced not in case.requirement_counts:
        failures.append(FAILURE_FRAME_COUNT)
    else:
        for frame, allowed in zip(
            ledger.frames, expected_kinds(case, produced), strict=False
        ):
            if not allowed:
                continue
            if frame.kind not in allowed and not set(frame.kind_alternatives) & set(
                allowed
            ):
                failures.append(FAILURE_FRAME_KIND)
                break

    if _unprovided_combination(result, source):
        failures.append(FAILURE_UNPROVIDED_COMBINATION)
    if _states_collapsed(result):
        failures.append(FAILURE_STATE_COLLAPSE)
    if result.lossy_discards and result.selectable_plans:
        failures.append(FAILURE_LOSSY_TRUNCATION)

    payload = presentation.payload_for(result.plan_options, source)
    if presentation.leaked_values(payload, source):
        failures.append(FAILURE_PAYLOAD_LEAK)
    measured = presentation.estimate(payload, len(result.plan_options))
    scaled = presentation.scale_estimates(result.plan_options, source)

    return CaseResult(
        test_id=case.test_id,
        split=case.split,
        capability=case.capability,
        frames_expected=case.requirement_counts,
        frames_produced=produced,
        generation_status=result.generation_status,
        plan_count=len(result.plan_options),
        selectable_count=len(result.selectable_plans),
        requirement_option_counts=tuple(
            len(options) for options in result.requirement_options.values()
        ),
        raw_counts=tuple(item.raw for item in result.requirement_metrics),
        pruned_counts=tuple(item.deduplicated for item in result.requirement_metrics),
        partial_plans=result.partial_plans_considered,
        plans_before_cap=result.plan_options_before_cap,
        lossy_discards=result.lossy_discards,
        payload_bytes=measured.bytes_utf8,
        payload_tokens=measured.estimated_tokens,
        scale_estimates=tuple(
            (item.option_count, item.bytes_utf8, item.estimated_tokens)
            for item in scaled
        ),
        failures=tuple(dict.fromkeys(failures)),
        blocking_reasons=tuple(
            dict.fromkeys(
                reason
                for options in result.requirement_options.values()
                for option in options
                for reason in option.blocking_reasons
            )
        ),
        canonicalisation_codes=tuple(
            dict.fromkeys(
                code
                for options in result.requirement_options.values()
                for option in options
                for code in option.canonicalization_failures
            )
        ),
        non_requirement_reasons=tuple(
            sorted({item.reason for item in ledger.non_requirement})
        ),
        modifier_residue=len(
            [
                span
                for span in ledger.spans
                if ROLE_UNRESOLVED_MODIFIER in span.roles
            ]
        ),
        required_keys=len(required),
        keys_without_a_span=span_only_missing,
    )


def run(root: Path, cases: Sequence[Case], split: str) -> RunReport:
    sources: dict[str, ViewSource] = {}
    results: list[CaseResult] = []
    for case in cases:
        if case.view_source not in sources:
            sources[case.view_source] = load_view_source(
                Path(root) / "tests" / "fixtures" / case.view_source
            )
        results.append(run_case(root, case, sources[case.view_source]))

    totals: dict[str, int] = {"cases": len(results)}
    for name in (
        FAILURE_ANCHOR_KEY_MISSING,
        FAILURE_SPAN_ANCHOR_MISSING,
        FAILURE_OPERATION_ANCHOR_MISSING,
        FAILURE_FRAME_COUNT,
        FAILURE_FRAME_KIND,
        FAILURE_NON_REQUIREMENT,
        FAILURE_UNPROVIDED_COMBINATION,
        FAILURE_STATE_COLLAPSE,
        FAILURE_LOSSY_TRUNCATION,
        FAILURE_PAYLOAD_LEAK,
    ):
        totals[name] = sum(1 for item in results if name in item.failures)
    totals["required_anchor_keys"] = sum(item.required_keys for item in results)
    totals["anchor_keys_recalled_only_by_derivation"] = sum(
        item.keys_without_a_span for item in results
    )
    totals["selectable_cases"] = sum(1 for item in results if item.selectable_count)
    totals["blocked_cases"] = sum(1 for item in results if not item.selectable_count)
    return RunReport(split=split, cases=tuple(results), totals=totals)
