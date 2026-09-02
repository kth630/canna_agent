"""The envelope may be a string; what it carries is judged exactly as before.

The tool now declares one required ``submission_json`` string, because that is
the shape the provider accepted on 2026-08-31 while every grouped-flat schema
was refused. The risk that creates is specific and worth testing hard: with the
structure gone from the wire, the provider no longer rejects anything for us, so
every rule has to still be enforced on the way in.

These tests check that it is — and that it is enforced by the code that already
enforced it, not by a second copy living in the bridge. Each refusal below is
also produced by calling the existing parser directly on the same payload, so a
divergence would show up as a failing equality rather than as a quiet
difference in behaviour.

No network call is made anywhere here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from canna.runtime_view import (
    CODE_UNKNOWN_REF,
    DETAIL_KINDS,
    REF_ROLES,
    CandidateProposal,
    build_runtime_view,
    keyword_vocabulary,
    parse_grouped_flat,
    to_grouped_flat,
    validate,
)
from canna.runtime_view.contract import REQUIREMENT_KINDS, REQUIREMENT_STATUSES

# The JSON bridge is no longer the package's wire, so it is imported from its
# own module. These tests keep running because the bridge itself is unchanged:
# what moved is which envelope the runtime hands to HCX, not whether this one
# still behaves as its own tests say.
from canna.runtime_view.hcx_bridge import (
    ENVELOPE_PROPERTY,
    bridge_parameters_schema,
    envelope_diagnostics,
    parse_tool_arguments,
    submission_guidance,
)
from canna.runtime_view.hcx_wire import HCX_WIRE_KEYWORDS
from canna.runtime_view.refs import KIND_PREFIXES, REF_DIGITS
from canna.runtime_view.schema import FUNCTION_NAME
from canna.runtime_view.view import MATCH_EXACT

DATASET_REF = f"{KIND_PREFIXES['dataset']}_" + "0" * REF_DIGITS
FIELD_REF = f"{KIND_PREFIXES['field']}_" + "1" * REF_DIGITS
OTHER_FIELD_REF = f"{KIND_PREFIXES['field']}_" + "2" * REF_DIGITS
PREDICATE_REF = f"{KIND_PREFIXES['predicate']}_" + "3" * REF_DIGITS
ENTITY_REF = f"{KIND_PREFIXES['entity']}_" + "4" * REF_DIGITS


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
                {"field_ref": FIELD_REF, "comparison_span": "이상", "value_span": "3%"},
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


def _envelope(wire: Any) -> dict[str, str]:
    return {ENVELOPE_PROPERTY: json.dumps(wire, ensure_ascii=False)}


def _codes(parsed) -> set[str]:
    return {problem.code for problem in parsed.problems}


# --------------------------------------------------------------- round trip


def test_a_valid_grouped_flat_json_string_reaches_the_canonical_submission() -> None:
    wire = to_grouped_flat(RICH_CANONICAL)
    parsed = parse_tool_arguments(_envelope(wire))
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None

    direct = parse_grouped_flat(wire)
    assert direct.well_formed, direct.problems
    assert parsed.query == direct.query

    first = parsed.query.requirements[0]
    assert first.target_dataset_refs == (DATASET_REF,)
    assert first.ordering is not None
    assert (first.ordering.field_ref, first.ordering.direction_span) == (FIELD_REF, "높은")
    assert first.limit_span == "10개"
    assert [
        (c.field_ref, c.comparison_span, c.value_span) for c in first.conditions
    ] == [(FIELD_REF, "이상", "3%"), (OTHER_FIELD_REF, "이하", "0.3%")]
    assert first.relationship is not None


def test_unresolved_and_ambiguous_requirements_are_carried_not_dropped() -> None:
    parsed = parse_tool_arguments(_envelope(to_grouped_flat(RICH_CANONICAL)))
    assert parsed.query is not None
    assert [r.status for r in parsed.query.requirements] == [
        "mapped",
        "unresolved",
        "ambiguous",
    ]
    assert [r.requirement_id for r in parsed.query.requirements] == ["r1", "r2", "r3"]


# ------------------------------------------------------- the envelope itself


@pytest.mark.parametrize(
    "arguments",
    [
        {ENVELOPE_PROPERTY: "{not json"},
        {ENVELOPE_PROPERTY: ""},
        {ENVELOPE_PROPERTY: "{'single': 'quotes'}"},
    ],
)
def test_malformed_json_is_refused(arguments: dict) -> None:
    parsed = parse_tool_arguments(arguments)
    assert not parsed.well_formed
    assert parsed.query is None
    assert "malformed_submission_json" in _codes(parsed)


@pytest.mark.parametrize("payload", ["[]", "null", '"text"', "3", "true"])
def test_json_that_is_not_an_object_is_refused(payload: str) -> None:
    parsed = parse_tool_arguments({ENVELOPE_PROPERTY: payload})
    assert not parsed.well_formed
    assert parsed.query is None
    assert "submission_json_not_an_object" in _codes(parsed)


def test_a_non_string_envelope_value_is_refused() -> None:
    parsed = parse_tool_arguments({ENVELOPE_PROPERTY: {"requirement_records": []}})
    assert not parsed.well_formed
    assert "malformed_submission_json" in _codes(parsed)


def test_an_extra_tool_argument_is_refused() -> None:
    arguments = _envelope(to_grouped_flat(_canonical()))
    arguments["sql"] = "select 1"
    parsed = parse_tool_arguments(arguments)
    assert not parsed.well_formed
    assert parsed.query is None
    assert "unknown_envelope_property" in _codes(parsed)


def test_a_missing_envelope_property_is_refused() -> None:
    parsed = parse_tool_arguments({"payload": "{}"})
    assert not parsed.well_formed
    assert "unknown_envelope_property" in _codes(parsed)
    assert not parse_tool_arguments({}).well_formed


@pytest.mark.parametrize("arguments", ["a string", ["a list"], 7, None])
def test_arguments_that_are_not_an_object_are_refused(arguments: Any) -> None:
    parsed = parse_tool_arguments(arguments)
    assert not parsed.well_formed
    assert "envelope_not_an_object" in _codes(parsed)


# ------------------- everything below the envelope keeps its existing refusal


def _assert_same_as_direct(wire: Any, code: str) -> None:
    """The bridge must refuse exactly what the existing parser refuses."""
    through_bridge = parse_tool_arguments(_envelope(wire))
    direct = parse_grouped_flat(wire)
    assert not through_bridge.well_formed
    assert not direct.well_formed
    assert _codes(through_bridge) == _codes(direct)
    assert code in _codes(through_bridge)
    assert through_bridge.query == direct.query


def test_an_unknown_grouped_flat_property_is_refused_as_before() -> None:
    wire = to_grouped_flat(_canonical())
    wire["extra"] = 1
    _assert_same_as_direct(wire, "unknown_property")

    wire = to_grouped_flat(_canonical())
    wire["requirement_records"][0]["source_table"] = "PRBD01N001"
    _assert_same_as_direct(wire, "unknown_property")


@pytest.mark.parametrize(
    ("role", "wrong_ref"),
    [
        ("target_dataset", FIELD_REF),
        ("field", DATASET_REF),
        ("relationship_predicate", FIELD_REF),
        ("relationship_anchor_entity", FIELD_REF),
    ],
)
def test_a_wrong_kind_reference_is_refused_as_before(role: str, wrong_ref: str) -> None:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"] = [{"requirement_id": "r1", "role": role, "ref": wrong_ref}]
    _assert_same_as_direct(wire, "wrong_reference_kind")


def test_a_malformed_reference_is_refused_as_before() -> None:
    for malformed in (DATASET_REF[:-1], DATASET_REF + "0", DATASET_REF[:3] + "g" * REF_DIGITS):
        wire = to_grouped_flat(_canonical())
        wire["ref_records"] = [
            {"requirement_id": "r1", "role": "target_dataset", "ref": malformed}
        ]
        _assert_same_as_direct(wire, "malformed_reference")


def test_a_missing_span_is_refused_as_before() -> None:
    _assert_same_as_direct(
        to_grouped_flat(_canonical(source_span="")), "missing_required_span"
    )
    wire = to_grouped_flat(_canonical())
    wire["detail_records"] = [
        {"requirement_id": "r1", "detail_kind": "ordering", "ref": FIELD_REF, "span": ""}
    ]
    _assert_same_as_direct(wire, "missing_required_span")


def test_orphan_duplicate_and_conflicting_records_are_refused_as_before() -> None:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"].append(
        {"requirement_id": "nope", "role": "field", "ref": FIELD_REF}
    )
    _assert_same_as_direct(wire, "orphan_record")

    wire = to_grouped_flat(_canonical())
    wire["ref_records"].append(dict(wire["ref_records"][0]))
    _assert_same_as_direct(wire, "duplicate_record")

    wire = to_grouped_flat(
        _canonical(ordering={"field_ref": FIELD_REF, "direction_span": "높은"})
    )
    wire["detail_records"].append(
        {
            "requirement_id": "r1",
            "detail_kind": "ordering",
            "ref": OTHER_FIELD_REF,
            "span": "낮은",
        }
    )
    _assert_same_as_direct(wire, "conflicting_record")


def test_an_unknown_kind_or_status_is_refused_as_before() -> None:
    _assert_same_as_direct(
        to_grouped_flat(_canonical(kind="delete_everything")), "unknown_requirement_kind"
    )
    _assert_same_as_direct(
        to_grouped_flat(_canonical(status="probably")), "unknown_requirement_status"
    )


def test_no_requirement_at_all_is_refused_as_before() -> None:
    _assert_same_as_direct({"requirement_records": []}, "empty_submission")


def test_a_physical_execution_plan_cannot_be_smuggled_through_the_string() -> None:
    """A JSON string is not a way around the closed contract."""
    for smuggled in (
        {"requirement_records": [], "sql": "select 1"},
        {"requirement_records": [{**_canonical()["requirements"][0], "table": "x"}]},
        {"requirement_records": [{**_canonical()["requirements"][0], "join": "inner"}]},
    ):
        wire = to_grouped_flat(_canonical())
        wire.update(smuggled)
        through_bridge = parse_tool_arguments(_envelope(wire))
        assert not through_bridge.well_formed
        assert _codes(through_bridge) == _codes(parse_grouped_flat(wire))


# ------------------------------------------ semantic validation still decides


SYNTHETIC_QUESTION = "알파상품 중에서 알파 비용이 낮은 순으로 10개를 보여줘"


def _synthetic_wire(view) -> dict[str, Any]:
    """A submission written against a real per-request view, as records."""
    dataset_ref = view.ref_for("syn:AlphaProduct")
    field_ref = view.ref_for("syn:AlphaCost")
    assert dataset_ref and field_ref
    return {
        "requirement_records": [
            {
                "requirement_id": "s1",
                "kind": "ranking",
                "status": "mapped",
                "source_span": "알파 비용이 낮은 순으로 10개",
                "limit_span": "10개",
            }
        ],
        "ref_records": [
            {"requirement_id": "s1", "role": "target_dataset", "ref": dataset_ref}
        ],
        "detail_records": [
            {
                "requirement_id": "s1",
                "detail_kind": "ordering",
                "ref": field_ref,
                "span": "낮은 순",
            }
        ],
    }


def test_a_well_formed_submission_still_faces_the_semantic_validator(facts) -> None:
    """Parsing is not permission: the validator runs on the bridge's output."""
    view = build_runtime_view(
        facts,
        SYNTHETIC_QUESTION,
        [
            CandidateProposal("syn:AlphaProduct", MATCH_EXACT),
            CandidateProposal("syn:AlphaCost", MATCH_EXACT),
        ],
    )
    wire = _synthetic_wire(view)
    parsed = parse_tool_arguments(_envelope(wire))
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None

    direct_query = parse_grouped_flat(wire).query
    through_bridge = validate(facts, view, parsed.query)
    direct = validate(facts, view, direct_query)
    assert through_bridge.semantic_valid == direct.semantic_valid
    assert {i.code for i in through_bridge.issues} == {i.code for i in direct.issues}
    # References resolve, the spans are quoted and the direction and the count
    # canonicalise, so nothing is left to refuse. What this asserts is that the
    # bridge changes none of that: the verdict is the parser-direct verdict.
    assert through_bridge.issues == ()
    assert through_bridge.semantic_valid
    assert through_bridge.plan.requirements[0].execution_values is not None


def test_an_invented_reference_is_refused_by_the_validator(facts) -> None:
    view = build_runtime_view(
        facts,
        SYNTHETIC_QUESTION,
        [
            CandidateProposal("syn:AlphaProduct", MATCH_EXACT),
            CandidateProposal("syn:AlphaCost", MATCH_EXACT),
        ],
    )
    wire = _synthetic_wire(view)
    wire["ref_records"][0]["ref"] = DATASET_REF  # well formed, not this request's
    parsed = parse_tool_arguments(_envelope(wire))
    assert parsed.well_formed, parsed.problems
    result = validate(facts, view, parsed.query)
    assert not result.semantic_valid
    assert CODE_UNKNOWN_REF in {i.code for i in result.issues}


# --------------------------------------------------------- the declaration


def test_the_declaration_is_one_object_with_one_required_string() -> None:
    """This bridge's own declaration. What the runtime sends is now the line one.

    ``hcx_tool_definition`` is no longer asserted here: it carries the line
    notation's parameters since 2026-08-31, and the shape both bridges share —
    one object, one required string, the function name unchanged — is what this
    bridge still has to satisfy on its own.
    """
    assert FUNCTION_NAME == "submit_semantic_query"
    parameters = bridge_parameters_schema()
    assert parameters["type"] == "object"
    assert set(parameters["properties"]) == {ENVELOPE_PROPERTY}
    assert parameters["properties"][ENVELOPE_PROPERTY]["type"] == "string"
    assert parameters["required"] == [ENVELOPE_PROPERTY]
    # as plain as the declaration the provider accepted
    assert "additionalProperties" not in parameters
    assert keyword_vocabulary(parameters) <= HCX_WIRE_KEYWORDS
    assert bridge_parameters_schema() is not bridge_parameters_schema()


def test_the_guidance_names_every_field_and_enum_the_server_accepts() -> None:
    """What left the schema has to appear in the message, or the model cannot comply."""
    guidance = submission_guidance()
    for name in (
        "requirement_records",
        "ref_records",
        "detail_records",
        "unaccounted_spans",
        "requirement_id",
        "source_span",
        "limit_span",
        "span",
        "value_span",
        ENVELOPE_PROPERTY,
    ):
        assert name in guidance, name
    for value in (*REQUIREMENT_KINDS, *REQUIREMENT_STATUSES, *REF_ROLES, *DETAIL_KINDS):
        assert value in guidance, value


# ------------------------------------- the envelope's own rules are stated


def test_the_guidance_states_the_envelope_rules_the_model_got_wrong() -> None:
    """The 2026-08-31 call emitted a tool and then failed to parse.

    Whatever the envelope mistake was, the instruction now has to rule it out
    in words: a string rather than an object, a bare JSON document, and no
    second argument.
    """
    guidance = submission_guidance().lower()
    assert "must itself be a string, not a json object" in guidance
    assert "serialise the object" in guidance
    assert "code fence" in guidance
    assert "before or after it" in guidance
    assert f"no argument other than {ENVELOPE_PROPERTY}" in guidance
    assert "start with { and end with }" in guidance


def test_the_guidance_hardcodes_no_question_reference_or_family() -> None:
    guidance = submission_guidance()
    assert "ds_" not in guidance
    assert "fd_" not in guidance
    assert "ETF" not in guidance
    assert "국내" not in guidance


# ------------------------------------------------- diagnostics carry no content


def test_diagnostics_report_shape_and_never_the_payload() -> None:
    wire = to_grouped_flat(RICH_CANONICAL)
    arguments = _envelope(wire)
    parsed = parse_tool_arguments(arguments)
    diagnostics = envelope_diagnostics(arguments, parsed)

    assert diagnostics["raw_args_type"] == "dict"
    assert diagnostics["argument_keys"] == [ENVELOPE_PROPERTY]
    assert diagnostics["submission_json_value_type"] == "str"
    assert diagnostics["json_decoded"] == "yes"
    assert diagnostics["decoded_type"] == "dict"
    assert diagnostics["parser_problem_codes"] == []

    serialised = json.dumps(diagnostics, ensure_ascii=False)
    for content in (DATASET_REF, FIELD_REF, "1년 수익률이 높은 10개", "이상", "3%"):
        assert content not in serialised


@pytest.mark.parametrize(
    ("arguments", "value_type", "decoded"),
    [
        ({ENVELOPE_PROPERTY: "{not json"}, "str", "no"),
        ({ENVELOPE_PROPERTY: {"requirement_records": []}}, "dict", "not_attempted"),
        ({ENVELOPE_PROPERTY: "[]"}, "str", "yes"),
        ({"other": "x"}, "absent", "not_attempted"),
    ],
)
def test_diagnostics_name_the_stage_that_refused(
    arguments: dict, value_type: str, decoded: str
) -> None:
    parsed = parse_tool_arguments(arguments)
    diagnostics = envelope_diagnostics(arguments, parsed)
    assert diagnostics["submission_json_value_type"] == value_type
    assert diagnostics["json_decoded"] == decoded
    assert diagnostics["parser_problem_codes"] == sorted(_codes(parsed))
    assert diagnostics["argument_keys"] == sorted(arguments)


def test_diagnostics_survive_arguments_that_are_not_an_object() -> None:
    diagnostics = envelope_diagnostics("a string", parse_tool_arguments("a string"))
    assert diagnostics["raw_args_type"] == "str"
    assert diagnostics["argument_keys"] == []
    assert diagnostics["parser_problem_codes"] == ["envelope_not_an_object"]


# --------------------------------------- shape diagnostics, still not content


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            '```json\n{"requirement_records": []}\n```',
            {
                "starts_with_code_fence": True,
                "first_char_is_open_brace": False,
                "last_char_is_close_brace": False,
                "json_decoded": "no",
            },
        ),
        (
            'Here you go: {"requirement_records": []}',
            {
                "starts_with_code_fence": False,
                "first_char_is_open_brace": False,
                "last_char_is_close_brace": True,
                "json_decoded": "no",
            },
        ),
        (
            '{"requirement_records": [{"requirement_id": "r1"',
            {
                "starts_with_code_fence": False,
                "first_char_is_open_brace": True,
                "last_char_is_close_brace": False,
                "json_decoded": "no",
            },
        ),
        (
            "{'requirement_records': []}",
            {
                "starts_with_code_fence": False,
                "first_char_is_open_brace": True,
                "last_char_is_close_brace": True,
                "json_decoded": "no",
            },
        ),
    ],
)
def test_shape_diagnostics_tell_the_failure_modes_apart(
    payload: str, expected: dict
) -> None:
    """A fence, a preamble, a truncation and a quoting fault look different."""
    arguments = {ENVELOPE_PROPERTY: payload}
    diagnostics = envelope_diagnostics(arguments, parse_tool_arguments(arguments))
    for key, value in expected.items():
        assert diagnostics[key] == value, key
    assert diagnostics["length"] == len(payload)
    assert 0.0 <= diagnostics["decode_error_position_ratio"] <= 1.0
    assert diagnostics["parser_problem_codes"] == ["malformed_submission_json"]


def test_shape_diagnostics_keep_no_character_of_the_payload() -> None:
    secret = "삼성전자를 보유한 국내 ETF"
    payload = f'{{"requirement_records": [{{"source_span": "{secret}"'
    arguments = {ENVELOPE_PROPERTY: payload}
    serialised = json.dumps(
        envelope_diagnostics(arguments, parse_tool_arguments(arguments)),
        ensure_ascii=False,
    )
    assert secret not in serialised
    assert "requirement_records" not in serialised
    assert "source_span" not in serialised


def test_a_truncated_string_reads_as_a_late_failure() -> None:
    """Truncation shows as an error at the very end; a fence as one at the start."""
    complete = json.dumps({"requirement_records": []})
    truncated = {ENVELOPE_PROPERTY: complete[:-1]}
    fenced = {ENVELOPE_PROPERTY: f"```json\n{complete}\n```"}
    late = envelope_diagnostics(truncated, parse_tool_arguments(truncated))
    early = envelope_diagnostics(fenced, parse_tool_arguments(fenced))
    assert late["decode_error_position_ratio"] > early["decode_error_position_ratio"]
    assert late["first_char_is_open_brace"] is True
    assert early["starts_with_code_fence"] is True


def test_the_guidance_forbids_escaping_the_text_that_broke_the_last_call() -> None:
    r"""The 2026-08-31 failure was a malformed \uXXXX escape, not a fence.

    The string opened with a brace and carried no code fence, and the decoder
    stopped a fifth of the way in on an invalid escape. So the instruction that
    matters is not about fences any more; it is to write the characters instead
    of escaping them.
    """
    guidance = submission_guidance()
    assert "as the characters themselves" in guidance
    assert r"\u escape sequences" in guidance
    assert "ending with the closing brace" in guidance
    # still no example carrying a question, a reference or a family
    assert "ds_" not in guidance and "fd_" not in guidance


def test_a_broken_escape_is_told_apart_from_a_fence_and_a_truncation() -> None:
    r"""The three failure modes seen so far must not look alike in diagnostics."""
    complete = json.dumps({"requirement_records": []})
    cases = {
        "broken_escape": '{"requirement_records": [{"source_span": "\\u00"}]}',
        "fence": f"```json\n{complete}\n```",
        "truncation": complete[:-1],
    }
    shapes = {}
    for name, payload in cases.items():
        arguments = {ENVELOPE_PROPERTY: payload}
        shapes[name] = envelope_diagnostics(arguments, parse_tool_arguments(arguments))
        assert shapes[name]["json_decoded"] == "no"

    assert "escape" in shapes["broken_escape"]["decode_error"].lower()
    assert shapes["broken_escape"]["starts_with_code_fence"] is False
    assert shapes["broken_escape"]["first_char_is_open_brace"] is True
    assert shapes["fence"]["starts_with_code_fence"] is True
    assert "escape" not in shapes["truncation"]["decode_error"].lower()


def test_the_guidance_asks_for_a_compact_complete_document() -> None:
    """The model finished normally and still left the document open.

    It had 8192 tokens and used 269, so the remedy is not more room; it is less
    for it to keep track of while writing.
    """
    guidance = submission_guidance()
    assert "on one line, compact" in guidance
    assert "no line breaks" in guidance
    assert "Omit any property you have nothing to put in" in guidance
    assert "every brace and bracket you opened is closed" in guidance
    assert "ds_" not in guidance and "fd_" not in guidance
