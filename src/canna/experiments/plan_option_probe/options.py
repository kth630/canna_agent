"""RequirementOption and PlanOption generation, and the caps that bound it.

This is the part of the proposal that decides whether server-side pre-generation
is affordable at all. Section 6 orders the hard prunes; section 7 sets four
provisional caps and one rule that makes them safe -- discarding a candidate
that means something different is not a smaller answer, it is a wrong one, so a
single lossy discard blocks the whole option set.

Three states are kept apart on purpose, because collapsing them is the failure
the contract exists to prevent. ``semantic_status`` says whether the meaning was
placed on allowed references. ``canonicalization_status`` says whether the
server could read the question's own words for the operator, the direction, the
count and the function. ``execution_readiness`` says whether the Execution
Registry could actually serve it. A requirement can be mapped, unreadable and
unservable at the same time, and each has to be visible separately.

Coverage and freshness never delete a meaning. They are carried as execution
constraints, which is what ARCHITECTURE.md section 6 requires: an incomplete
population changes what may be claimed, not what was asked.

This module is experiment-only. It is not imported by any serving path,
it calls no provider, index or database, and nothing it produces is a
product contract.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from canna.runtime_view.canonicalize import (
    OPERATION_AGGREGATE,
    OPERATION_FILTER,
    OPERATION_ORDER,
    FieldMetadata,
    canonicalize_aggregation,
    canonicalize_comparison,
    canonicalize_limit,
    canonicalize_ordering,
)
from canna.runtime_view.contract import (
    AVAILABLE_CANONICALIZERS,
    KIND_CANONICALIZERS,
    REQUIREMENT_KIND_COUNT,
    STATUS_AMBIGUOUS,
    STATUS_MAPPED,
    STATUS_UNRESOLVED,
)

from .ledger import (
    ROLE_AGGREGATION_FUNCTION,
    ROLE_COMPARISON_OPERATOR,
    ROLE_CONDITION_FIELD,
    ROLE_CONDITION_VALUE,
    ROLE_ENTITY,
    ROLE_FIELD,
    ROLE_LIMIT,
    ROLE_NESTED_REUSE,
    ROLE_ORDER_DIRECTION,
    ROLE_RELATIONSHIP,
    ROLE_TARGET,
    ROLE_UNRESOLVED_ANCHOR,
    ROLE_UNRESOLVED_MODIFIER,
    RequirementFrame,
    Span,
    SpanLedger,
)
from .lexicon import fixture_operation_code, fixture_unit_code
from .sources import (
    AXIS_CURRENCY,
    AXIS_DOMAIN_RANGE,
    AXIS_FAMILY,
    AXIS_GRAIN,
    AXIS_OPERATION,
    AXIS_PERIOD,
    AXIS_UNIT,
    ViewCandidate,
    ViewSource,
)

CANONICALIZATION_READY = "ready"
CANONICALIZATION_REFUSED = "refused"
CANONICALIZATION_UNAVAILABLE = "unavailable"

READINESS_NOT_EVALUATED = "not_evaluated"
READINESS_BLOCKED = "blocked"

GENERATION_COMPLETE = "complete"
GENERATION_CHOICE_REQUIRED = "choice_required"
GENERATION_NO_CANDIDATE = "no_candidate"
GENERATION_MATERIALLY_AMBIGUOUS = "materially_ambiguous"
GENERATION_TRUNCATED = "truncated"

REASON_TRUNCATED = "candidate_space_truncated"
REASON_STRUCTURE_LIMIT = "structure_limit_exceeded"
REASON_MISSING_TARGET = "missing_target_dataset"
REASON_UNRESOLVED_ANCHOR = "anchor_has_no_runtime_view_candidate"
REASON_UNACCOUNTED_MODIFIER = "unaccounted_modifier_span"
REASON_FIELD_PRUNED_FROM_TARGET = "field_span_not_bound_to_this_target"
REASON_PRUNE_AXIS_UNAVAILABLE = "prune_axis_unavailable"
REASON_CANONICALIZER_UNAVAILABLE = "canonicalizer_unavailable"
REASON_CANONICALIZATION_REFUSED = "canonicalization_refused"
REASON_HOMONYM_NO_DISCRIMINATOR = "same_span_candidates_differ_without_discriminator"
REASON_EQUIVALENT_BINDING_COLLAPSED = "equivalent_binding_collapsed"
REASON_OPERAND_INCOMPATIBLE = "comparison_operands_are_not_on_one_scale"
REASON_PROVENANCE_UNAVAILABLE = "execution_provenance_binding_unavailable"


@dataclass(frozen=True)
class OptionGenerationPolicy:
    """The caps, owned in one place and provisional until measured.

    These are the proposal's section 7 numbers. They are not approved constants;
    the experiment exists in part to report the distribution they would bind.
    """

    max_requirements: int = 8
    max_options_per_requirement: int = 8
    join_beam: int = 32
    max_plan_options: int = 16
    nested_depth: int = 1
    comparison_operands: int = 2
    policy_version: str = "offline_probe_provisional_v1"


@dataclass(frozen=True)
class Condition:
    field_key: str
    operator: str
    value: str
    comparison_span: str
    value_span: str


@dataclass(frozen=True)
class RequirementOption:
    requirement_id: str
    kind: str
    semantic_status: str
    canonicalization_status: str
    execution_readiness: str
    target_keys: tuple[str, ...]
    output_field_keys: tuple[str, ...]
    conditions: tuple[Condition, ...]
    ordering_field_key: str
    ordering_direction: str
    limit: int
    aggregation_field_key: str
    aggregation_function: str
    relationship_key: str
    relationship_anchor_key: str
    relationship_direction: str
    result_reuse_of: str
    comparison_operand_keys: tuple[str, ...]
    canonicalization_failures: tuple[str, ...]
    execution_constraints: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    equivalence_key: str
    span_texts: tuple[str, ...]

    @property
    def selectable(self) -> bool:
        return (
            self.semantic_status == STATUS_MAPPED
            and self.canonicalization_status == CANONICALIZATION_READY
        )


@dataclass(frozen=True)
class PlanOption:
    plan_ref: str
    requirement_options: tuple[RequirementOption, ...]
    plan_status: str
    equivalence_key: str
    execution_constraints: tuple[str, ...]
    blocking_reasons: tuple[str, ...]

    @property
    def selectable(self) -> bool:
        return self.plan_status == "candidate_selectable"


@dataclass
class RequirementMetrics:
    requirement_id: str
    kind: str
    raw: int
    pruned: int
    deduplicated: int
    prune_by_axis: dict[str, int] = field(default_factory=dict)
    lossy_truncated: int = 0


@dataclass
class PlanOptionSet:
    generation_status: str
    generation_reasons: tuple[str, ...]
    requirement_metrics: tuple[RequirementMetrics, ...]
    requirement_options: Mapping[str, tuple[RequirementOption, ...]]
    plan_options: tuple[PlanOption, ...]
    partial_plans_considered: int
    plan_options_before_cap: int
    lossy_discards: int
    policy: OptionGenerationPolicy

    @property
    def selectable_plans(self) -> tuple[PlanOption, ...]:
        return tuple(item for item in self.plan_options if item.selectable)


def _digest(payload: object) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _metadata(candidate: ViewCandidate) -> FieldMetadata:
    """What the canonicalisers are told about a field, in their own vocabulary.

    ``currency_policy`` is deliberately left empty. In the real Registry it
    names a *policy* -- where a row's currency comes from -- and a field that
    has one cannot be compared against a written amount. The synthetic sources
    instead carry a fixed currency *code* on every field including percentages,
    so passing it through would refuse every percentage comparison for a reason
    that is a fixture artefact rather than a fact about the data. The code is
    still used, on its own axis, to prune incompatible comparison operands.
    """
    return FieldMetadata(
        semantic_id=candidate.key,
        unit_code=fixture_unit_code(candidate.unit),
        period_code=candidate.period,
        currency_policy="",
        allowed_operations=tuple(
            fixture_operation_code(item) for item in candidate.allowed_operations
        ),
    )


def _belongs(candidate: ViewCandidate, target_key: str) -> bool:
    return target_key in candidate.dataset_keys


def _grain_compatible(candidate: ViewCandidate, target: ViewCandidate) -> bool:
    if not candidate.grains or not target.grains:
        return False
    return bool(set(candidate.grains) & set(target.grains))


def _first(spans: Sequence[Span]) -> Span | None:
    return spans[0] if spans else None


def _targets_for(
    frame: RequirementFrame,
    inherited: Sequence[str],
    source: ViewSource,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The dataset candidates this requirement is about, and why if there are none."""
    named = tuple(
        dict.fromkeys(
            key
            for span in frame.spans
            if ROLE_TARGET in span.roles
            for key in span.candidate_keys
        )
    )
    if named:
        return named, ()
    if inherited:
        return tuple(inherited), ()
    entities = tuple(
        dict.fromkeys(
            key
            for span in frame.spans
            if ROLE_ENTITY in span.roles
            for key in span.candidate_keys
        )
    )
    for key in entities:
        candidate = source.get(key)
        if candidate and candidate.dataset_keys:
            return tuple(candidate.dataset_keys), ()
    return (), (REASON_MISSING_TARGET,)


def _field_options(
    frame: RequirementFrame,
    role: str,
    target: ViewCandidate,
    source: ViewSource,
    operation: str,
    metrics: RequirementMetrics,
) -> tuple[list[ViewCandidate], list[str]]:
    """Candidates for one field slot, after the section 6 hard prunes."""
    reasons: list[str] = []
    spans = frame.of_role(role)
    survivors: list[ViewCandidate] = []
    for span in spans:
        for key in span.candidate_keys:
            candidate = source.get(key)
            if candidate is None:
                continue
            metrics.raw += 1
            if not candidate.declares(AXIS_FAMILY) or not candidate.declares(
                AXIS_GRAIN
            ):
                metrics.prune_by_axis[REASON_PRUNE_AXIS_UNAVAILABLE] = (
                    metrics.prune_by_axis.get(REASON_PRUNE_AXIS_UNAVAILABLE, 0) + 1
                )
                reasons.append(REASON_PRUNE_AXIS_UNAVAILABLE)
                continue
            if not _belongs(candidate, target.key):
                metrics.prune_by_axis[AXIS_FAMILY] = (
                    metrics.prune_by_axis.get(AXIS_FAMILY, 0) + 1
                )
                continue
            if not _grain_compatible(candidate, target):
                metrics.prune_by_axis[AXIS_GRAIN] = (
                    metrics.prune_by_axis.get(AXIS_GRAIN, 0) + 1
                )
                continue
            if operation and candidate.declares(AXIS_OPERATION):
                allowed = {
                    fixture_operation_code(item)
                    for item in candidate.allowed_operations
                }
                if operation not in allowed:
                    metrics.prune_by_axis[AXIS_OPERATION] = (
                        metrics.prune_by_axis.get(AXIS_OPERATION, 0) + 1
                    )
                    continue
            survivors.append(candidate)
    return survivors, reasons


def _discriminators(candidate: ViewCandidate) -> tuple[str, str, str, tuple[str, ...]]:
    """The declared facts that tell two same-named candidates apart.

    An axis the source is silent about is returned as the empty string rather
    than as a match, so two candidates that declare nothing are never treated as
    proven equivalent.
    """
    return (
        candidate.period if candidate.declares(AXIS_PERIOD) else "",
        candidate.unit if candidate.declares(AXIS_UNIT) else "",
        candidate.currency if candidate.declares(AXIS_CURRENCY) else "",
        tuple(sorted(candidate.grains)),
    )


def _homonym_conflict(
    frame: RequirementFrame, role: str, survivors: Sequence[ViewCandidate]
) -> tuple[bool, list[ViewCandidate], list[str]]:
    """Sort same-named survivors into a real ambiguity and a mere duplication.

    Two candidates the question named with the very same words are only a
    material ambiguity if their declared period, unit, currency or grain differ
    -- then two different user meanings survive and nobody may choose. If every
    declared discriminator matches, they are the same meaning served twice, and
    ARCHITECTURE.md's equivalent-alternatives rule allows one to stand for both.
    """
    by_text: dict[str, list[ViewCandidate]] = {}
    for span in frame.of_role(role):
        for key in span.candidate_keys:
            match = next((item for item in survivors if item.key == key), None)
            if match is not None:
                by_text.setdefault(span.text, []).append(match)

    ambiguous = False
    notes: list[str] = []
    dropped: set[str] = set()
    for matched in by_text.values():
        if len(matched) < 2:
            continue
        profiles = {_discriminators(item) for item in matched}
        if len(profiles) > 1:
            ambiguous = True
            continue
        notes.append(REASON_EQUIVALENT_BINDING_COLLAPSED)
        keep = min(matched, key=lambda item: item.key)
        dropped.update(item.key for item in matched if item.key != keep.key)
    kept = [item for item in survivors if item.key not in dropped]
    return ambiguous, kept, notes


def _relationship_options(
    frame: RequirementFrame,
    target: ViewCandidate,
    source: ViewSource,
    metrics: RequirementMetrics,
) -> list[tuple[ViewCandidate, ViewCandidate | None, str]]:
    """Relation candidates whose direction the Registry fixes, not the model."""
    results: list[tuple[ViewCandidate, ViewCandidate | None, str]] = []
    anchors = [
        source.get(key)
        for span in frame.of_role(ROLE_ENTITY)
        for key in span.candidate_keys
    ]
    keyed = [
        key
        for span in frame.of_role(ROLE_RELATIONSHIP)
        for key in span.candidate_keys
    ]
    for relation_key in keyed:
        predicate = source.get(relation_key)
        if predicate is None:
            continue
        metrics.raw += 1
        if predicate.dataset_keys and target.key not in predicate.dataset_keys:
            metrics.prune_by_axis[AXIS_FAMILY] = (
                metrics.prune_by_axis.get(AXIS_FAMILY, 0) + 1
            )
            continue
        if not predicate.declares(AXIS_DOMAIN_RANGE):
            metrics.prune_by_axis[REASON_PRUNE_AXIS_UNAVAILABLE] = (
                metrics.prune_by_axis.get(REASON_PRUNE_AXIS_UNAVAILABLE, 0) + 1
            )
            results.append((predicate, next(iter(anchors), None), ""))
            continue
        anchor = next(
            (
                item
                for item in anchors
                if item is not None
                and item.entity_class in (predicate.object_class, predicate.subject_class)
            ),
            None,
        )
        if anchor is None or anchor.entity_class == predicate.object_class:
            direction = "subject_is_target"
        else:
            direction = "object_is_target"
        results.append((predicate, anchor, direction))
    return results


def _constraints(target: ViewCandidate) -> tuple[str, ...]:
    """Coverage and freshness, carried rather than used to delete a meaning."""
    notes: list[str] = []
    coverage = target.coverage or {}
    observed = coverage.get("observed_universe") or {}
    if observed:
        seen = observed.get("observed_products")
        universe = observed.get("universe_products")
        if seen is not None and universe is not None and seen != universe:
            notes.append("universe_observed_not_full")
        else:
            notes.append("universe_declared_full")
    else:
        notes.append("universe_not_declared")
    status = (target.freshness or {}).get("as_of_status")
    notes.append(f"as_of_status_{status}" if status else "as_of_status_not_declared")
    # No Execution Registry row provenance exists yet, so readiness is blocked
    # for every option. Recording it here keeps it out of semantic status.
    notes.append(REASON_PROVENANCE_UNAVAILABLE)
    return tuple(notes)


def _canonicalize(
    question: str,
    frame: RequirementFrame,
    ordering_field: ViewCandidate | None,
    aggregation_field: ViewCandidate | None,
    condition_pairs: Sequence[tuple[ViewCandidate, Span, Span]],
) -> tuple[str, tuple[str, ...], str, int, str, tuple[Condition, ...]]:
    """Run the four production canonicalisers over this option's own spans."""
    failures: list[str] = []
    conditions: list[Condition] = []
    for candidate, comparison_span, value_span in condition_pairs:
        result = canonicalize_comparison(
            question,
            comparison_span.text,
            value_span.text if value_span else "",
            _metadata(candidate),
        )
        if result.ok and result.value is not None:
            conditions.append(
                Condition(
                    field_key=candidate.key,
                    operator=result.operator,
                    value=str(result.value.number),
                    comparison_span=comparison_span.text,
                    value_span=value_span.text if value_span else "",
                )
            )
        else:
            failures.append(
                result.failure.code if result.failure else "comparison_incomplete"
            )

    direction = ""
    order_spans = frame.of_role(ROLE_ORDER_DIRECTION)
    if order_spans and ordering_field is not None:
        result = canonicalize_ordering(
            question, order_spans[0].text, _metadata(ordering_field)
        )
        if result.ok:
            direction = result.direction
        else:
            failures.append(result.failure.code if result.failure else "ordering_refused")
    elif order_spans:
        failures.append("ordering_field_unresolved")

    limit = 0
    limit_spans = frame.of_role(ROLE_LIMIT)
    if limit_spans:
        result = canonicalize_limit(question, limit_spans[0].text)
        if result.ok:
            limit = result.limit
        else:
            failures.append(result.failure.code if result.failure else "limit_refused")

    function = ""
    function_spans = frame.of_role(ROLE_AGGREGATION_FUNCTION)
    if function_spans and aggregation_field is not None:
        result = canonicalize_aggregation(
            question, function_spans[0].text, _metadata(aggregation_field)
        )
        if result.ok:
            function = result.function
        else:
            failures.append(
                result.failure.code if result.failure else "aggregation_refused"
            )
    elif function_spans and frame.kind == REQUIREMENT_KIND_COUNT:
        function = "count"

    status = CANONICALIZATION_READY
    needed = KIND_CANONICALIZERS.get(frame.kind, ())
    if any(item not in AVAILABLE_CANONICALIZERS for item in needed):
        status = CANONICALIZATION_UNAVAILABLE
        failures.append(REASON_CANONICALIZER_UNAVAILABLE)
    elif failures:
        status = CANONICALIZATION_REFUSED
    return status, tuple(failures), direction, limit, function, tuple(conditions)


def _options_for_frame(
    question: str,
    frame: RequirementFrame,
    targets: Sequence[str],
    missing: Sequence[str],
    source: ViewSource,
    policy: OptionGenerationPolicy,
    producer_id: str,
) -> tuple[list[RequirementOption], RequirementMetrics]:
    metrics = RequirementMetrics(
        requirement_id=frame.requirement_id, kind=frame.kind, raw=0, pruned=0,
        deduplicated=0,
    )
    options: list[RequirementOption] = []
    unresolved_spans = frame.of_role(ROLE_UNRESOLVED_ANCHOR)
    modifier_spans = frame.of_role(ROLE_UNRESOLVED_MODIFIER)
    reuse_of = producer_id if frame.of_role(ROLE_NESTED_REUSE) else ""

    if not targets:
        options.append(
            _unresolved_option(frame, tuple(missing) or (REASON_MISSING_TARGET,), reuse_of)
        )
        metrics.raw += 1
        metrics.pruned = 1
        metrics.deduplicated = 1
        return options, metrics

    for target_key in targets:
        target = source.get(target_key)
        if target is None:
            continue
        order_operation = OPERATION_ORDER if frame.of_role(ROLE_ORDER_DIRECTION) else ""
        aggregate_operation = (
            OPERATION_AGGREGATE if frame.of_role(ROLE_AGGREGATION_FUNCTION) else ""
        )
        outputs, output_reasons = _field_options(
            frame, ROLE_FIELD, target, source, "", metrics
        )
        conditions_fields, condition_reasons = _field_options(
            frame, ROLE_CONDITION_FIELD, target, source, OPERATION_FILTER, metrics
        )
        relationships = _relationship_options(frame, target, source, metrics)

        output_ambiguous, outputs, output_notes = _homonym_conflict(
            frame, ROLE_FIELD, outputs
        )
        condition_ambiguous, conditions_fields, condition_notes = _homonym_conflict(
            frame, ROLE_CONDITION_FIELD, conditions_fields
        )
        ambiguous = output_ambiguous or condition_ambiguous
        equivalence_notes = [*output_notes, *condition_notes]

        condition_pairs: list[tuple[ViewCandidate, Span, Span]] = []
        comparison_spans = frame.of_role(ROLE_COMPARISON_OPERATOR)
        value_spans = frame.of_role(ROLE_CONDITION_VALUE)
        for index, candidate in enumerate(conditions_fields):
            comparison = (
                comparison_spans[index]
                if index < len(comparison_spans)
                else _first(comparison_spans)
            )
            value = (
                value_spans[index] if index < len(value_spans) else _first(value_spans)
            )
            if comparison is not None:
                condition_pairs.append((candidate, comparison, value))

        metric_choices: list[ViewCandidate | None] = list(outputs) or [None]
        for metric in metric_choices:
            ordering_field = (
                metric
                if metric is not None
                and order_operation
                and order_operation
                in {fixture_operation_code(x) for x in metric.allowed_operations}
                else None
            )
            aggregation_field = (
                metric
                if metric is not None
                and aggregate_operation
                and aggregate_operation
                in {fixture_operation_code(x) for x in metric.allowed_operations}
                else None
            )
            (
                canonical_status,
                failures,
                direction,
                limit,
                function,
                canonical_conditions,
            ) = _canonicalize(
                question, frame, ordering_field, aggregation_field, condition_pairs
            )
            relationship = relationships[0] if relationships else None
            blocking: list[str] = []
            semantic = STATUS_MAPPED
            if unresolved_spans:
                semantic = STATUS_UNRESOLVED
                blocking.append(REASON_UNRESOLVED_ANCHOR)
            if metric is None and frame.of_role(ROLE_FIELD):
                semantic = STATUS_UNRESOLVED
                blocking.append(REASON_FIELD_PRUNED_FROM_TARGET)
            if modifier_spans:
                # The meaning stayed on allowed references, but a word the
                # question wrote is still unaccounted for and could change what
                # the metric means. That blocks execution without pretending the
                # mapping failed.
                blocking.append(REASON_UNACCOUNTED_MODIFIER)
            if ambiguous:
                semantic = STATUS_AMBIGUOUS
                blocking.append(REASON_HOMONYM_NO_DISCRIMINATOR)
            if output_reasons or condition_reasons:
                blocking.extend(dict.fromkeys([*output_reasons, *condition_reasons]))
            if len(
                option_operands(frame, policy)
            ) == policy.comparison_operands and not _operands_compatible(metric):
                blocking.append(REASON_OPERAND_INCOMPATIBLE)
            blocking.extend(equivalence_notes)
            if canonical_status == CANONICALIZATION_REFUSED:
                blocking.append(REASON_CANONICALIZATION_REFUSED)
            if canonical_status == CANONICALIZATION_UNAVAILABLE:
                blocking.append(REASON_CANONICALIZER_UNAVAILABLE)

            option = RequirementOption(
                requirement_id=frame.requirement_id,
                kind=frame.kind,
                semantic_status=semantic,
                canonicalization_status=canonical_status,
                execution_readiness=READINESS_BLOCKED,
                target_keys=(target.key,),
                output_field_keys=(metric.key,) if metric is not None else (),
                conditions=canonical_conditions,
                ordering_field_key=ordering_field.key if ordering_field else "",
                ordering_direction=direction,
                limit=limit,
                aggregation_field_key=(
                    aggregation_field.key if aggregation_field else ""
                ),
                aggregation_function=function,
                relationship_key=relationship[0].key if relationship else "",
                relationship_anchor_key=(
                    relationship[1].key if relationship and relationship[1] else ""
                ),
                relationship_direction=relationship[2] if relationship else "",
                result_reuse_of=reuse_of,
                comparison_operand_keys=tuple(
                    sorted(
                        {
                            key
                            for span in frame.of_role(ROLE_ENTITY)
                            for key in span.candidate_keys
                        }
                    )
                )[: policy.comparison_operands],
                canonicalization_failures=failures,
                execution_constraints=_constraints(target),
                blocking_reasons=tuple(dict.fromkeys(blocking)),
                equivalence_key="",
                span_texts=tuple(span.text for span in frame.spans),
            )
            options.append(_with_equivalence_key(option))

    metrics.pruned = len(options)
    deduplicated: dict[str, RequirementOption] = {}
    for option in options:
        deduplicated.setdefault(option.equivalence_key, option)
    ordered = sorted(deduplicated.values(), key=lambda item: item.equivalence_key)
    metrics.deduplicated = len(ordered)
    if len(ordered) > policy.max_options_per_requirement:
        metrics.lossy_truncated = len(ordered) - policy.max_options_per_requirement
        ordered = ordered[: policy.max_options_per_requirement]
    return ordered, metrics


def option_operands(
    frame: RequirementFrame, policy: OptionGenerationPolicy
) -> tuple[str, ...]:
    """The entities a bounded comparison would be between."""
    return tuple(
        sorted({key for span in frame.of_role(ROLE_ENTITY) for key in span.candidate_keys})
    )[: policy.comparison_operands]


def _operands_compatible(metric: ViewCandidate | None) -> bool:
    """Two operands share one scale only when the metric declares one."""
    if metric is None:
        return False
    return bool(metric.declares(AXIS_UNIT) and metric.unit)


def _unresolved_option(
    frame: RequirementFrame, reasons: Sequence[str], reuse_of: str
) -> RequirementOption:
    option = RequirementOption(
        requirement_id=frame.requirement_id,
        kind=frame.kind,
        semantic_status=STATUS_UNRESOLVED,
        canonicalization_status=CANONICALIZATION_UNAVAILABLE,
        execution_readiness=READINESS_NOT_EVALUATED,
        target_keys=(),
        output_field_keys=(),
        conditions=(),
        ordering_field_key="",
        ordering_direction="",
        limit=0,
        aggregation_field_key="",
        aggregation_function="",
        relationship_key="",
        relationship_anchor_key="",
        relationship_direction="",
        result_reuse_of=reuse_of,
        comparison_operand_keys=(),
        canonicalization_failures=(),
        execution_constraints=(),
        blocking_reasons=tuple(dict.fromkeys(reasons)),
        equivalence_key="",
        span_texts=tuple(span.text for span in frame.spans),
    )
    return _with_equivalence_key(option)


def _with_equivalence_key(option: RequirementOption) -> RequirementOption:
    """A fingerprint of meaning: no reference, no salt, no candidate order."""
    payload = {
        "kind": option.kind,
        "semantic_status": option.semantic_status,
        "targets": sorted(option.target_keys),
        "outputs": sorted(option.output_field_keys),
        "conditions": sorted(
            (item.field_key, item.operator, item.value) for item in option.conditions
        ),
        "ordering": (option.ordering_field_key, option.ordering_direction),
        "limit": option.limit,
        "aggregation": (option.aggregation_field_key, option.aggregation_function),
        "relationship": (
            option.relationship_key,
            option.relationship_anchor_key,
            option.relationship_direction,
        ),
        "reuse": bool(option.result_reuse_of),
        "comparison": sorted(option.comparison_operand_keys),
    }
    return RequirementOption(**{**option.__dict__, "equivalence_key": _digest(payload)})


def _plan_status(options: Sequence[RequirementOption]) -> tuple[str, tuple[str, ...]]:
    reasons: list[str] = []
    for option in options:
        reasons.extend(option.blocking_reasons)
    if any(REASON_UNACCOUNTED_MODIFIER in item.blocking_reasons for item in options):
        return "blocked_validation", tuple(dict.fromkeys(reasons))
    if any(item.semantic_status == STATUS_AMBIGUOUS for item in options):
        return "blocked_materially_ambiguous", tuple(dict.fromkeys(reasons))
    if any(item.semantic_status == STATUS_UNRESOLVED for item in options):
        return "blocked_unresolved", tuple(dict.fromkeys(reasons))
    if any(
        item.canonicalization_status != CANONICALIZATION_READY for item in options
    ):
        return "blocked_validation", tuple(dict.fromkeys(reasons))
    return "candidate_selectable", tuple(dict.fromkeys(reasons))


def generate(
    question: str,
    ledger: SpanLedger,
    source: ViewSource,
    policy: OptionGenerationPolicy | None = None,
    ref_minter: object | None = None,
) -> PlanOptionSet:
    """Build every plan the Runtime View can prove, and refuse the rest."""
    policy = policy or OptionGenerationPolicy()
    reasons: list[str] = []
    if not ledger.frames:
        return PlanOptionSet(
            generation_status=GENERATION_NO_CANDIDATE,
            generation_reasons=(REASON_MISSING_TARGET,),
            requirement_metrics=(),
            requirement_options={},
            plan_options=(),
            partial_plans_considered=0,
            plan_options_before_cap=0,
            lossy_discards=0,
            policy=policy,
        )
    if len(ledger.frames) > policy.max_requirements:
        return PlanOptionSet(
            generation_status=GENERATION_TRUNCATED,
            generation_reasons=(REASON_STRUCTURE_LIMIT,),
            requirement_metrics=(),
            requirement_options={},
            plan_options=(),
            partial_plans_considered=0,
            plan_options_before_cap=0,
            lossy_discards=0,
            policy=policy,
        )

    by_requirement: dict[str, tuple[RequirementOption, ...]] = {}
    metrics: list[RequirementMetrics] = []
    inherited: tuple[str, ...] = ()
    lossy = 0
    previous_id = ""
    for frame in ledger.frames:
        targets, missing = _targets_for(frame, inherited, source)
        if targets:
            inherited = targets
        options, frame_metrics = _options_for_frame(
            question, frame, targets, missing, source, policy, previous_id
        )
        lossy += frame_metrics.lossy_truncated
        by_requirement[frame.requirement_id] = tuple(options)
        metrics.append(frame_metrics)
        previous_id = frame.requirement_id

    partial = 0
    combinations: list[tuple[RequirementOption, ...]] = []
    for combination in itertools.product(*list(by_requirement.values())):
        partial += 1
        if partial > policy.join_beam * max(1, len(by_requirement)):
            lossy += 1
            break
        combinations.append(combination)

    seen: dict[str, PlanOption] = {}
    for combination in combinations:
        key = _digest(sorted(item.equivalence_key for item in combination))
        if key in seen:
            continue
        status, blocking = _plan_status(combination)
        constraints = tuple(
            dict.fromkeys(
                note for item in combination for note in item.execution_constraints
            )
        )
        seen[key] = PlanOption(
            plan_ref="",
            requirement_options=combination,
            plan_status=status,
            equivalence_key=key,
            execution_constraints=constraints,
            blocking_reasons=blocking,
        )

    plans = sorted(seen.values(), key=lambda item: item.equivalence_key)
    before_cap = len(plans)
    if before_cap > policy.max_plan_options:
        lossy += before_cap - policy.max_plan_options
        plans = plans[: policy.max_plan_options]

    if lossy:
        status = GENERATION_TRUNCATED
        reasons.append(REASON_TRUNCATED)
        plans = tuple(
            PlanOption(
                plan_ref=item.plan_ref,
                requirement_options=item.requirement_options,
                plan_status="blocked_truncated",
                equivalence_key=item.equivalence_key,
                execution_constraints=item.execution_constraints,
                blocking_reasons=(*item.blocking_reasons, REASON_TRUNCATED),
            )
            for item in plans
        )
    else:
        selectable = [item for item in plans if item.selectable]
        if not selectable:
            if any(
                item.plan_status == "blocked_materially_ambiguous" for item in plans
            ):
                status = GENERATION_MATERIALLY_AMBIGUOUS
            else:
                status = GENERATION_NO_CANDIDATE
            reasons.extend(
                dict.fromkeys(
                    reason for item in plans for reason in item.blocking_reasons
                )
            )
        elif len(selectable) > 1:
            status = GENERATION_CHOICE_REQUIRED
        else:
            status = GENERATION_COMPLETE
        plans = tuple(plans)

    if ref_minter is not None:
        plans = tuple(
            PlanOption(
                plan_ref=ref_minter(index),  # type: ignore[operator]
                requirement_options=item.requirement_options,
                plan_status=item.plan_status,
                equivalence_key=item.equivalence_key,
                execution_constraints=item.execution_constraints,
                blocking_reasons=item.blocking_reasons,
            )
            for index, item in enumerate(plans)
        )

    return PlanOptionSet(
        generation_status=status,
        generation_reasons=tuple(dict.fromkeys(reasons)),
        requirement_metrics=tuple(metrics),
        requirement_options=by_requirement,
        plan_options=tuple(plans),
        partial_plans_considered=partial,
        plan_options_before_cap=before_cap,
        lossy_discards=lossy,
        policy=policy,
    )
