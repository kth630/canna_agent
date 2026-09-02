"""The grouped-flat wire encoding of the same submission contract.

``RUNTIME_VIEW_TOOL_DECISION_20260831.md`` section 5 approved this in advance:
keep the nested schema as primary, and if the provider constraint reproduces,
carry the same logical contract as flat records grouped by a repeated
``requirement_id``. The constraint reproduced. Three single calls on
2026-08-31 — the neutral schema, the keyword projection of it, and that
projection under the stage 0-A function name — were each refused with API
``40009`` before any tool was emitted. In the final 0-A evaluation the same
provider took ``grouped_flat`` 0 times out of 93 as a provider failure, against
24 for ``nested`` and 5 for ``delimited``.

So the wire changes and nothing behind it does. This module is a translator: a
grouped-flat payload is assembled into exactly the canonical submission shape
``parse_submission`` already reads, and then handed to it. Every rule the
server enforces — the complete reference format, reference kind per slot,
non-empty spans, closed objects, at least one requirement, the three
requirement statuses — is enforced once, in the place it already lived. Nothing
here re-implements a check, and nothing here can pass something the nested
encoding would have refused.

Grouping is by repeated ``requirement_id`` and nothing else. What belongs
together stays together: a condition is one record carrying its own field
reference, its comparison span and its value span, so two conditions on one
requirement can never have their halves swapped. That is the property
``ARCHITECTURE.md`` section 4 asks for when it forbids splitting bound
span/ref/status groups into independent parallel arrays.

A record that names a requirement nobody declared, a second ordering for one
requirement, a repeated reference, an unknown role or an unknown detail kind is
refused rather than merged. Assembly that silently reconciled records would be
a second, looser contract wearing the first one's name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contract import REQUIREMENT_KINDS, REQUIREMENT_STATUSES
from .hcx_wire import project_for_hcx
from .query import (
    CODE_MALFORMED_SUBMISSION,
    CODE_MISSING_REQUIREMENT_ID,
    CODE_UNKNOWN_PROPERTY,
    CODE_WRONG_TYPE,
    ShapeProblem,
    Submission,
    parse_submission,
)

__all__ = [
    "CODE_CONFLICTING_RECORD",
    "CODE_DUPLICATE_RECORD",
    "CODE_ORPHAN_RECORD",
    "CODE_UNKNOWN_DETAIL_KIND",
    "CODE_UNKNOWN_ROLE",
    "DETAIL_KINDS",
    "GROUPED_FLAT_PROPERTIES",
    "REF_ROLES",
    "assemble_submission_payload",
    "grouped_flat_schema",
    "grouped_flat_slots",
    "parse_grouped_flat",
    "to_grouped_flat",
]

# ------------------------------------------------------------------ vocabulary

# Wire property names, written once so the schema and the assembler cannot
# disagree about what a record is called.
P_REQUIREMENT_RECORDS = "requirement_records"
P_REF_RECORDS = "ref_records"
P_DETAIL_RECORDS = "detail_records"
P_UNACCOUNTED_SPANS = "unaccounted_spans"

P_REQUIREMENT_ID = "requirement_id"
P_KIND = "kind"
P_STATUS = "status"
P_SOURCE_SPAN = "source_span"
P_LIMIT_SPAN = "limit_span"
P_ROLE = "role"
P_REF = "ref"
P_DETAIL_KIND = "detail_kind"
P_SPAN = "span"
P_VALUE_SPAN = "value_span"

# Each role routes a reference into one canonical slot. The slot decides which
# kind of reference is acceptable — ``query.SLOT_KINDS`` already says so and the
# parser already checks it — so a role is a routing decision, never a second
# opinion about reference kinds.
LIST_ROLES: dict[str, str] = {
    "target_dataset": "target_dataset_refs",
    "field": "field_refs",
    "output_field": "output_field_refs",
    "grouping_field": "grouping_field_refs",
}
RELATION_ROLES: dict[str, str] = {
    "relationship_predicate": "predicate_ref",
    "relationship_anchor_entity": "anchor_entity_ref",
}
REF_ROLES: tuple[str, ...] = (*LIST_ROLES, *RELATION_ROLES)

DETAIL_CONDITION = "condition"
DETAIL_ORDERING = "ordering"
DETAIL_AGGREGATION = "aggregation"
DETAIL_KINDS: tuple[str, ...] = (DETAIL_CONDITION, DETAIL_ORDERING, DETAIL_AGGREGATION)

# Where a detail's own reference goes, and what its spans are called once the
# record becomes the canonical object.
_DETAIL_SLOTS: dict[str, str] = {
    DETAIL_CONDITION: "condition.field_ref",
    DETAIL_ORDERING: "ordering.field_ref",
    DETAIL_AGGREGATION: "aggregation.field_ref",
}
_DETAIL_SPAN_NAMES: dict[str, str] = {
    DETAIL_CONDITION: "comparison_span",
    DETAIL_ORDERING: "direction_span",
    DETAIL_AGGREGATION: "function_span",
}
# At most one per requirement. A condition is repeatable; an ordering or an
# aggregation is not, and a second one is a conflict rather than a refinement.
_SINGULAR_DETAILS = frozenset({DETAIL_ORDERING, DETAIL_AGGREGATION})

REQUIREMENT_RECORD_PROPERTIES = frozenset(
    {P_REQUIREMENT_ID, P_KIND, P_STATUS, P_SOURCE_SPAN, P_LIMIT_SPAN}
)
REF_RECORD_PROPERTIES = frozenset({P_REQUIREMENT_ID, P_ROLE, P_REF})
DETAIL_RECORD_PROPERTIES = frozenset(
    {P_REQUIREMENT_ID, P_DETAIL_KIND, P_REF, P_SPAN, P_VALUE_SPAN}
)
GROUPED_FLAT_PROPERTIES = frozenset(
    {P_REQUIREMENT_RECORDS, P_REF_RECORDS, P_DETAIL_RECORDS, P_UNACCOUNTED_SPANS}
)

# Structural problems only this encoding can have. Everything else reuses the
# codes the canonical parser already publishes.
CODE_ORPHAN_RECORD = "orphan_record"
CODE_DUPLICATE_RECORD = "duplicate_record"
CODE_CONFLICTING_RECORD = "conflicting_record"
CODE_UNKNOWN_ROLE = "unknown_reference_role"
CODE_UNKNOWN_DETAIL_KIND = "unknown_detail_kind"


# ---------------------------------------------------------------- wire schema

# Compatibility minimisation, 2026-08-31. A minimal declaration (244 bytes) was
# accepted by the provider on the same model, key and client that refused four
# project declarations of 3.6-4.4 KB. Descriptions were most of that weight —
# 2,167 bytes across 19 of them — so they are cut to what a reader needs to fill
# the slot correctly, and the longer guidance about roles and detail kinds moves
# into the system message, which is instruction rather than declaration.
#
# Nothing the contract depends on was cut: every property name, enum value,
# required entry, nesting level and ``additionalProperties`` is unchanged, and
# the parser is untouched.

DESCRIPTION = (
    "Account for the question's explicit requirements using the references this "
    "request offered. Every record repeats its requirement_id."
)

_SPAN_GUIDE = "copied from the question, not normalised"


def _text_property(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _string() -> dict[str, Any]:
    """A string slot whose own name already says what it holds.

    Every description costs about seventeen bytes before a word of it is
    written, and the declaration's weight is the thing being reduced. What these
    slots need said is said once in the system message instead.
    """
    return {"type": "string"}


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _array(items: dict[str, Any], description: str) -> dict[str, Any]:
    return {"type": "array", "description": description, "items": items}


_REQUIREMENT_RECORD_SCHEMA = _object(
    {
        P_REQUIREMENT_ID: _text_property("an id you choose; other records repeat it"),
        P_KIND: {"type": "string", "enum": list(REQUIREMENT_KINDS)},
        P_STATUS: {"type": "string", "enum": list(REQUIREMENT_STATUSES)},
        P_SOURCE_SPAN: _text_property(f"the words asking for this, {_SPAN_GUIDE}"),
        P_LIMIT_SPAN: _string(),
    },
    [P_REQUIREMENT_ID, P_KIND, P_STATUS, P_SOURCE_SPAN],
)

_REF_RECORD_SCHEMA = _object(
    {
        P_REQUIREMENT_ID: _string(),
        P_ROLE: {"type": "string", "enum": list(REF_ROLES)},
        P_REF: _text_property("an opaque reference this request offered"),
    },
    [P_REQUIREMENT_ID, P_ROLE, P_REF],
)

_DETAIL_RECORD_SCHEMA = _object(
    {
        P_REQUIREMENT_ID: _string(),
        P_DETAIL_KIND: {"type": "string", "enum": list(DETAIL_KINDS)},
        P_REF: _string(),
        P_SPAN: _text_property(f"comparison, direction or function words, {_SPAN_GUIDE}"),
        P_VALUE_SPAN: _text_property("the value words; condition only"),
    },
    [P_REQUIREMENT_ID, P_DETAIL_KIND, P_REF, P_SPAN],
)

# The root carries no description: the function envelope already states it, and
# stating it twice was 309 bytes of the refused declaration.
GROUPED_FLAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        P_REQUIREMENT_RECORDS: _array(
            _REQUIREMENT_RECORD_SCHEMA, "one per requirement the question states"
        ),
        P_REF_RECORDS: _array(_REF_RECORD_SCHEMA, "references, by requirement_id"),
        P_DETAIL_RECORDS: _array(
            _DETAIL_RECORD_SCHEMA,
            "conditions, ordering, aggregation, by requirement_id",
        ),
        P_UNACCOUNTED_SPANS: _array(_string(), "question parts not accounted for"),
    },
    "required": [P_REQUIREMENT_RECORDS],
}


def grouped_flat_schema() -> dict[str, Any]:
    """The wire schema, in the keyword vocabulary the provider has accepted.

    Authored in that vocabulary and projected anyway, so the guarantee is
    enforced rather than remembered.
    """
    return project_for_hcx(GROUPED_FLAT_SCHEMA)


# ------------------------------------------------------------------- assembly


def _is_list(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)


class _Assembler:
    """Builds the canonical payload, reporting rather than reconciling."""

    def __init__(self) -> None:
        self.problems: list[ShapeProblem] = []
        self.order: list[str] = []
        self.rows: dict[str, dict[str, Any]] = {}
        self.seen_refs: dict[str, set[tuple[str, Any]]] = {}
        self.seen_details: dict[str, list[tuple[Any, ...]]] = {}

    def problem(self, code: str, detail: str, requirement_id: str = "") -> None:
        self.problems.append(ShapeProblem(code, detail, requirement_id))

    def record_mapping(
        self, row: Any, *, name: str, allowed: frozenset[str], index: int
    ) -> Mapping[str, Any] | None:
        if not isinstance(row, Mapping):
            self.problem(CODE_WRONG_TYPE, f"{name} item {index} is not an object")
            return None
        unknown = sorted(set(row) - allowed)
        if unknown:
            self.problem(CODE_UNKNOWN_PROPERTY, f"{name} item {index} has unknown {unknown}")
            return None
        return row

    def owner(self, row: Mapping[str, Any], *, name: str, index: int) -> str | None:
        raw = row.get(P_REQUIREMENT_ID)
        if not isinstance(raw, str) or not raw.strip():
            self.problem(CODE_MISSING_REQUIREMENT_ID, f"{name} item {index} names no requirement")
            return None
        requirement_id = raw.strip()
        if requirement_id not in self.rows:
            self.problem(
                CODE_ORPHAN_RECORD,
                f"{name} item {index} names a requirement that was not declared",
                requirement_id,
            )
            return None
        return requirement_id

    # -- requirement records

    def add_requirements(self, records: Any) -> bool:
        if not _is_list(records):
            self.problem(CODE_MALFORMED_SUBMISSION, f"{P_REQUIREMENT_RECORDS} must be a list")
            return False
        for index, row in enumerate(records):
            record = self.record_mapping(
                row,
                name=P_REQUIREMENT_RECORDS,
                allowed=REQUIREMENT_RECORD_PROPERTIES,
                index=index,
            )
            if record is None:
                continue
            raw = record.get(P_REQUIREMENT_ID)
            if not isinstance(raw, str) or not raw.strip():
                self.problem(
                    CODE_MISSING_REQUIREMENT_ID,
                    f"{P_REQUIREMENT_RECORDS} item {index} has no {P_REQUIREMENT_ID}",
                )
                continue
            requirement_id = raw.strip()
            if requirement_id in self.rows:
                self.problem(CODE_DUPLICATE_RECORD, "repeated requirement record", requirement_id)
                continue
            # kind, status and the spans are copied unread: the canonical parser
            # owns what they may say, and a value it would refuse must reach it.
            canonical: dict[str, Any] = {P_REQUIREMENT_ID: requirement_id}
            for name in (P_KIND, P_STATUS, P_SOURCE_SPAN):
                canonical[name] = record.get(name)
            if P_LIMIT_SPAN in record:
                canonical[P_LIMIT_SPAN] = record[P_LIMIT_SPAN]
            self.order.append(requirement_id)
            self.rows[requirement_id] = canonical
            self.seen_refs[requirement_id] = set()
            self.seen_details[requirement_id] = []
        return True

    # -- reference records

    def add_refs(self, records: Any) -> None:
        if records is None:
            return
        if not _is_list(records):
            self.problem(CODE_WRONG_TYPE, f"{P_REF_RECORDS} must be a list")
            return
        for index, row in enumerate(records):
            record = self.record_mapping(
                row, name=P_REF_RECORDS, allowed=REF_RECORD_PROPERTIES, index=index
            )
            if record is None:
                continue
            requirement_id = self.owner(record, name=P_REF_RECORDS, index=index)
            if requirement_id is None:
                continue
            role = record.get(P_ROLE)
            if role not in REF_ROLES:
                self.problem(CODE_UNKNOWN_ROLE, f"role={role!r}", requirement_id)
                continue
            ref = record.get(P_REF)
            signature = (str(role), ref if isinstance(ref, str) else repr(ref))
            if signature in self.seen_refs[requirement_id]:
                self.problem(
                    CODE_DUPLICATE_RECORD, f"{role} reference repeated", requirement_id
                )
                continue
            self.seen_refs[requirement_id].add(signature)
            canonical = self.rows[requirement_id]
            if role in LIST_ROLES:
                canonical.setdefault(LIST_ROLES[role], []).append(ref)
                continue
            relationship = canonical.setdefault("relationship", {})
            slot = RELATION_ROLES[str(role)]
            if slot in relationship:
                self.problem(
                    CODE_CONFLICTING_RECORD,
                    f"{role} was given more than one reference",
                    requirement_id,
                )
                continue
            relationship[slot] = ref

    # -- detail records

    def add_details(self, records: Any) -> None:
        if records is None:
            return
        if not _is_list(records):
            self.problem(CODE_WRONG_TYPE, f"{P_DETAIL_RECORDS} must be a list")
            return
        for index, row in enumerate(records):
            record = self.record_mapping(
                row, name=P_DETAIL_RECORDS, allowed=DETAIL_RECORD_PROPERTIES, index=index
            )
            if record is None:
                continue
            requirement_id = self.owner(record, name=P_DETAIL_RECORDS, index=index)
            if requirement_id is None:
                continue
            detail_kind = record.get(P_DETAIL_KIND)
            if detail_kind not in DETAIL_KINDS:
                self.problem(
                    CODE_UNKNOWN_DETAIL_KIND, f"detail_kind={detail_kind!r}", requirement_id
                )
                continue
            detail_kind = str(detail_kind)
            if detail_kind != DETAIL_CONDITION and P_VALUE_SPAN in record:
                self.problem(
                    CODE_UNKNOWN_PROPERTY,
                    f"{P_VALUE_SPAN} belongs only to a {DETAIL_CONDITION}",
                    requirement_id,
                )
                continue
            signature = (
                detail_kind,
                repr(record.get(P_REF)),
                repr(record.get(P_SPAN)),
                repr(record.get(P_VALUE_SPAN)),
            )
            if signature in self.seen_details[requirement_id]:
                self.problem(
                    CODE_DUPLICATE_RECORD, f"{detail_kind} detail repeated", requirement_id
                )
                continue
            self.seen_details[requirement_id].append(signature)

            canonical = self.rows[requirement_id]
            detail: dict[str, Any] = {
                "field_ref": record.get(P_REF),
                _DETAIL_SPAN_NAMES[detail_kind]: record.get(P_SPAN),
            }
            if detail_kind == DETAIL_CONDITION:
                detail[P_VALUE_SPAN] = record.get(P_VALUE_SPAN)
                canonical.setdefault("conditions", []).append(detail)
                continue
            if detail_kind in _SINGULAR_DETAILS and detail_kind in canonical:
                self.problem(
                    CODE_CONFLICTING_RECORD,
                    f"a requirement may carry one {detail_kind}",
                    requirement_id,
                )
                continue
            canonical[detail_kind] = detail

    def payload(self, unaccounted: Any) -> dict[str, Any]:
        canonical: dict[str, Any] = {
            "requirements": [self.rows[requirement_id] for requirement_id in self.order]
        }
        if unaccounted is not None:
            canonical["unaccounted_spans"] = unaccounted
        return canonical


def assemble_submission_payload(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, tuple[ShapeProblem, ...]]:
    """Turn a grouped-flat payload into the canonical submission shape.

    Returns ``(None, problems)`` only when there is nothing to hand on at all.
    Otherwise the canonical payload is returned *with* whatever problems
    assembly found, because the parser has its own to add and the caller must
    see both.
    """
    if not isinstance(payload, Mapping):
        return None, (ShapeProblem(CODE_MALFORMED_SUBMISSION, "not an object"),)
    assembler = _Assembler()
    unknown = sorted(set(payload) - GROUPED_FLAT_PROPERTIES)
    if unknown:
        assembler.problem(CODE_UNKNOWN_PROPERTY, f"submission has unknown {unknown}")
    if not assembler.add_requirements(payload.get(P_REQUIREMENT_RECORDS)):
        return None, tuple(assembler.problems)
    assembler.add_refs(payload.get(P_REF_RECORDS))
    assembler.add_details(payload.get(P_DETAIL_RECORDS))
    return assembler.payload(payload.get(P_UNACCOUNTED_SPANS)), tuple(assembler.problems)


def parse_grouped_flat(payload: Mapping[str, Any]) -> Submission:
    """Read a grouped-flat tool payload through the canonical parser.

    The encoding is the only thing that changed, so the validation is not
    repeated here: assembly routes records into canonical slots and
    ``parse_submission`` decides whether what arrived is acceptable.
    """
    canonical, problems = assemble_submission_payload(payload)
    if canonical is None:
        return Submission(None, problems)
    parsed = parse_submission(canonical)
    return Submission(parsed.query, (*problems, *parsed.problems))


# -------------------------------------------------------------------- encoding


def to_grouped_flat(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The inverse: a canonical submission payload as grouped-flat records.

    Used to show the two encodings carry the same contract, and to build wire
    payloads in tests without writing records by hand.
    """
    requirement_records: list[dict[str, Any]] = []
    ref_records: list[dict[str, Any]] = []
    detail_records: list[dict[str, Any]] = []

    for requirement in payload.get("requirements", ()):
        requirement_id = requirement.get(P_REQUIREMENT_ID)
        record = {
            P_REQUIREMENT_ID: requirement_id,
            P_KIND: requirement.get(P_KIND),
            P_STATUS: requirement.get(P_STATUS),
            P_SOURCE_SPAN: requirement.get(P_SOURCE_SPAN),
        }
        if P_LIMIT_SPAN in requirement:
            record[P_LIMIT_SPAN] = requirement[P_LIMIT_SPAN]
        requirement_records.append(record)

        for role, slot in LIST_ROLES.items():
            for ref in requirement.get(slot, ()) or ():
                ref_records.append(
                    {P_REQUIREMENT_ID: requirement_id, P_ROLE: role, P_REF: ref}
                )
        relationship = requirement.get("relationship") or {}
        for role, slot in RELATION_ROLES.items():
            if slot in relationship:
                ref_records.append(
                    {
                        P_REQUIREMENT_ID: requirement_id,
                        P_ROLE: role,
                        P_REF: relationship[slot],
                    }
                )
        for condition in requirement.get("conditions", ()) or ():
            detail_records.append(
                {
                    P_REQUIREMENT_ID: requirement_id,
                    P_DETAIL_KIND: DETAIL_CONDITION,
                    P_REF: condition.get("field_ref"),
                    P_SPAN: condition.get(_DETAIL_SPAN_NAMES[DETAIL_CONDITION]),
                    P_VALUE_SPAN: condition.get(P_VALUE_SPAN),
                }
            )
        for detail_kind in (DETAIL_ORDERING, DETAIL_AGGREGATION):
            detail = requirement.get(detail_kind)
            if detail:
                detail_records.append(
                    {
                        P_REQUIREMENT_ID: requirement_id,
                        P_DETAIL_KIND: detail_kind,
                        P_REF: detail.get("field_ref"),
                        P_SPAN: detail.get(_DETAIL_SPAN_NAMES[detail_kind]),
                    }
                )

    wire: dict[str, Any] = {P_REQUIREMENT_RECORDS: requirement_records}
    if ref_records:
        wire[P_REF_RECORDS] = ref_records
    if detail_records:
        wire[P_DETAIL_RECORDS] = detail_records
    if "unaccounted_spans" in payload:
        wire[P_UNACCOUNTED_SPANS] = payload["unaccounted_spans"]
    return wire


def grouped_flat_slots() -> dict[str, str]:
    """Every role and detail kind, and the canonical slot it routes into.

    Published so a test can check the routing table against the parser's own
    slot table instead of against a copy of it.
    """
    routes = {role: slot for role, slot in LIST_ROLES.items()}
    routes.update(
        {role: f"relationship.{slot}" for role, slot in RELATION_ROLES.items()}
    )
    routes.update({kind: _DETAIL_SLOTS[kind] for kind in DETAIL_KINDS})
    return routes
