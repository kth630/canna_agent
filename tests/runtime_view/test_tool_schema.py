"""The published schema and the server's parser must refuse the same things.

If they disagree, whichever the provider happens to enforce becomes the real
contract and the other becomes decoration. So every rule is checked twice: once
as a property of the schema document, and once by handing the same bad payload
to the parser.

No network call is made anywhere here. The provider adapter is exercised by
passing it to the existing tool-binding factory with a stub, which proves the
shape travels without spending a request.
"""

from __future__ import annotations

import json
import re

import pytest

from canna.runtime_view import (
    CONTRACT_STATUS,
    SUBMISSION_SCHEMA,
    hcx_tool_definition,
    hcx_wire_schema,
    parse_submission,
    tool_definition,
)
from canna.runtime_view.refs import KIND_PREFIXES, REF_DIGITS
from canna.runtime_view.schema import (
    FUNCTION_NAME,
    parser_properties,
    parser_required_spans,
    schema_properties,
    schema_ref_patterns,
    schema_required_spans,
)

DATASET_REF = f"{KIND_PREFIXES['dataset']}_" + "0" * REF_DIGITS
FIELD_REF = f"{KIND_PREFIXES['field']}_" + "1" * REF_DIGITS
PREDICATE_REF = f"{KIND_PREFIXES['predicate']}_" + "2" * REF_DIGITS
ENTITY_REF = f"{KIND_PREFIXES['entity']}_" + "3" * REF_DIGITS


def _submission(**requirement) -> dict:
    row = {
        "requirement_id": "r1",
        "kind": "listing",
        "status": "mapped",
        "source_span": "국내 ETF",
        "target_dataset_refs": [DATASET_REF],
        "field_refs": [FIELD_REF],
    }
    row.update(requirement)
    return {"requirements": [row]}


def _codes(parsed) -> set[str]:
    return {problem.code for problem in parsed.problems}


# ------------------------------------------------------------------- parity


def test_the_schema_and_the_parser_allow_the_same_properties() -> None:
    assert schema_properties() == parser_properties()


def test_the_schema_and_the_parser_require_the_same_spans() -> None:
    assert schema_required_spans() == parser_required_spans()


def test_every_reference_slot_is_typed_the_same_on_both_sides() -> None:
    patterns = schema_ref_patterns()
    assert set(patterns) == set(parser_properties()["requirement"]) - {
        "requirement_id",
        "kind",
        "status",
        "source_span",
        "limit_span",
        "conditions",
        "ordering",
        "aggregation",
        "relationship",
    } | {
        "condition.field_ref",
        "ordering.field_ref",
        "aggregation.field_ref",
        "relationship.predicate_ref",
        "relationship.anchor_entity_ref",
    }
    for slot, pattern in patterns.items():
        assert re.fullmatch(r"\^[a-z]{2}_\[0-9a-f\]\{\d+\}\$", pattern), (slot, pattern)


@pytest.mark.parametrize(
    ("slot", "reference"),
    [
        ("target_dataset_refs", DATASET_REF),
        ("field_refs", FIELD_REF),
        ("output_field_refs", FIELD_REF),
        ("grouping_field_refs", FIELD_REF),
    ],
)
def test_each_list_slot_accepts_only_its_own_reference_kind(slot, reference) -> None:
    assert parse_submission(_submission(**{slot: [reference]})).well_formed
    wrong = PREDICATE_REF if reference != PREDICATE_REF else DATASET_REF
    parsed = parse_submission(_submission(**{slot: [wrong]}))
    assert "wrong_reference_kind" in _codes(parsed)
    assert re.fullmatch(
        schema_ref_patterns()[slot].replace("^", "").replace("$", ""), reference[3:] or ""
    ) or reference.startswith(schema_ref_patterns()[slot][1:3])


def test_a_relationship_slot_rejects_a_field_reference() -> None:
    parsed = parse_submission(
        _submission(
            relationship={"predicate_ref": FIELD_REF, "anchor_entity_ref": ENTITY_REF}
        )
    )
    assert "wrong_reference_kind" in _codes(parsed)
    good = parse_submission(
        _submission(
            relationship={"predicate_ref": PREDICATE_REF, "anchor_entity_ref": ENTITY_REF}
        )
    )
    assert good.well_formed


@pytest.mark.parametrize(
    ("slot", "valid"),
    [
        ("target_dataset_refs", DATASET_REF),
        ("field_refs", FIELD_REF),
        ("relationship.predicate_ref", PREDICATE_REF),
        ("relationship.anchor_entity_ref", ENTITY_REF),
    ],
)
def test_schema_and_parser_reject_the_same_malformed_same_prefix_refs(slot, valid) -> None:
    malformed = (valid[:-1], valid + "0", valid[:3] + "g" * REF_DIGITS)
    pattern = schema_ref_patterns()[slot]
    assert re.fullmatch(pattern, valid)
    for ref in malformed:
        assert re.fullmatch(pattern, ref) is None
        if slot == "target_dataset_refs":
            payload = _submission(target_dataset_refs=[ref])
        elif slot == "field_refs":
            payload = _submission(field_refs=[ref])
        elif slot == "relationship.predicate_ref":
            payload = _submission(
                relationship={"predicate_ref": ref, "anchor_entity_ref": ENTITY_REF}
            )
        else:
            payload = _submission(
                relationship={"predicate_ref": PREDICATE_REF, "anchor_entity_ref": ref}
            )
        parsed = parse_submission(payload)
        assert not parsed.well_formed
        assert "malformed_reference" in _codes(parsed)


# --------------------------------------------------------- required span rules


def test_a_condition_without_a_comparison_or_a_value_is_refused() -> None:
    for payload in (
        {"field_ref": FIELD_REF, "value_span": "0.3%"},
        {"field_ref": FIELD_REF, "comparison_span": "이하"},
        {"field_ref": FIELD_REF, "comparison_span": "", "value_span": ""},
    ):
        parsed = parse_submission(_submission(conditions=[payload]))
        assert "missing_required_span" in _codes(parsed)
    assert parse_submission(
        _submission(
            conditions=[
                {"field_ref": FIELD_REF, "comparison_span": "이하", "value_span": "0.3%"}
            ]
        )
    ).well_formed


def test_an_ordering_without_a_direction_is_refused() -> None:
    parsed = parse_submission(_submission(ordering={"field_ref": FIELD_REF}))
    assert "missing_required_span" in _codes(parsed)
    assert parse_submission(
        _submission(ordering={"field_ref": FIELD_REF, "direction_span": "높은 순"})
    ).well_formed


def test_an_aggregation_without_a_function_is_refused() -> None:
    parsed = parse_submission(_submission(aggregation={"field_ref": FIELD_REF}))
    assert "missing_required_span" in _codes(parsed)
    assert parse_submission(
        _submission(aggregation={"field_ref": FIELD_REF, "function_span": "평균"})
    ).well_formed


def test_an_empty_source_span_is_refused_at_the_parser() -> None:
    parsed = parse_submission(_submission(source_span=""))
    assert "missing_required_span" in _codes(parsed)
    assert SUBMISSION_SCHEMA["properties"]["requirements"]["items"]["properties"][
        "source_span"
    ]["minLength"] == 1


def test_an_unknown_property_is_refused_by_both_sides() -> None:
    parsed = parse_submission(_submission(sql="select 1"))
    assert "unknown_property" in _codes(parsed)
    assert SUBMISSION_SCHEMA["properties"]["requirements"]["items"][
        "additionalProperties"
    ] is False


# ----------------------------------------------------------- schema structure


def _property_names(node) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        names |= set(node.get("properties", {}))
        for value in node.values():
            names |= _property_names(value)
    elif isinstance(node, list):
        for item in node:
            names |= _property_names(item)
    return names


def test_the_schema_is_closed_everywhere_and_names_required_fields() -> None:
    requirement = SUBMISSION_SCHEMA["properties"]["requirements"]["items"]
    assert SUBMISSION_SCHEMA["additionalProperties"] is False
    assert SUBMISSION_SCHEMA["required"] == ["requirements"]
    assert requirement["required"] == ["requirement_id", "kind", "status", "source_span"]
    for name in ("conditions", "ordering", "aggregation", "relationship"):
        nested = requirement["properties"][name]
        nested = nested["items"] if nested["type"] == "array" else nested
        assert nested["additionalProperties"] is False
        assert nested["required"]


def test_the_schema_offers_no_slot_for_a_physical_plan() -> None:
    names = _property_names(SUBMISSION_SCHEMA)
    assert names
    for forbidden in ("sql", "table", "column", "join", "semantic_id", "traversal", "plan"):
        assert not any(forbidden in name for name in names), (forbidden, sorted(names))


# ------------------------------------------------------- provider adapter shape


def test_the_hcx_adapter_carries_the_wire_encoding_not_this_schema() -> None:
    """The name is shared; the schema and its description are not.

    Until 2026-08-31 this asserted the adapter passed ``SUBMISSION_SCHEMA``
    itself, so that a wire form could not drift from the contract. The provider
    then refused that declaration three times, and the wire moved to the
    grouped-flat encoding approved as the fallback. This schema stays the
    server's contract and ``tool_definition()`` still publishes it; drift is
    prevented by ``grouped_flat`` assembling into this shape and handing it to
    the same parser, which ``test_grouped_flat.py`` holds it to.
    """
    hcx = hcx_tool_definition()
    assert hcx["type"] == "function"
    assert hcx["function"]["name"] == FUNCTION_NAME
    assert hcx["function"]["parameters"] is not SUBMISSION_SCHEMA
    assert hcx["function"]["parameters"] == hcx_wire_schema()
    # the wire description describes the wire, not the nested contract
    assert hcx["function"]["description"] != tool_definition()["description"]
    assert tool_definition()["input_schema"] is SUBMISSION_SCHEMA
    assert tool_definition()["x-contract-status"] == CONTRACT_STATUS


def test_the_adapter_reaches_the_existing_tool_binding_factory_without_a_call() -> None:
    """The probe's provider binds one tool mapping; check ours travels intact."""
    from canna.experiments.semantic_probe.provider import HcxSemanticProvider

    seen: dict[str, object] = {}

    class StubChat:
        def bind_tools(self, tools, tool_choice):
            seen["tools"] = tools
            seen["tool_choice"] = tool_choice
            return self

    def factory(model, timeout, tool_schema):
        seen["model"] = model
        seen["schema"] = tool_schema
        return StubChat().bind_tools(
            tools=[dict(tool_schema)],
            tool_choice={"type": "function", "function": {"name": FUNCTION_NAME}},
        )

    provider = HcxSemanticProvider(chat_factory=factory)
    provider._build_chat(hcx_tool_definition())

    assert seen["schema"]["function"]["name"] == FUNCTION_NAME
    assert seen["tools"][0]["function"]["parameters"]["additionalProperties"] is False
    assert seen["tool_choice"]["function"]["name"] == FUNCTION_NAME
    # nothing here touched the network
    assert json.dumps(seen["schema"])


def test_a_payload_the_schema_forbids_is_also_refused_by_the_parser() -> None:
    forbidden_payloads = [
        {"requirements": "not a list"},
        {"requirements": [], "unaccounted_spans": []},
        {"requirements": [_submission()["requirements"][0]], "extra_root": 1},
        _submission(kind="delete_everything"),
        _submission(status="probably"),
        _submission(target_dataset_refs=DATASET_REF),
    ]
    for payload in forbidden_payloads:
        parsed = parse_submission(payload)
        assert not parsed.well_formed, payload
