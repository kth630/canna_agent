"""Grouped-flat is a different encoding of the same contract, not a looser one.

The provider refused the nested declaration three times on 2026-08-31, so the
wire moved to the fallback ``RUNTIME_VIEW_TOOL_DECISION_20260831.md`` section 5
approved in advance. That makes one question worth asking repeatedly here: can
anything now reach the server that the nested encoding would have refused?

The answer has to be no by construction — assembly routes records into
canonical slots and ``parse_submission`` decides them — so these tests check the
routing rather than re-checking the decisions: that everything survives a
round-trip, that records which cannot be grouped honestly are refused instead
of merged, and that a payload the canonical parser rejects is still rejected
with the same reason code when it arrives as records.

No network call is made anywhere here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from canna.runtime_view import (
    DETAIL_KINDS,
    REF_ROLES,
    assemble_submission_payload,
    grouped_flat_schema,
    grouped_flat_slots,
    hcx_tool_definition,
    keyword_vocabulary,
    parse_grouped_flat,
    parse_submission,
    to_grouped_flat,
)
from canna.runtime_view.grouped_flat import (
    GROUPED_FLAT_PROPERTIES,
    GROUPED_FLAT_SCHEMA,
)
from canna.runtime_view.hcx_wire import HCX_WIRE_KEYWORDS
from canna.runtime_view.query import SLOT_KINDS
from canna.runtime_view.refs import KIND_PREFIXES, REF_DIGITS
from canna.runtime_view.schema import FUNCTION_NAME

DATASET_REF = f"{KIND_PREFIXES['dataset']}_" + "0" * REF_DIGITS
FIELD_REF = f"{KIND_PREFIXES['field']}_" + "1" * REF_DIGITS
OTHER_FIELD_REF = f"{KIND_PREFIXES['field']}_" + "2" * REF_DIGITS
PREDICATE_REF = f"{KIND_PREFIXES['predicate']}_" + "3" * REF_DIGITS
ENTITY_REF = f"{KIND_PREFIXES['entity']}_" + "4" * REF_DIGITS


def _codes(parsed) -> set[str]:
    return {problem.code for problem in parsed.problems}


def _canonical(**overrides: Any) -> dict[str, Any]:
    row = {
        "requirement_id": "r1",
        "kind": "listing",
        "status": "mapped",
        "source_span": "국내 ETF",
        "target_dataset_refs": [DATASET_REF],
        "field_refs": [FIELD_REF],
    }
    row.update(overrides)
    return {"requirements": [row]}


RICH_CANONICAL: dict[str, Any] = {
    "requirements": [
        {
            "requirement_id": "r1",
            "kind": "ranking",
            "status": "mapped",
            "source_span": "1년 수익률이 높은 10개",
            "target_dataset_refs": [DATASET_REF],
            "field_refs": [FIELD_REF],
            "output_field_refs": [OTHER_FIELD_REF],
            "conditions": [
                {
                    "field_ref": FIELD_REF,
                    "comparison_span": "이상",
                    "value_span": "3%",
                },
                {
                    "field_ref": OTHER_FIELD_REF,
                    "comparison_span": "이하",
                    "value_span": "0.3%",
                },
            ],
            "ordering": {"field_ref": FIELD_REF, "direction_span": "높은"},
            "limit_span": "10개",
            "grouping_field_refs": [OTHER_FIELD_REF],
            "relationship": {
                "predicate_ref": PREDICATE_REF,
                "anchor_entity_ref": ENTITY_REF,
            },
        },
        {
            "requirement_id": "r2",
            "kind": "aggregation",
            "status": "unresolved",
            "source_span": "평균 총보수",
            "target_dataset_refs": [DATASET_REF],
            "aggregation": {"field_ref": OTHER_FIELD_REF, "function_span": "평균"},
        },
        {
            "requirement_id": "r3",
            "kind": "comparison",
            "status": "ambiguous",
            "source_span": "어느 쪽이 더 나은지",
            "target_dataset_refs": [DATASET_REF],
        },
    ],
    "unaccounted_spans": [],
}


# ------------------------------------------------------------------ round-trip


def test_a_canonical_submission_survives_the_round_trip_unchanged() -> None:
    wire = to_grouped_flat(RICH_CANONICAL)
    assembled, problems = assemble_submission_payload(wire)
    assert problems == ()
    assert assembled == RICH_CANONICAL


def test_the_round_trip_preserves_every_requirement_and_its_status() -> None:
    parsed = parse_grouped_flat(to_grouped_flat(RICH_CANONICAL))
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    direct = parse_submission(RICH_CANONICAL)
    assert direct.well_formed, direct.problems
    assert parsed.query == direct.query

    statuses = [requirement.status for requirement in parsed.query.requirements]
    kinds = [requirement.kind for requirement in parsed.query.requirements]
    ids = [requirement.requirement_id for requirement in parsed.query.requirements]
    assert ids == ["r1", "r2", "r3"]
    assert kinds == ["ranking", "aggregation", "comparison"]
    # an unresolved or ambiguous requirement is carried, never dropped
    assert statuses == ["mapped", "unresolved", "ambiguous"]


def test_conditions_keep_their_own_comparison_and_value_together() -> None:
    """Two conditions in one requirement must not have their halves swapped."""
    parsed = parse_grouped_flat(to_grouped_flat(RICH_CANONICAL))
    assert parsed.query is not None
    conditions = parsed.query.requirements[0].conditions
    assert [(c.field_ref, c.comparison_span, c.value_span) for c in conditions] == [
        (FIELD_REF, "이상", "3%"),
        (OTHER_FIELD_REF, "이하", "0.3%"),
    ]


def test_ordering_aggregation_limit_and_relationship_all_survive() -> None:
    parsed = parse_grouped_flat(to_grouped_flat(RICH_CANONICAL))
    assert parsed.query is not None
    first, second, _third = parsed.query.requirements
    assert first.ordering is not None
    assert (first.ordering.field_ref, first.ordering.direction_span) == (FIELD_REF, "높은")
    assert first.limit_span == "10개"
    assert first.grouping_field_refs == (OTHER_FIELD_REF,)
    assert first.output_field_refs == (OTHER_FIELD_REF,)
    assert first.relationship is not None
    assert first.relationship.predicate_ref == PREDICATE_REF
    assert first.relationship.anchor_entity_ref == ENTITY_REF
    assert second.aggregation is not None
    assert (second.aggregation.field_ref, second.aggregation.function_span) == (
        OTHER_FIELD_REF,
        "평균",
    )


def test_spans_are_carried_as_written_and_never_normalised() -> None:
    wire = to_grouped_flat(RICH_CANONICAL)
    spans = {
        record.get("span")
        for record in wire["detail_records"]
    } | {
        record.get("value_span")
        for record in wire["detail_records"]
        if record.get("value_span") is not None
    }
    assert {"이상", "이하", "높은", "평균", "3%", "0.3%"} <= spans
    serialised = json.dumps(wire, ensure_ascii=False)
    for normalised in ("gte", "lte", "desc", "descending", "avg", "0.03", "10"):
        assert f'"{normalised}"' not in serialised


def test_unaccounted_spans_reach_the_server() -> None:
    payload = dict(RICH_CANONICAL)
    payload["unaccounted_spans"] = ["설명해줘"]
    parsed = parse_grouped_flat(to_grouped_flat(payload))
    assert parsed.query is not None
    assert parsed.query.unaccounted_spans == ("설명해줘",)


# ------------------------------------------------- grouping cannot be faked


def test_a_record_naming_an_undeclared_requirement_is_refused() -> None:
    for records in (
        {"ref_records": [{"requirement_id": "nope", "role": "field", "ref": FIELD_REF}]},
        {
            "detail_records": [
                {
                    "requirement_id": "nope",
                    "detail_kind": "ordering",
                    "ref": FIELD_REF,
                    "span": "높은",
                }
            ]
        },
    ):
        wire = to_grouped_flat(_canonical())
        wire.update(records)
        parsed = parse_grouped_flat(wire)
        assert not parsed.well_formed
        assert "orphan_record" in _codes(parsed)


def test_a_record_without_a_requirement_id_is_refused() -> None:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"].append({"role": "field", "ref": FIELD_REF})
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "missing_requirement_id" in _codes(parsed)


def test_a_repeated_requirement_record_is_refused() -> None:
    wire = to_grouped_flat(_canonical())
    wire["requirement_records"].append(dict(wire["requirement_records"][0]))
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "duplicate_record" in _codes(parsed)


def test_a_repeated_reference_record_is_refused() -> None:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"].append(dict(wire["ref_records"][0]))
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "duplicate_record" in _codes(parsed)


def test_a_repeated_detail_record_is_refused() -> None:
    canonical = _canonical(ordering={"field_ref": FIELD_REF, "direction_span": "높은"})
    wire = to_grouped_flat(canonical)
    wire["detail_records"].append(dict(wire["detail_records"][0]))
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "duplicate_record" in _codes(parsed)


def test_two_conflicting_orderings_for_one_requirement_are_refused() -> None:
    canonical = _canonical(ordering={"field_ref": FIELD_REF, "direction_span": "높은"})
    wire = to_grouped_flat(canonical)
    wire["detail_records"].append(
        {
            "requirement_id": "r1",
            "detail_kind": "ordering",
            "ref": OTHER_FIELD_REF,
            "span": "낮은",
        }
    )
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "conflicting_record" in _codes(parsed)


def test_two_conflicting_relationship_predicates_are_refused() -> None:
    canonical = _canonical(
        relationship={"predicate_ref": PREDICATE_REF, "anchor_entity_ref": ENTITY_REF}
    )
    wire = to_grouped_flat(canonical)
    wire["ref_records"].append(
        {
            "requirement_id": "r1",
            "role": "relationship_predicate",
            "ref": f"{KIND_PREFIXES['predicate']}_" + "9" * REF_DIGITS,
        }
    )
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "conflicting_record" in _codes(parsed)


def test_an_unknown_role_or_detail_kind_is_refused() -> None:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"].append(
        {"requirement_id": "r1", "role": "physical_table", "ref": FIELD_REF}
    )
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "unknown_reference_role" in _codes(parsed)

    wire = to_grouped_flat(_canonical())
    wire["detail_records"] = [
        {"requirement_id": "r1", "detail_kind": "join", "ref": FIELD_REF, "span": "x"}
    ]
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "unknown_detail_kind" in _codes(parsed)


def test_a_value_span_outside_a_condition_is_refused() -> None:
    wire = to_grouped_flat(_canonical())
    wire["detail_records"] = [
        {
            "requirement_id": "r1",
            "detail_kind": "ordering",
            "ref": FIELD_REF,
            "span": "높은",
            "value_span": "10",
        }
    ]
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "unknown_property" in _codes(parsed)


# ------------------------------- the server's own refusals are unchanged


@pytest.mark.parametrize(
    ("role", "wrong_ref"),
    [
        ("target_dataset", FIELD_REF),
        ("field", DATASET_REF),
        ("output_field", PREDICATE_REF),
        ("grouping_field", ENTITY_REF),
        ("relationship_predicate", FIELD_REF),
        ("relationship_anchor_entity", FIELD_REF),
    ],
)
def test_a_role_refuses_a_reference_of_the_wrong_kind(role: str, wrong_ref: str) -> None:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"] = [{"requirement_id": "r1", "role": role, "ref": wrong_ref}]
    parsed = parse_grouped_flat(wire)
    assert not parsed.well_formed
    assert "wrong_reference_kind" in _codes(parsed)


@pytest.mark.parametrize(
    ("role", "valid"),
    [
        ("target_dataset", DATASET_REF),
        ("field", FIELD_REF),
        ("relationship_predicate", PREDICATE_REF),
        ("relationship_anchor_entity", ENTITY_REF),
    ],
)
def test_a_malformed_reference_is_refused_by_the_same_code_as_before(
    role: str, valid: str
) -> None:
    for malformed in (valid[:-1], valid + "0", valid[:3] + "g" * REF_DIGITS):
        wire = to_grouped_flat(_canonical())
        wire["ref_records"] = [{"requirement_id": "r1", "role": role, "ref": malformed}]
        parsed = parse_grouped_flat(wire)
        assert not parsed.well_formed
        assert "malformed_reference" in _codes(parsed)


def test_empty_required_spans_are_refused_by_the_same_code_as_before() -> None:
    wire = to_grouped_flat(_canonical(source_span=""))
    assert "missing_required_span" in _codes(parse_grouped_flat(wire))

    for detail in (
        {"requirement_id": "r1", "detail_kind": "ordering", "ref": FIELD_REF, "span": ""},
        {
            "requirement_id": "r1",
            "detail_kind": "aggregation",
            "ref": FIELD_REF,
            "span": "",
        },
        {
            "requirement_id": "r1",
            "detail_kind": "condition",
            "ref": FIELD_REF,
            "span": "",
            "value_span": "",
        },
    ):
        wire = to_grouped_flat(_canonical())
        wire["detail_records"] = [detail]
        parsed = parse_grouped_flat(wire)
        assert not parsed.well_formed
        assert "missing_required_span" in _codes(parsed)


def test_an_unknown_kind_or_status_is_refused_by_the_same_code_as_before() -> None:
    wire = to_grouped_flat(_canonical(kind="delete_everything"))
    assert "unknown_requirement_kind" in _codes(parse_grouped_flat(wire))
    wire = to_grouped_flat(_canonical(status="probably"))
    assert "unknown_requirement_status" in _codes(parse_grouped_flat(wire))


def test_no_requirement_at_all_is_still_refused() -> None:
    parsed = parse_grouped_flat({"requirement_records": []})
    assert not parsed.well_formed
    assert "empty_submission" in _codes(parsed)


def test_unknown_properties_are_refused_at_every_level() -> None:
    wire = to_grouped_flat(_canonical())
    wire["sql"] = "select 1"
    assert "unknown_property" in _codes(parse_grouped_flat(wire))

    wire = to_grouped_flat(_canonical())
    wire["requirement_records"][0]["source_table"] = "PRBD01N001"
    assert "unknown_property" in _codes(parse_grouped_flat(wire))

    wire = to_grouped_flat(_canonical())
    wire["ref_records"][0]["join"] = "inner"
    assert "unknown_property" in _codes(parse_grouped_flat(wire))


def test_a_payload_that_is_not_an_object_is_refused() -> None:
    for payload in ([], "records", 3):
        parsed = parse_grouped_flat(payload)  # type: ignore[arg-type]
        assert not parsed.well_formed
    assert not parse_grouped_flat({"requirement_records": "one"}).well_formed


# ------------------------------------------------------------------ the schema


def test_the_wire_schema_uses_only_the_accepted_keyword_vocabulary() -> None:
    assert keyword_vocabulary(grouped_flat_schema()) <= HCX_WIRE_KEYWORDS
    assert grouped_flat_schema() is not grouped_flat_schema()
    assert grouped_flat_schema() == GROUPED_FLAT_SCHEMA


def test_the_schema_and_the_assembler_name_the_same_records_and_properties() -> None:
    schema = grouped_flat_schema()
    assert set(schema["properties"]) == GROUPED_FLAT_PROPERTIES
    assert schema["required"] == ["requirement_records"]
    roles = schema["properties"]["ref_records"]["items"]["properties"]["role"]["enum"]
    details = schema["properties"]["detail_records"]["items"]["properties"][
        "detail_kind"
    ]["enum"]
    assert tuple(roles) == REF_ROLES
    assert tuple(details) == DETAIL_KINDS


def test_every_role_and_detail_kind_routes_into_a_slot_the_parser_types() -> None:
    """Reference kinds are decided by the parser's table, not by a copy of it."""
    routes = grouped_flat_slots()
    assert set(routes) == {*REF_ROLES, *DETAIL_KINDS}
    for name, slot in routes.items():
        assert slot in SLOT_KINDS, (name, slot)


def test_every_record_repeats_the_requirement_id() -> None:
    schema = grouped_flat_schema()
    for records in ("ref_records", "detail_records"):
        item = schema["properties"][records]["items"]
        assert "requirement_id" in item["properties"]
        assert "requirement_id" in item["required"]
        assert item["additionalProperties"] is False


def test_the_wire_schema_offers_no_slot_for_a_physical_plan() -> None:
    def names(node: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            found |= set(node.get("properties", {}))
            for value in node.values():
                found |= names(value)
        elif isinstance(node, list):
            for value in node:
                found |= names(value)
        return found

    found = names(grouped_flat_schema())
    assert found
    for forbidden in ("sql", "table", "column", "join", "semantic_id", "traversal", "plan"):
        assert not any(forbidden in name for name in found), forbidden

    serialised = json.dumps(grouped_flat_schema(), ensure_ascii=False).lower()
    for forbidden in ("select ", "src_", " join "):
        assert forbidden not in serialised


def test_the_tool_definition_keeps_the_logical_name_and_carries_the_wire_schema() -> None:
    tool = hcx_tool_definition()
    assert tool["type"] == "function"
    assert tool["function"]["name"] == FUNCTION_NAME == "submit_semantic_query"
    assert tool["function"]["parameters"] == grouped_flat_schema()
