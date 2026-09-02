"""Server validation: the point where a wrong product family stops being silent.

The model chose references; this decides whether that choice is executable.
Three rules carry most of the weight.

The first is family binding. A field may serve a requirement only if the
Registry puts it in one of the target datasets that requirement actually
selected — not merely in the right family somewhere. When it does not, the
requirement is refused and left unresolved: the server does not look for a
same-named measure in the right family and quietly swap it in, because a
question naming a measure the target does not have has no answer, and
manufacturing one would be indistinguishable from answering.

The second is relation direction. The model submits a relationship and an
anchor; the server picks the traversal from the predicate's domain and range and
the anchor's verified type, and considers only the Registry's declared inverse
as an alternative. Two relations sharing a domain and range but not inverses — a
direct holding and a look-through exposure — are different meanings, and one is
never substituted for the other.

The third is that an operation nobody can canonicalise cannot be executed.
Ordering, limits, comparisons, aggregations and groupings must be derived
deterministically from the question span before they can run. Four of those
derivations now exist and are applied here: the span is read, the Registry is
asked whether the field permits the operation, and a slot that cannot be turned
into an execution value refuses rather than guessing a descending default or an
implicit top ten. Grouping, whole comparison requirements and explanations still
have no canonicaliser and are still refused by name. The submitted spans and
references survive into the plan either way, so nothing is lost.

A requirement that refused anything hands out no execution values. The
canonicalisation is kept on the plan as a record, failures included, but
``execution_values`` releases it only when the requirement passed, so a compiler
cannot reach past a refusal to the values produced before it.

Two distinctions run through the result. The model's ``submitted_status`` and
the server's ``server_decision`` are kept apart, because a requirement the model
called mapped and the server refused has to end its accounting as unresolved —
otherwise a refusal would read as an answer. And ``semantic_valid`` is not
``execution_ready``: this layer validates meaning against the Semantic Registry
and knows nothing about physical bindings or coverage, so it never claims a
requirement can actually run.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .canonicalize import (
    FieldMetadata,
    RequirementCanonicalization,
    canonicalize_requirement,
    field_metadata,
)
from .contract import (
    AVAILABLE_CANONICALIZERS,
    CANONICALIZER_COMPARISON,
    CANONICALIZER_LIMIT,
    CANONICALIZER_ORDERING,
    CONTRACT_STATUS,
    DECISION_AMBIGUOUS,
    DECISION_MAPPED,
    DECISION_UNRESOLVED,
    KIND_CANONICALIZERS,
    KINDS_REQUIRING_OUTPUT,
    REQUIREMENT_KIND_AGGREGATION,
    REQUIREMENT_KIND_RANKING,
    STATUS_AMBIGUOUS,
    STATUS_MAPPED,
)
from .query import SubmittedQuery, SubmittedRequirement
from .refs import KIND_DATASET, KIND_FIELD, KIND_PREDICATE, RefError
from .registry_facts import RegistryFacts
from .spans import CODE_SPAN_ALIGNMENT_FAILED, aligned
from .view import SCOPE_UNPROVEN, RuntimeView, inverse_partners

# Provisional internal reason codes. No shared contract has been approved for
# them; ``CONTRACT_STATUS`` travels with every result to say so.
CODE_UNKNOWN_REF = "unknown_ref"
CODE_REF_KIND_MISMATCH = "ref_kind_mismatch"
CODE_MISSING_TARGET = "missing_target_dataset"
CODE_CROSS_FAMILY_FIELD = "cross_family_field"
CODE_CROSS_FAMILY_PREDICATE = "cross_family_predicate"
CODE_FIELD_SCOPE_UNPROVEN = "field_scope_unproven"
CODE_GRAIN_MISMATCH = "field_grain_mismatch"
CODE_REQUIREMENT_UNRESOLVED = "requirement_unresolved"
CODE_REQUIREMENT_AMBIGUOUS = "requirement_ambiguous"
CODE_REQUIREMENT_INCOMPLETE = "requirement_incomplete"
CODE_ENTITY_UNRESOLVED = "entity_unresolved"
CODE_DIRECTION_UNDECIDABLE = "relation_direction_undecidable"
CODE_RELATION_TARGET_MISMATCH = "relation_target_mismatch"
CODE_CANONICALIZER_UNAVAILABLE = "canonicalizer_unavailable"
CODE_UNACCOUNTED_SPAN = "unaccounted_explicit_span"
# CODE_SPAN_ALIGNMENT_FAILED is not defined here. It belongs to spans.py, which
# owns alignment, and a second copy of the string would be a second contract.
CODE_CANONICALIZATION_REFUSED = "canonicalization_refused"
CODE_MISSING_SOURCE_SPAN = "missing_source_span"
CODE_EMPTY_REQUIREMENT = "empty_requirement"

# A refusal that means "two meanings were possible" ends as ambiguous; every
# other refusal ends as unresolved. The distinction is the one
# QUESTION_STRUCTURE.md section 5 draws, applied to the server's own verdict.
AMBIGUOUS_DECISION_CODES = frozenset({CODE_DIRECTION_UNDECIDABLE})

TRAVERSAL_FROM_ANCHOR = "anchor_is_subject"

EXECUTION_READINESS_NOT_EVALUATED = "not_evaluated_by_semantic_validation"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    requirement_id: str
    detail: str
    refs: tuple[str, ...] = ()
    substitute_offered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "requirement_id": self.requirement_id,
            "detail": self.detail,
            "refs": list(self.refs),
            "substitute_offered": self.substitute_offered,
        }


@dataclass(frozen=True)
class FieldBinding:
    """One field, bound to one target the requirement actually selected."""

    target_dataset_id: str
    field_id: str
    role: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_dataset_id": self.target_dataset_id,
            "field_id": self.field_id,
            "role": self.role,
        }


@dataclass(frozen=True)
class RelationBinding:
    predicate_id: str
    submitted_predicate_id: str
    subject_class_id: str
    object_class_id: str
    anchor_entity_key: str
    anchor_class_id: str
    traversal: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicate_id": self.predicate_id,
            "submitted_predicate_id": self.submitted_predicate_id,
            "subject_class_id": self.subject_class_id,
            "object_class_id": self.object_class_id,
            "anchor_entity_key": self.anchor_entity_key,
            "anchor_class_id": self.anchor_class_id,
            "traversal": self.traversal,
        }


@dataclass(frozen=True)
class PreservedSubmission:
    """Exactly what the model submitted, kept for whoever canonicalises it later."""

    source_span: str
    condition_spans: tuple[tuple[str, str, str], ...]
    ordering_span: tuple[str, str] | None
    limit_span: str
    aggregation_span: tuple[str, str] | None
    grouping_field_ids: tuple[str, ...]
    submitted_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_span": self.source_span,
            "condition_spans": [
                {"field_id": field_id, "comparison_span": comparison, "value_span": value}
                for field_id, comparison, value in self.condition_spans
            ],
            "ordering_span": (
                {"field_id": self.ordering_span[0], "direction_span": self.ordering_span[1]}
                if self.ordering_span
                else None
            ),
            "limit_span": self.limit_span,
            "aggregation_span": (
                {
                    "field_id": self.aggregation_span[0],
                    "function_span": self.aggregation_span[1],
                }
                if self.aggregation_span
                else None
            ),
            "grouping_field_ids": list(self.grouping_field_ids),
            "submitted_refs": list(self.submitted_refs),
        }


@dataclass(frozen=True)
class CanonicalRequirement:
    """One requirement, as the server understood it.

    ``submitted_status`` is the model's own accounting and is never overwritten;
    ``server_decision`` is this layer's verdict. They disagree exactly when the
    model claimed a mapping the server refused, and that disagreement is the
    interesting record, so both are kept.
    """

    requirement_id: str
    kind: str
    submitted_status: str
    server_decision: str
    semantic_valid: bool
    target_dataset_ids: tuple[str, ...]
    field_bindings: tuple[FieldBinding, ...]
    relation: RelationBinding | None
    preserved: PreservedSubmission
    canonical: RequirementCanonicalization | None
    blocking_codes: tuple[str, ...]

    @property
    def execution_values(self) -> RequirementCanonicalization | None:
        """The values a compiler may execute, and only when nothing was refused.

        ``canonical`` is the record and keeps its failures for whoever reads the
        plan. This is the gate: a requirement that did not pass validation hands
        out no execution values at all, so a caller cannot reach past a refusal
        by looking at the values it produced before the refusal.
        """
        return self.canonical if self.semantic_valid else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "kind": self.kind,
            "submitted_status": self.submitted_status,
            "server_decision": self.server_decision,
            "semantic_valid": self.semantic_valid,
            "target_dataset_ids": list(self.target_dataset_ids),
            "field_bindings": [binding.to_dict() for binding in self.field_bindings],
            "relation": self.relation.to_dict() if self.relation else None,
            "preserved": self.preserved.to_dict(),
            "canonical": _canonical_dict(self.canonical),
            "execution_values_released": self.execution_values is not None,
            "blocking_codes": list(self.blocking_codes),
        }


def _canonical_dict(canonical: RequirementCanonicalization | None) -> dict[str, Any] | None:
    """The derived execution values, and every slot that refused to produce one."""
    if canonical is None:
        return None
    return {
        "conditions": [
            {
                "operator": item.operator,
                "value": item.value.to_dict() if item.value else None,
            }
            for item in canonical.conditions
        ],
        "ordering_direction": canonical.ordering.direction if canonical.ordering else "",
        "limit": canonical.limit.limit if canonical.limit and canonical.limit.ok else None,
        "aggregation_function": (
            canonical.aggregation.function if canonical.aggregation else ""
        ),
        "failures": [failure.to_dict() for failure in canonical.failures],
    }


@dataclass(frozen=True)
class CanonicalPlan:
    requirements: tuple[CanonicalRequirement, ...]

    @property
    def semantic_valid(self) -> bool:
        return bool(self.requirements) and all(
            item.semantic_valid for item in self.requirements
        )

    def to_dict(self) -> dict[str, Any]:
        """The server's own plan. Not safe to hand to the model — see model_response."""
        return {
            "contract_status": CONTRACT_STATUS,
            "audience": "server_internal",
            "requirements": [item.to_dict() for item in self.requirements],
        }


@dataclass
class ValidationResult:
    plan: CanonicalPlan | None
    issues: tuple[ValidationIssue, ...] = ()
    unresolved_requirement_ids: tuple[str, ...] = ()

    @property
    def semantic_valid(self) -> bool:
        """The meanings check out. It says nothing about whether they can run."""
        return self.plan is not None and self.plan.semantic_valid and not self.issues

    @property
    def execution_readiness(self) -> str:
        """Not a verdict this layer is entitled to give.

        Whether a plan can run depends on resolving each candidate to exactly
        one Execution Registry binding and checking its operations, coverage and
        as-of. That happens after this layer, so the honest answer here is that
        the question has not been asked yet — never a boolean that reads as yes.
        """
        return EXECUTION_READINESS_NOT_EVALUATED

    def to_dict(self) -> dict[str, Any]:
        """The server's own record. Not safe to hand to the model."""
        return {
            "contract_status": CONTRACT_STATUS,
            "audience": "server_internal",
            "semantic_valid": self.semantic_valid,
            "execution_readiness": self.execution_readiness,
            "execution_readiness_basis": (
                "operation, coverage and as-of are resolved against the Execution "
                "Registry after this layer; nothing here asserts a plan can run"
            ),
            "plan": self.plan.to_dict() if self.plan else None,
            "issues": [issue.to_dict() for issue in self.issues],
            "unresolved_requirement_ids": list(self.unresolved_requirement_ids),
        }


def validate(
    facts: RegistryFacts,
    view: RuntimeView,
    submission: SubmittedQuery,
) -> ValidationResult:
    """Refuse anything that would need a guess, and canonicalise the rest."""
    issues: list[ValidationIssue] = []
    unresolved: list[str] = []
    canonical: list[CanonicalRequirement] = []

    issues.extend(
        ValidationIssue(
            code=CODE_UNACCOUNTED_SPAN,
            requirement_id="",
            detail=(
                "the model reported an explicit span it did not account for; an incomplete "
                f"accounting is not executed (span: {span!r})"
            ),
        )
        for span in submission.unaccounted_spans
    )

    for requirement in submission.requirements:
        built, requirement_issues = _validate_requirement(facts, view, requirement)
        issues.extend(requirement_issues)
        canonical.append(built)
        if built.server_decision != DECISION_MAPPED:
            unresolved.append(requirement.requirement_id)

    plan = CanonicalPlan(
        requirements=tuple(sorted(canonical, key=lambda item: item.requirement_id))
    )
    return ValidationResult(
        plan=plan if canonical else None,
        issues=tuple(issues),
        unresolved_requirement_ids=tuple(sorted(unresolved)),
    )


def _resolve(view: RuntimeView, ref: str, expected_kind: str) -> tuple[str | None, str | None]:
    """``(semantic_id, error_code)`` — an unknown and a foreign ref are the same."""
    try:
        _kind, key = view.minter.resolve(ref, expected_kind=expected_kind)
    except RefError as error:
        return None, error.code
    return key, None


def _preserved(view: RuntimeView, requirement: SubmittedRequirement) -> PreservedSubmission:
    """Keep the model's spans and references even when nothing can execute."""

    def field_id(ref: str) -> str:
        semantic_id, _code = _resolve(view, ref, KIND_FIELD)
        return semantic_id or ref

    refs = [
        *requirement.target_dataset_refs,
        *(ref for ref, _role in requirement.referenced_field_refs),
    ]
    if requirement.relationship is not None:
        refs += [
            requirement.relationship.predicate_ref,
            requirement.relationship.anchor_entity_ref,
        ]
    return PreservedSubmission(
        source_span=requirement.source_span,
        condition_spans=tuple(
            (field_id(condition.field_ref), condition.comparison_span, condition.value_span)
            for condition in requirement.conditions
        ),
        ordering_span=(
            (field_id(requirement.ordering.field_ref), requirement.ordering.direction_span)
            if requirement.ordering
            else None
        ),
        limit_span=requirement.limit_span,
        aggregation_span=(
            (field_id(requirement.aggregation.field_ref), requirement.aggregation.function_span)
            if requirement.aggregation
            else None
        ),
        grouping_field_ids=tuple(field_id(ref) for ref in requirement.grouping_field_refs),
        submitted_refs=tuple(refs),
    )


def _field_metadata_lookup(facts: RegistryFacts, view: RuntimeView):
    """Answer a submitted field reference with what the Registry says about it.

    The canonicaliser needs a declared unit and a declared set of permitted
    operations, and it must get them from the Registry rather than from the
    submission. A reference that does not resolve gets ``None``, which the
    canonicaliser turns into a refusal rather than a default.
    """

    def lookup(ref: str) -> FieldMetadata | None:
        semantic_id, _code = _resolve(view, ref, KIND_FIELD)
        if semantic_id is None or not facts.has(semantic_id):
            return None
        return field_metadata(facts.term(semantic_id))

    return lookup


def _missing_canonicalizers(requirement: SubmittedRequirement) -> tuple[str, ...]:
    """Which deterministic derivations this requirement needs and nobody has."""
    needed = set(KIND_CANONICALIZERS.get(requirement.kind, ()))
    if requirement.conditions:
        needed.add(CANONICALIZER_COMPARISON)
    if requirement.ordering is not None:
        needed.add(CANONICALIZER_ORDERING)
    if requirement.limit_span:
        needed.add(CANONICALIZER_LIMIT)
    return tuple(sorted(needed - AVAILABLE_CANONICALIZERS))


def _check_spans(
    view: RuntimeView, requirement: SubmittedRequirement
) -> list[ValidationIssue]:
    """Every span the model wrote has to be a quotation, not a composition."""
    issues: list[ValidationIssue] = []
    named: list[tuple[str, str]] = [("source_span", requirement.source_span)]
    for condition in requirement.conditions:
        named.append(("comparison_span", condition.comparison_span))
        named.append(("value_span", condition.value_span))
    if requirement.ordering is not None:
        named.append(("direction_span", requirement.ordering.direction_span))
    named.append(("limit_span", requirement.limit_span))
    if requirement.aggregation is not None:
        named.append(("function_span", requirement.aggregation.function_span))

    if not requirement.source_span.strip():
        issues.append(
            ValidationIssue(
                code=CODE_MISSING_SOURCE_SPAN,
                requirement_id=requirement.requirement_id,
                detail=(
                    "an explicit requirement must quote the part of the question it came "
                    "from; without it the accounting cannot be checked"
                ),
            )
        )
    issues.extend(
        ValidationIssue(
            code=CODE_SPAN_ALIGNMENT_FAILED,
            requirement_id=requirement.requirement_id,
            detail=(
                f"the submitted {name} does not appear in the question, exactly or after "
                "the approved normalisation"
            ),
        )
        for name, span in named
        if span.strip() and not aligned(view.question, span)
    )
    return issues


def _check_completeness(
    requirement: SubmittedRequirement, targets: Sequence[str]
) -> list[ValidationIssue]:
    """A requirement has to say what it is about and what it wants."""
    issues: list[ValidationIssue] = []
    has_output = bool(
        requirement.field_refs or requirement.output_field_refs or requirement.relationship
    )
    if not targets:
        issues.append(
            ValidationIssue(
                code=CODE_MISSING_TARGET,
                requirement_id=requirement.requirement_id,
                detail="every requirement needs the population it applies to",
            )
        )
    if requirement.kind in KINDS_REQUIRING_OUTPUT and not has_output:
        issues.append(
            ValidationIssue(
                code=CODE_REQUIREMENT_INCOMPLETE,
                requirement_id=requirement.requirement_id,
                detail=(
                    "an attribute lookup has to name the field or the relationship output "
                    "it is asking for"
                ),
            )
        )
    if not targets and not has_output and not requirement.conditions:
        issues.append(
            ValidationIssue(
                code=CODE_EMPTY_REQUIREMENT,
                requirement_id=requirement.requirement_id,
                detail=(
                    "this requirement names nothing at all; an empty plan is never a valid "
                    "reading of a question"
                ),
            )
        )
    if requirement.kind == REQUIREMENT_KIND_AGGREGATION and (
        requirement.aggregation is None
        or not requirement.aggregation.field_ref
        or not requirement.aggregation.function_span
    ):
        issues.append(
            ValidationIssue(
                code=CODE_REQUIREMENT_INCOMPLETE,
                requirement_id=requirement.requirement_id,
                detail=(
                    "an aggregation has to name the field it aggregates and quote the "
                    "word that says which aggregation; neither is inferred"
                ),
            )
        )
    if requirement.kind == REQUIREMENT_KIND_RANKING and (
        requirement.ordering is None or not requirement.limit_span
    ):
        issues.append(
            ValidationIssue(
                code=CODE_REQUIREMENT_INCOMPLETE,
                requirement_id=requirement.requirement_id,
                detail=(
                    "a ranking needs an ordering and a limit taken from the question; no "
                    "default direction or size is invented"
                ),
            )
        )
    return issues


def _decision(submitted_status: str, blocking: Sequence[str]) -> str:
    """The server's verdict, which may disagree with what the model claimed."""
    if not blocking:
        return DECISION_MAPPED
    if submitted_status == STATUS_AMBIGUOUS or (set(blocking) & AMBIGUOUS_DECISION_CODES):
        return DECISION_AMBIGUOUS
    return DECISION_UNRESOLVED


def _validate_requirement(
    facts: RegistryFacts,
    view: RuntimeView,
    requirement: SubmittedRequirement,
) -> tuple[CanonicalRequirement, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    preserved = _preserved(view, requirement)

    if requirement.status != STATUS_MAPPED:
        issues.append(
            ValidationIssue(
                code=(
                    CODE_REQUIREMENT_AMBIGUOUS
                    if requirement.status == STATUS_AMBIGUOUS
                    else CODE_REQUIREMENT_UNRESOLVED
                ),
                requirement_id=requirement.requirement_id,
                detail=(
                    f"the model left this requirement {requirement.status}; it is preserved "
                    "and not executed"
                ),
            )
        )
        return _blocked(requirement, preserved, issues), issues

    issues.extend(_check_spans(view, requirement))
    targets, target_issues = _resolve_targets(view, requirement)
    issues.extend(target_issues)
    if not target_issues:
        issues.extend(_check_completeness(requirement, targets))

    bindings = _bind_fields(view, requirement, targets, issues)
    relation = _bind_relation(facts, view, requirement, targets, issues)

    issues.extend(
        ValidationIssue(
            code=CODE_CANONICALIZER_UNAVAILABLE,
            requirement_id=requirement.requirement_id,
            detail=(
                f"the server has no deterministic canonicaliser for {name}; the requirement "
                "is preserved and not executed"
            ),
        )
        for name in _missing_canonicalizers(requirement)
    )

    canonical = canonicalize_requirement(
        view.question, requirement, _field_metadata_lookup(facts, view)
    )
    issues.extend(
        ValidationIssue(
            code=CODE_CANONICALIZATION_REFUSED,
            requirement_id=requirement.requirement_id,
            detail=(
                f"{failure.slot} could not be turned into an execution value: "
                f"{failure.detail}"
            ),
        )
        for failure in canonical.failures
    )

    blocking = tuple(
        sorted(
            {
                issue.code
                for issue in issues
                if issue.requirement_id == requirement.requirement_id
            }
        )
    )
    return (
        CanonicalRequirement(
            requirement_id=requirement.requirement_id,
            kind=requirement.kind,
            submitted_status=requirement.status,
            server_decision=_decision(requirement.status, blocking),
            semantic_valid=not blocking,
            target_dataset_ids=tuple(sorted(set(targets))),
            field_bindings=tuple(
                sorted(
                    bindings,
                    key=lambda item: (item.target_dataset_id, item.field_id, item.role),
                )
            ),
            relation=relation,
            preserved=preserved,
            canonical=canonical,
            blocking_codes=blocking,
        ),
        issues,
    )


def _blocked(
    requirement: SubmittedRequirement,
    preserved: PreservedSubmission,
    issues: Sequence[ValidationIssue],
) -> CanonicalRequirement:
    codes = tuple(sorted({issue.code for issue in issues}))
    return CanonicalRequirement(
        requirement_id=requirement.requirement_id,
        kind=requirement.kind,
        submitted_status=requirement.status,
        server_decision=_decision(requirement.status, codes),
        semantic_valid=False,
        target_dataset_ids=(),
        field_bindings=(),
        relation=None,
        preserved=preserved,
        canonical=None,
        blocking_codes=codes,
    )


def _resolve_targets(
    view: RuntimeView, requirement: SubmittedRequirement
) -> tuple[list[str], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    targets: list[str] = []
    for ref in requirement.target_dataset_refs:
        semantic_id, code = _resolve(view, ref, KIND_DATASET)
        candidate = view.dataset(ref) if semantic_id else None
        if semantic_id is None or candidate is None:
            issues.append(
                ValidationIssue(
                    code=code or CODE_UNKNOWN_REF,
                    requirement_id=requirement.requirement_id,
                    detail="target dataset reference does not belong to this request",
                    refs=(ref,),
                )
            )
            continue
        targets.append(semantic_id)
    return targets, issues


def _bind_fields(
    view: RuntimeView,
    requirement: SubmittedRequirement,
    targets: Sequence[str],
    issues: list[ValidationIssue],
) -> list[FieldBinding]:
    """Bind each field to the targets this requirement actually selected."""
    bindings: list[FieldBinding] = []
    for ref, role in requirement.referenced_field_refs:
        semantic_id, code = _resolve(view, ref, KIND_FIELD)
        candidate = view.field(ref) if semantic_id else None
        if semantic_id is None or candidate is None:
            issues.append(
                ValidationIssue(
                    code=code or CODE_UNKNOWN_REF,
                    requirement_id=requirement.requirement_id,
                    detail="field reference does not belong to this request",
                    refs=(ref,),
                )
            )
            continue
        if candidate.dataset_scope == SCOPE_UNPROVEN:
            issues.append(
                ValidationIssue(
                    code=CODE_FIELD_SCOPE_UNPROVEN,
                    requirement_id=requirement.requirement_id,
                    detail=(
                        "the Registry does not state which product families this field "
                        "applies to, so it cannot be bound to a target and the requirement "
                        "stays unresolved"
                    ),
                    refs=(ref,),
                )
            )
            continue
        matched: list[str] = []
        grain_only_mismatch = False
        for target_id in targets:
            dataset = next(
                (item for item in view.datasets if item.semantic_id == target_id), None
            )
            if dataset is None or not set(candidate.families) & set(dataset.families):
                continue
            if not set(candidate.grains) & set(dataset.grains):
                grain_only_mismatch = True
                continue
            matched.append(target_id)
        if matched:
            bindings.extend(
                FieldBinding(target_dataset_id=target_id, field_id=semantic_id, role=role)
                for target_id in matched
            )
            continue
        issues.append(
            ValidationIssue(
                code=CODE_GRAIN_MISMATCH if grain_only_mismatch else CODE_CROSS_FAMILY_FIELD,
                requirement_id=requirement.requirement_id,
                detail=(
                    "this field is not part of any target this requirement selected; the "
                    "requirement stays unresolved and no same-named field of the target is "
                    "substituted"
                ),
                refs=(ref, *requirement.target_dataset_refs),
                substitute_offered=False,
            )
        )
    return bindings


def _bind_relation(
    facts: RegistryFacts,
    view: RuntimeView,
    requirement: SubmittedRequirement,
    targets: Sequence[str],
    issues: list[ValidationIssue],
) -> RelationBinding | None:
    relationship = requirement.relationship
    if relationship is None:
        return None

    semantic_id, code = _resolve(view, relationship.predicate_ref, KIND_PREDICATE)
    candidate = view.predicate(relationship.predicate_ref) if semantic_id else None
    if semantic_id is None or candidate is None:
        issues.append(
            ValidationIssue(
                code=code or CODE_UNKNOWN_REF,
                requirement_id=requirement.requirement_id,
                detail="predicate reference does not belong to this request",
                refs=(relationship.predicate_ref,),
            )
        )
        return None

    anchor = view.entity(relationship.anchor_entity_ref)
    if anchor is None:
        issues.append(
            ValidationIssue(
                code=CODE_UNKNOWN_REF,
                requirement_id=requirement.requirement_id,
                detail="anchor entity reference does not belong to this request",
                refs=(relationship.anchor_entity_ref,),
            )
        )
        return None
    if not anchor.resolved:
        issues.append(
            ValidationIssue(
                code=CODE_ENTITY_UNRESOLVED,
                requirement_id=requirement.requirement_id,
                detail=(
                    f"the anchor entity is {anchor.resolution_status}; entity resolution is "
                    "a separate layer and the relation is not executed on an unresolved "
                    "anchor"
                ),
                refs=(relationship.anchor_entity_ref,),
            )
        )
        return None

    fits = [
        option
        for option in _direction_options(facts, semantic_id)
        if facts.is_kind_of(anchor.entity_class_id, option["domain"])
    ]
    if len(fits) != 1:
        issues.append(
            ValidationIssue(
                code=CODE_DIRECTION_UNDECIDABLE,
                requirement_id=requirement.requirement_id,
                detail=(
                    "the traversal direction is not uniquely determined by the predicate's "
                    "domain/range and the anchor entity type"
                ),
                refs=(relationship.predicate_ref, relationship.anchor_entity_ref),
            )
        )
        return None

    chosen = fits[0]
    if targets and not any(facts.is_kind_of(target, chosen["range"]) for target in targets):
        issues.append(
            ValidationIssue(
                code=CODE_RELATION_TARGET_MISMATCH,
                requirement_id=requirement.requirement_id,
                detail=(
                    "the requirement's target is not the kind of thing this relation "
                    "returns from the submitted anchor"
                ),
                refs=(relationship.predicate_ref,),
            )
        )
        return None

    endpoint_families = _families_of(facts, chosen["range"])
    if endpoint_families:
        target_families = {
            family for target in targets for family in _families_of(facts, target)
        }
        if not endpoint_families & target_families:
            issues.append(
                ValidationIssue(
                    code=CODE_CROSS_FAMILY_PREDICATE,
                    requirement_id=requirement.requirement_id,
                    detail="this relation belongs to another product family than the target",
                    refs=(relationship.predicate_ref, *requirement.target_dataset_refs),
                )
            )
            return None

    return RelationBinding(
        predicate_id=chosen["predicate"],
        submitted_predicate_id=semantic_id,
        subject_class_id=chosen["domain"],
        object_class_id=chosen["range"],
        anchor_entity_key=anchor.resolved_key,
        anchor_class_id=anchor.entity_class_id,
        traversal=TRAVERSAL_FROM_ANCHOR,
    )


def _direction_options(facts: RegistryFacts, semantic_id: str) -> list[dict[str, str]]:
    """The submitted predicate and its declared inverses — never a mode sibling."""
    options = []
    for value in (semantic_id, *inverse_partners(facts, semantic_id)):
        if not facts.has(value):
            continue
        evidence = facts.term(value).evidence
        domain = [str(item) for item in evidence.get("domain", ()) or ()]
        range_ = [str(item) for item in evidence.get("range", ()) or ()]
        if not domain or not range_:
            continue
        options.append({"predicate": value, "domain": domain[0], "range": range_[0]})
    return options


def _families_of(facts: RegistryFacts, semantic_id: str) -> set[str]:
    if not semantic_id or not facts.has(semantic_id):
        return set()
    return {str(value) for value in facts.term(semantic_id).evidence.get("families", ()) or ()}
