"""Logical structures exchanged across the HCX semantic boundary.

Experiment only. The wire encoding is an experiment variable
(``ARCHITECTURE.md`` section 4), so every encoding decodes into the structures
below and every measurement reads only these structures.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# QUESTION_STRUCTURE.md section 2 defines the result units a question can ask
# for, and section 5 defines how an explicit requirement may terminate. Both
# enumerations are semantic contract vocabulary, not data values.
RequirementKind = Literal[
    "listing",
    "attribute_lookup",
    "count",
    "aggregation",
    "ranking",
    "grouping",
    "comparison",
    "explanation",
]
REQUIREMENT_KINDS: tuple[str, ...] = (
    "listing",
    "attribute_lookup",
    "count",
    "aggregation",
    "ranking",
    "grouping",
    "comparison",
    "explanation",
)

RequirementStatus = Literal["mapped", "unresolved", "ambiguous"]
REQUIREMENT_STATUSES: tuple[str, ...] = ("mapped", "unresolved", "ambiguous")

CandidateKind = Literal["dataset", "field", "predicate", "entity"]

# A requirement's detail slots. ARCHITECTURE.md section 4 already requires the
# logical contract to preserve filters, relationship filters, order and limit;
# these slots are the experiment's compact encoding of that requirement.
DETAIL_SLOTS: tuple[str, ...] = (
    "condition",
    "relationship",
    "aggregation",
    "order",
    "limit",
    "comparison_subject",
)
(
    SLOT_CONDITION,
    SLOT_RELATIONSHIP,
    SLOT_AGGREGATION,
    SLOT_ORDER,
    SLOT_LIMIT,
    SLOT_COMPARISON_SUBJECT,
) = DETAIL_SLOTS

# QUESTION_STRUCTURE.md section 2 lists aggregation as a result unit; which
# function was asked for is part of the question's meaning.
AGGREGATE_FUNCTIONS: tuple[str, ...] = ("count", "sum", "average", "minimum", "maximum")

# Condition comparison vocabulary. Derived from QUESTION_STRUCTURE.md section 2
# ("수치 비교, 범위, 포함, 관계, 기간, status"), not from any physical column.
CONDITION_OPERATORS: tuple[str, ...] = (
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "contains",
    "at_least",
    "at_most",
)

# Relationship traversal. The predicate candidate declares its own orientation;
# the question decides which end is known.
TRAVERSALS: tuple[str, ...] = ("subject_to_object", "object_to_subject")

SORT_DIRECTIONS: tuple[str, ...] = ("ascending", "descending")


class Candidate(BaseModel):
    """One Runtime View candidate carrying its own semantic discriminators."""

    model_config = ConfigDict(frozen=True)

    catalog_key: str
    kind: CandidateKind
    ref: str
    label: str
    meaning: str
    dataset_key: str | None = None
    dataset_ref: str | None = None
    period: str | None = None
    unit: str | None = None
    currency: str | None = None
    grain: str | None = None
    source: str | None = None
    direction: str | None = None
    subject_role: str | None = None
    object_role: str | None = None
    identifier_scheme: str | None = None
    allowed_operations: tuple[str, ...] = ()

    def as_prompt_payload(self) -> dict[str, object]:
        """Render the candidate for the model without leaking the catalog key.

        ``catalog_key`` and ``dataset_key`` are harness-side handles. Sending
        either would give the model a stable, meaningful identifier and defeat
        the opaque-ref experiment, so ownership travels as ``dataset_ref`` — the
        request-scoped ref of the owning dataset candidate.
        """
        payload: dict[str, object] = {"ref": self.ref, "label": self.label, "meaning": self.meaning}
        optional = {
            "belongs_to_dataset_ref": self.dataset_ref,
            "period": self.period,
            "unit": self.unit,
            "currency": self.currency,
            "grain": self.grain,
            "source": self.source,
            "direction": self.direction,
            "subject_role": self.subject_role,
            "object_role": self.object_role,
            "identifier_scheme": self.identifier_scheme,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        if self.allowed_operations:
            payload["allowed_operations"] = list(self.allowed_operations)
        return payload


class RuntimeView(BaseModel):
    """Per-request candidate set with request-scoped opaque refs."""

    model_config = ConfigDict(frozen=True)

    datasets: tuple[Candidate, ...]
    fields: tuple[Candidate, ...]
    predicates: tuple[Candidate, ...]
    entities: tuple[Candidate, ...]
    presentation_order: tuple[str, ...] = ()

    def all_candidates(self) -> tuple[Candidate, ...]:
        return self.datasets + self.fields + self.predicates + self.entities

    def refs(self) -> frozenset[str]:
        return frozenset(candidate.ref for candidate in self.all_candidates())

    def dataset_refs(self) -> frozenset[str]:
        return frozenset(candidate.ref for candidate in self.datasets)

    def key_by_ref(self) -> dict[str, str]:
        return {candidate.ref: candidate.catalog_key for candidate in self.all_candidates()}

    def ref_by_key(self) -> dict[str, str]:
        return {candidate.catalog_key: candidate.ref for candidate in self.all_candidates()}

    def as_prompt_payload(self) -> dict[str, object]:
        return {
            "dataset_candidates": [item.as_prompt_payload() for item in self.datasets],
            "field_candidates": [item.as_prompt_payload() for item in self.fields],
            "predicate_candidates": [item.as_prompt_payload() for item in self.predicates],
            "entity_candidates": [item.as_prompt_payload() for item in self.entities],
        }


class RequirementDetail(BaseModel):
    """One preserved piece of a requirement's meaning.

    ``slot`` decides how the other fields read:

    * ``condition``          ref=field ref, operator=comparison, value=literal
    * ``relationship``       ref=predicate ref, operator=traversal, value=anchor entity ref
    * ``aggregation``        ref=aggregated field ref, operator=aggregate function
    * ``order``              ref=field ref, operator=sort direction
    * ``limit``              value=requested row count
    * ``comparison_subject`` ref=entity ref being compared
    """

    model_config = ConfigDict(frozen=True)

    slot: str
    ref: str = ""
    operator: str = ""
    value: str = ""

    def carried_refs(self) -> tuple[str, ...]:
        refs = [self.ref] if self.ref else []
        if self.slot == SLOT_RELATIONSHIP and self.value:
            refs.append(self.value)
        return tuple(refs)


class RequirementRecord(BaseModel):
    """One explicit requirement the model accounted for."""

    model_config = ConfigDict(frozen=True)

    requirement_id: str
    text_span: str = ""
    kind: str = ""
    status: str = ""
    refs: tuple[str, ...] = ()
    details: tuple[RequirementDetail, ...] = ()
    note: str = ""

    def details_for(self, slot: str) -> tuple[RequirementDetail, ...]:
        return tuple(detail for detail in self.details if detail.slot == slot)


class QuestionSemantics(BaseModel):
    """Decoded result of one semantic-accounting call, independent of encoding."""

    model_config = ConfigDict(frozen=True)

    target_dataset_refs: tuple[str, ...] = ()
    requirements: tuple[RequirementRecord, ...] = Field(default=())

    def all_refs(self) -> tuple[str, ...]:
        refs = list(self.target_dataset_refs)
        for requirement in self.requirements:
            refs.extend(requirement.refs)
            for detail in requirement.details:
                refs.extend(detail.carried_refs())
        return tuple(refs)
