"""The ``submit_semantic_query`` input contract, parsed fail-closed.

What the model may say is bounded by what it can name. Every slot here holds
either a per-request reference or a span copied from the question; there is no
slot for a table, a column, a join, a traversal order or a product identifier,
so a submission cannot express an execution plan even if the model tries to
write one.

Condition values, comparison words, ordering directions and limits are carried
as question spans rather than normalised values. The 0-A re-verification showed
the model does not preserve them reliably under normalisation, so the server
derives the executable form from the span and the field's own metadata — or,
where it cannot yet, refuses.

Parsing is deliberately unforgiving. A string where a list belongs would
iterate into single characters and produce references nobody wrote; an
unrecognised property is a model saying something this contract has no way to
honour. Both are reported as structured problems rather than coerced, because a
submission that was silently repaired is a submission nobody validated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contract import (
    REQUIREMENT_KINDS,
    REQUIREMENT_STATUSES,
    STATUS_AMBIGUOUS,
    STATUS_MAPPED,
    STATUS_UNRESOLVED,
)
from .refs import (
    KIND_DATASET,
    KIND_ENTITY,
    KIND_FIELD,
    KIND_PREDICATE,
    KIND_PREFIXES,
    well_formed_reference,
)

__all__ = [
    "STATUS_AMBIGUOUS",
    "STATUS_MAPPED",
    "STATUS_UNRESOLVED",
    "ShapeProblem",
    "Submission",
    "SubmittedAggregation",
    "SubmittedCondition",
    "SubmittedOrdering",
    "SubmittedQuery",
    "SubmittedRelationship",
    "SubmittedRequirement",
    "parse_submission",
]

CODE_MALFORMED_SUBMISSION = "malformed_submission"
CODE_MALFORMED_REQUIREMENT = "malformed_requirement"
CODE_UNKNOWN_PROPERTY = "unknown_property"
CODE_WRONG_TYPE = "wrong_property_type"
CODE_MISSING_REQUIREMENT_ID = "missing_requirement_id"
CODE_DUPLICATE_REQUIREMENT_ID = "duplicate_requirement_id"
CODE_UNKNOWN_KIND = "unknown_requirement_kind"
CODE_UNKNOWN_STATUS = "unknown_requirement_status"
CODE_EMPTY_SUBMISSION = "empty_submission"
CODE_WRONG_REF_KIND = "wrong_reference_kind"
CODE_MALFORMED_REF = "malformed_reference"
CODE_MISSING_REQUIRED_SPAN = "missing_required_span"

# Which reference kind each slot accepts. The prefixes come from the minter, so
# the parser and the published schema constrain the same thing.
SLOT_KINDS = {
    "target_dataset_refs": KIND_DATASET,
    "field_refs": KIND_FIELD,
    "output_field_refs": KIND_FIELD,
    "grouping_field_refs": KIND_FIELD,
    "condition.field_ref": KIND_FIELD,
    "ordering.field_ref": KIND_FIELD,
    "aggregation.field_ref": KIND_FIELD,
    "relationship.predicate_ref": KIND_PREDICATE,
    "relationship.anchor_entity_ref": KIND_ENTITY,
}
SLOT_PREFIXES = {slot: KIND_PREFIXES[kind] for slot, kind in SLOT_KINDS.items()}

# Spans a slot cannot mean anything without. A condition with no comparison is
# not a weaker condition, it is an unreadable one.
REQUIRED_SPANS = {
    "requirement": ("source_span",),
    "condition": ("comparison_span", "value_span"),
    "ordering": ("direction_span",),
    "aggregation": ("function_span",),
}

REQUIREMENT_PROPERTIES = frozenset(
    {
        "requirement_id",
        "kind",
        "status",
        "source_span",
        "target_dataset_refs",
        "field_refs",
        "output_field_refs",
        "conditions",
        "ordering",
        "limit_span",
        "aggregation",
        "grouping_field_refs",
        "relationship",
    }
)
CONDITION_PROPERTIES = frozenset({"field_ref", "comparison_span", "value_span"})
ORDERING_PROPERTIES = frozenset({"field_ref", "direction_span"})
AGGREGATION_PROPERTIES = frozenset({"field_ref", "function_span"})
RELATIONSHIP_PROPERTIES = frozenset({"predicate_ref", "anchor_entity_ref"})
SUBMISSION_PROPERTIES = frozenset({"requirements", "unaccounted_spans"})


@dataclass(frozen=True)
class SubmittedCondition:
    field_ref: str
    comparison_span: str = ""
    value_span: str = ""


@dataclass(frozen=True)
class SubmittedOrdering:
    field_ref: str
    direction_span: str = ""


@dataclass(frozen=True)
class SubmittedAggregation:
    field_ref: str
    function_span: str = ""


@dataclass(frozen=True)
class SubmittedRelationship:
    predicate_ref: str
    anchor_entity_ref: str


@dataclass(frozen=True)
class SubmittedRequirement:
    requirement_id: str
    kind: str
    status: str
    source_span: str = ""
    target_dataset_refs: tuple[str, ...] = ()
    field_refs: tuple[str, ...] = ()
    output_field_refs: tuple[str, ...] = ()
    conditions: tuple[SubmittedCondition, ...] = ()
    ordering: SubmittedOrdering | None = None
    limit_span: str = ""
    aggregation: SubmittedAggregation | None = None
    grouping_field_refs: tuple[str, ...] = ()
    relationship: SubmittedRelationship | None = None

    @property
    def referenced_field_refs(self) -> tuple[tuple[str, str], ...]:
        """Every field reference this requirement names, with the role it plays."""
        rows: list[tuple[str, str]] = [(ref, "output") for ref in self.field_refs]
        rows += [(ref, "output") for ref in self.output_field_refs]
        rows += [(condition.field_ref, "condition") for condition in self.conditions]
        rows += [(ref, "grouping") for ref in self.grouping_field_refs]
        if self.ordering is not None:
            rows.append((self.ordering.field_ref, "ordering"))
        if self.aggregation is not None:
            rows.append((self.aggregation.field_ref, "aggregation"))
        return tuple(rows)


@dataclass(frozen=True)
class SubmittedQuery:
    requirements: tuple[SubmittedRequirement, ...] = ()
    unaccounted_spans: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShapeProblem:
    code: str
    detail: str
    requirement_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "requirement_id": self.requirement_id}


@dataclass
class Submission:
    query: SubmittedQuery | None
    problems: tuple[ShapeProblem, ...] = ()

    @property
    def well_formed(self) -> bool:
        return self.query is not None and not self.problems


def _is_list(value: Any) -> bool:
    """A list, and specifically not a string that would iterate into letters."""
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)


def _reference_problem(name: str, ref: str) -> str:
    """Classify a wrong kind separately from a malformed same-kind ref."""
    kind = SLOT_KINDS.get(name)
    if kind is None:
        return ""
    prefix = KIND_PREFIXES[kind]
    if not ref.startswith(f"{prefix}_"):
        return CODE_WRONG_REF_KIND
    return "" if well_formed_reference(ref, kind) else CODE_MALFORMED_REF


def _append_reference_problem(
    name: str, ref: str, requirement_id: str, problems: list[ShapeProblem]
) -> bool:
    code = _reference_problem(name, ref)
    if not code:
        return False
    detail = (
        f"{name} only accepts {SLOT_PREFIXES[name]}_ references"
        if code == CODE_WRONG_REF_KIND
        else f"{name} requires the complete opaque reference format"
    )
    problems.append(ShapeProblem(code, detail, requirement_id))
    return True


def _string_list(
    value: Any, *, name: str, requirement_id: str, problems: list[ShapeProblem]
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not _is_list(value):
        problems.append(
            ShapeProblem(CODE_WRONG_TYPE, f"{name} must be a list of references", requirement_id)
        )
        return ()
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            problems.append(
                ShapeProblem(
                    CODE_WRONG_TYPE, f"{name} must contain only references", requirement_id
                )
            )
            return ()
        if _append_reference_problem(name, item, requirement_id, problems):
            return ()
        out.append(item)
    return tuple(out)


def _object(
    value: Any,
    *,
    name: str,
    allowed: frozenset[str],
    requirement_id: str,
    problems: list[ShapeProblem],
) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        problems.append(
            ShapeProblem(CODE_WRONG_TYPE, f"{name} must be an object", requirement_id)
        )
        return None
    unknown = sorted(set(value) - allowed)
    if unknown:
        problems.append(
            ShapeProblem(CODE_UNKNOWN_PROPERTY, f"{name} has unknown {unknown}", requirement_id)
        )
        return None
    return value


def _text(
    value: Any,
    *,
    name: str,
    requirement_id: str,
    problems: list[ShapeProblem],
    required: bool = False,
) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        problems.append(ShapeProblem(CODE_WRONG_TYPE, f"{name} must be text", requirement_id))
        return ""
    if required and not value.strip():
        problems.append(
            ShapeProblem(
                CODE_MISSING_REQUIRED_SPAN,
                f"{name} must quote the question and cannot be empty",
                requirement_id,
            )
        )
        return ""
    return value


def _ref(
    value: Any, *, name: str, requirement_id: str, problems: list[ShapeProblem]
) -> str:
    text = _text(
        value, name=name, requirement_id=requirement_id, problems=problems, required=True
    )
    if text and _append_reference_problem(name, text, requirement_id, problems):
        return ""
    return text


def parse_submission(payload: Mapping[str, Any]) -> Submission:
    """Read a tool payload into the contract, refusing anything it cannot honour."""
    problems: list[ShapeProblem] = []
    if not isinstance(payload, Mapping):
        return Submission(None, (ShapeProblem(CODE_MALFORMED_SUBMISSION, "not an object"),))
    unknown = sorted(set(payload) - SUBMISSION_PROPERTIES)
    if unknown:
        problems.append(
            ShapeProblem(CODE_UNKNOWN_PROPERTY, f"submission has unknown {unknown}")
        )
    raw_requirements = payload.get("requirements")
    if not _is_list(raw_requirements):
        return Submission(
            None,
            (
                *problems,
                ShapeProblem(CODE_MALFORMED_SUBMISSION, "requirements must be a list"),
            ),
        )
    unaccounted = _string_list(
        payload.get("unaccounted_spans"),
        name="unaccounted_spans",
        requirement_id="",
        problems=problems,
    )

    requirements: list[SubmittedRequirement] = []
    seen: set[str] = set()
    for index, row in enumerate(raw_requirements):
        parsed = _parse_requirement(row, index, seen, problems)
        if parsed is not None:
            requirements.append(parsed)
    if not requirements and not problems:
        problems.append(ShapeProblem(CODE_EMPTY_SUBMISSION, "no requirement was submitted"))
    return Submission(
        SubmittedQuery(requirements=tuple(requirements), unaccounted_spans=unaccounted),
        tuple(problems),
    )


def _parse_requirement(
    row: Any, index: int, seen: set[str], problems: list[ShapeProblem]
) -> SubmittedRequirement | None:
    if not isinstance(row, Mapping):
        problems.append(
            ShapeProblem(CODE_MALFORMED_REQUIREMENT, f"item {index} is not an object")
        )
        return None
    requirement_id = row.get("requirement_id")
    if not isinstance(requirement_id, str) or not requirement_id.strip():
        problems.append(
            ShapeProblem(CODE_MISSING_REQUIREMENT_ID, f"item {index} has no requirement_id")
        )
        return None
    requirement_id = requirement_id.strip()
    if requirement_id in seen:
        problems.append(
            ShapeProblem(CODE_DUPLICATE_REQUIREMENT_ID, "repeated id", requirement_id)
        )
        return None
    seen.add(requirement_id)

    unknown = sorted(set(row) - REQUIREMENT_PROPERTIES)
    if unknown:
        problems.append(
            ShapeProblem(
                CODE_UNKNOWN_PROPERTY, f"requirement has unknown {unknown}", requirement_id
            )
        )
        return None
    kind = row.get("kind")
    if kind not in REQUIREMENT_KINDS:
        problems.append(ShapeProblem(CODE_UNKNOWN_KIND, f"kind={kind!r}", requirement_id))
        return None
    status = row.get("status")
    if status not in REQUIREMENT_STATUSES:
        problems.append(ShapeProblem(CODE_UNKNOWN_STATUS, f"status={status!r}", requirement_id))
        return None

    before = len(problems)
    conditions = _parse_conditions(row.get("conditions"), requirement_id, problems)
    ordering_payload = _object(
        row.get("ordering"),
        name="ordering",
        allowed=ORDERING_PROPERTIES,
        requirement_id=requirement_id,
        problems=problems,
    )
    aggregation_payload = _object(
        row.get("aggregation"),
        name="aggregation",
        allowed=AGGREGATION_PROPERTIES,
        requirement_id=requirement_id,
        problems=problems,
    )
    relationship_payload = _object(
        row.get("relationship"),
        name="relationship",
        allowed=RELATIONSHIP_PROPERTIES,
        requirement_id=requirement_id,
        problems=problems,
    )
    parsed = SubmittedRequirement(
        requirement_id=requirement_id,
        kind=str(kind),
        status=str(status),
        source_span=_text(
            row.get("source_span"),
            name="source_span",
            requirement_id=requirement_id,
            problems=problems,
            required=True,
        ),
        target_dataset_refs=_string_list(
            row.get("target_dataset_refs"),
            name="target_dataset_refs",
            requirement_id=requirement_id,
            problems=problems,
        ),
        field_refs=_string_list(
            row.get("field_refs"),
            name="field_refs",
            requirement_id=requirement_id,
            problems=problems,
        ),
        output_field_refs=_string_list(
            row.get("output_field_refs"),
            name="output_field_refs",
            requirement_id=requirement_id,
            problems=problems,
        ),
        conditions=conditions,
        ordering=(
            SubmittedOrdering(
                field_ref=_ref(
                    ordering_payload.get("field_ref"),
                    name="ordering.field_ref",
                    requirement_id=requirement_id,
                    problems=problems,
                ),
                direction_span=_text(
                    ordering_payload.get("direction_span"),
                    name="ordering.direction_span",
                    requirement_id=requirement_id,
                    problems=problems,
                    required=True,
                ),
            )
            if ordering_payload is not None
            else None
        ),
        limit_span=_text(
            row.get("limit_span"),
            name="limit_span",
            requirement_id=requirement_id,
            problems=problems,
        ),
        aggregation=(
            SubmittedAggregation(
                field_ref=_ref(
                    aggregation_payload.get("field_ref"),
                    name="aggregation.field_ref",
                    requirement_id=requirement_id,
                    problems=problems,
                ),
                function_span=_text(
                    aggregation_payload.get("function_span"),
                    name="aggregation.function_span",
                    requirement_id=requirement_id,
                    problems=problems,
                    required=True,
                ),
            )
            if aggregation_payload is not None
            else None
        ),
        grouping_field_refs=_string_list(
            row.get("grouping_field_refs"),
            name="grouping_field_refs",
            requirement_id=requirement_id,
            problems=problems,
        ),
        relationship=(
            SubmittedRelationship(
                predicate_ref=_ref(
                    relationship_payload.get("predicate_ref"),
                    name="relationship.predicate_ref",
                    requirement_id=requirement_id,
                    problems=problems,
                ),
                anchor_entity_ref=_ref(
                    relationship_payload.get("anchor_entity_ref"),
                    name="relationship.anchor_entity_ref",
                    requirement_id=requirement_id,
                    problems=problems,
                ),
            )
            if relationship_payload is not None
            else None
        ),
    )
    if len(problems) != before:
        return None
    return parsed


def _parse_conditions(
    value: Any, requirement_id: str, problems: list[ShapeProblem]
) -> tuple[SubmittedCondition, ...]:
    if value is None:
        return ()
    if not _is_list(value):
        problems.append(
            ShapeProblem(CODE_WRONG_TYPE, "conditions must be a list", requirement_id)
        )
        return ()
    conditions: list[SubmittedCondition] = []
    for item in value:
        payload = _object(
            item,
            name="condition",
            allowed=CONDITION_PROPERTIES,
            requirement_id=requirement_id,
            problems=problems,
        )
        if payload is None:
            return ()
        conditions.append(
            SubmittedCondition(
                field_ref=_ref(
                    payload.get("field_ref"),
                    name="condition.field_ref",
                    requirement_id=requirement_id,
                    problems=problems,
                ),
                comparison_span=_text(
                    payload.get("comparison_span"),
                    name="condition.comparison_span",
                    requirement_id=requirement_id,
                    problems=problems,
                    required=True,
                ),
                value_span=_text(
                    payload.get("value_span"),
                    name="condition.value_span",
                    requirement_id=requirement_id,
                    problems=problems,
                    required=True,
                ),
            )
        )
    return tuple(conditions)
