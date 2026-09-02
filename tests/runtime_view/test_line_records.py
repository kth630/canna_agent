"""Line records are a different notation for the same object, not a looser one.

The provider takes the string envelope; what it would not take reliably was JSON
written inside it. Across the 2026-08-31 calls the model alternated between two
faults it could not satisfy at once — escaped Korean and unbalanced braces — at
three percent of the token budget either way, so the notation inside the string
changed rather than the instruction about it.

That makes one question worth asking here repeatedly: can anything now reach the
server that the JSON notation would have refused? The answer has to be no by
construction — the reader produces the grouped-flat object and hands it to the
parsers that already existed — so these tests check the notation rather than
re-checking the decisions. A submission survives the round trip byte for byte,
the faults only this notation can have are refused rather than repaired, and
every payload the JSON path rejects is rejected with the same codes here.

No network call is made anywhere in this file.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from canna.runtime_view.contract import REQUIREMENT_KINDS, REQUIREMENT_STATUSES
from canna.runtime_view.grouped_flat import (
    DETAIL_KINDS,
    REF_ROLES,
    parse_grouped_flat,
    to_grouped_flat,
)
from canna.runtime_view.line_records import (
    CLASS_COUNTS,
    CODE_DUPLICATE_KEY,
    CODE_MALFORMED_KEY_LINE,
    CODE_STRAY_LINE,
    CODE_UNKNOWN_RECORD,
    CODE_UNSUPPORTED_LINE_BREAK,
    CODE_UNTERMINATED_RECORD,
    DIAGNOSTIC_FIELDS,
    END,
    ENVELOPE_PROPERTY,
    LINE_CLASSES,
    RECORD_DETAIL,
    RECORD_REQUIREMENT,
    RECORD_TOKENS,
    RECORD_UNACCOUNTED,
    LineFormatError,
    classify_line,
    grouped_flat_record_properties,
    line_envelope_diagnostics,
    line_parameters_schema,
    line_record_keys,
    line_shape_classes,
    line_submission_guidance,
    parse_line_submission,
    parse_tool_arguments,
    read_line_records,
    render_line_records,
)
from canna.runtime_view.query import Submission, parse_submission
from canna.runtime_view.refs import KIND_PREFIXES, REF_DIGITS

DATASET_REF = f"{KIND_PREFIXES['dataset']}_" + "0" * REF_DIGITS
FIELD_REF = f"{KIND_PREFIXES['field']}_" + "1" * REF_DIGITS
OTHER_FIELD_REF = f"{KIND_PREFIXES['field']}_" + "2" * REF_DIGITS
PREDICATE_REF = f"{KIND_PREFIXES['predicate']}_" + "3" * REF_DIGITS
ENTITY_REF = f"{KIND_PREFIXES['entity']}_" + "4" * REF_DIGITS

BACKSLASH = chr(92)
CARRIAGE_RETURN = chr(13)
LINE_SEPARATOR = chr(0x2028)


def _codes(parsed: Submission) -> set[str]:
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
    "unaccounted_spans": ["설명해줘"],
}

RICH_WIRE = to_grouped_flat(RICH_CANONICAL)
RICH_TEXT = render_line_records(RICH_WIRE)


def _rendered(**overrides: Any) -> str:
    return render_line_records(to_grouped_flat(_canonical(**overrides)))


# ------------------------------------------------------------------ round-trip


def test_a_grouped_flat_object_survives_the_line_round_trip_unchanged() -> None:
    payload, problems = read_line_records(RICH_TEXT)
    assert problems == ()
    assert payload == RICH_WIRE


def test_the_line_notation_produces_the_same_query_as_the_json_notation() -> None:
    parsed = parse_line_submission(RICH_TEXT)
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    assert parsed.query == parse_grouped_flat(RICH_WIRE).query
    assert parsed.query == parse_submission(RICH_CANONICAL).query


def test_every_requirement_keeps_its_kind_and_its_status() -> None:
    parsed = parse_line_submission(RICH_TEXT)
    assert parsed.query is not None
    requirements = parsed.query.requirements
    assert [r.requirement_id for r in requirements] == ["r1", "r2", "r3"]
    assert [r.kind for r in requirements] == ["ranking", "aggregation", "comparison"]
    # an unresolved or ambiguous requirement is carried, never dropped
    assert [r.status for r in requirements] == ["mapped", "unresolved", "ambiguous"]
    assert parsed.query.unaccounted_spans == ("설명해줘",)


def test_two_conditions_keep_their_own_comparison_and_value_together() -> None:
    parsed = parse_line_submission(RICH_TEXT)
    assert parsed.query is not None
    conditions = parsed.query.requirements[0].conditions
    assert [(c.field_ref, c.comparison_span, c.value_span) for c in conditions] == [
        (FIELD_REF, "이상", "3%"),
        (OTHER_FIELD_REF, "이하", "0.3%"),
    ]


def test_ordering_aggregation_limit_and_relationship_all_survive() -> None:
    parsed = parse_line_submission(RICH_TEXT)
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


def test_the_notation_carries_no_quoting_and_nothing_to_balance() -> None:
    """The two faults that alternated cannot be expressed in what is written."""
    for character in ("{", "}", "[", "]", '"', BACKSLASH):
        assert character not in RICH_TEXT


def test_spans_are_carried_as_written_and_never_normalised() -> None:
    for span in ("이상", "이하", "높은", "평균", "3%", "0.3%", "10개"):
        assert span in RICH_TEXT
    for normalised in ("gte", "lte", "desc", "avg", "0.03"):
        assert normalised not in RICH_TEXT


@pytest.mark.parametrize(
    "span",
    [
        "1년  수익률",  # a doubled space the reader must not collapse
        " 앞뒤 공백 ",  # leading and trailing space
        "괄호 { } 와 대괄호 [ ]",  # characters JSON would have had to balance
        f'따옴표 " 와 역슬래시 {BACKSLASH}',  # characters JSON would have had to escape
        END,  # a span that reads exactly like a terminator
        f"{RECORD_REQUIREMENT} {END}",  # and one that reads like two structural lines
        "\t들여쓴 값",
    ],
)
def test_a_span_reaches_the_server_exactly_as_it_was_written(span: str) -> None:
    """Delimiter collision cannot alter a value: the key ends at the first space."""
    parsed = parse_line_submission(_rendered(source_span=span))
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    assert parsed.query.requirements[0].source_span == span


def test_carriage_return_line_endings_are_read_as_line_endings() -> None:
    payload, problems = read_line_records(RICH_TEXT.replace("\n", CARRIAGE_RETURN + "\n"))
    assert problems == ()
    assert payload == RICH_WIRE


def test_blank_lines_between_records_carry_nothing_and_change_nothing() -> None:
    payload, problems = read_line_records(RICH_TEXT.replace("\n" + END, "\n" + END + "\n\n"))
    assert problems == ()
    assert payload == RICH_WIRE


def test_trailing_whitespace_on_a_structural_line_is_not_a_value() -> None:
    spaced = RICH_TEXT.replace(END + "\n", END + "  \n").replace(
        RECORD_DETAIL + "\n", RECORD_DETAIL + " \n"
    )
    payload, problems = read_line_records(spaced)
    assert problems == ()
    assert payload == RICH_WIRE


def test_records_may_arrive_in_any_order_including_before_their_requirement() -> None:
    """A model writing one block per requirement is read the same way."""
    interleaved = (
        f"{RECORD_REQUIREMENT}\nrequirement_id r1\nkind listing\nstatus mapped\n"
        f"source_span 국내 ETF\n{END}\n"
        f"REF\nrequirement_id r1\nrole target_dataset\nref {DATASET_REF}\n{END}\n"
        f"REF\nrequirement_id r2\nrole target_dataset\nref {DATASET_REF}\n{END}\n"
        f"{RECORD_REQUIREMENT}\nrequirement_id r2\nkind count\nstatus mapped\n"
        f"source_span 몇 개\n{END}\n"
    )
    parsed = parse_line_submission(interleaved)
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    assert [r.requirement_id for r in parsed.query.requirements] == ["r1", "r2"]
    assert all(r.target_dataset_refs == (DATASET_REF,) for r in parsed.query.requirements)


def test_the_keys_of_a_record_may_arrive_in_any_order() -> None:
    reordered = (
        f"{RECORD_REQUIREMENT}\nsource_span 국내 ETF\nstatus mapped\nkind listing\n"
        f"requirement_id r1\n{END}\n"
    )
    parsed = parse_line_submission(reordered)
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    assert parsed.query.requirements[0].source_span == "국내 ETF"


# ------------------------------------------------- the notation's own refusals


def test_a_line_that_is_not_a_record_header_is_refused() -> None:
    parsed = parse_line_submission("여기 결과입니다\n" + RICH_TEXT)
    assert not parsed.well_formed
    assert CODE_UNKNOWN_RECORD in _codes(parsed)


def test_an_undefined_record_name_is_refused() -> None:
    parsed = parse_line_submission(RICH_TEXT + "TABLE\nname products\nEND\n")
    assert not parsed.well_formed
    assert CODE_UNKNOWN_RECORD in _codes(parsed)


def test_an_end_that_closes_nothing_is_refused() -> None:
    parsed = parse_line_submission(RICH_TEXT + END + "\n")
    assert not parsed.well_formed
    assert CODE_STRAY_LINE in _codes(parsed)


def test_a_record_that_is_never_closed_is_refused() -> None:
    truncated = RICH_TEXT[: RICH_TEXT.rindex(END + "\n")]
    payload, problems = read_line_records(truncated)
    assert payload is None
    assert {problem.code for problem in problems} == {CODE_UNTERMINATED_RECORD}
    assert not parse_line_submission(truncated).well_formed


def test_a_new_record_opening_inside_an_open_one_is_refused() -> None:
    """A missing END is a boundary fault, so nothing after it is trusted."""
    text = (
        f"{RECORD_REQUIREMENT}\nrequirement_id r1\n"
        f"{RECORD_REQUIREMENT}\nrequirement_id r2\n{END}\n"
    )
    payload, problems = read_line_records(text)
    assert payload is None
    assert {problem.code for problem in problems} == {CODE_UNTERMINATED_RECORD}


def test_a_key_no_record_defines_is_refused() -> None:
    parsed = parse_line_submission(
        _rendered().replace("kind listing\n", "kind listing\ntable products\n")
    )
    assert not parsed.well_formed
    assert "unknown_property" in _codes(parsed)


def test_a_repeated_key_inside_one_record_is_refused_rather_than_overwritten() -> None:
    parsed = parse_line_submission(
        _rendered().replace("kind listing\n", "kind listing\nkind ranking\n")
    )
    assert not parsed.well_formed
    assert CODE_DUPLICATE_KEY in _codes(parsed)


def test_a_line_that_begins_with_no_key_is_refused() -> None:
    parsed = parse_line_submission(_rendered().replace("kind listing\n", " kind listing\n"))
    assert not parsed.well_formed
    assert CODE_MALFORMED_KEY_LINE in _codes(parsed)


@pytest.mark.parametrize("character", [CARRIAGE_RETURN, LINE_SEPARATOR, "\v", "\f", "\x85"])
def test_any_other_line_break_character_is_refused_rather_than_read_through(
    character: str,
) -> None:
    text = _rendered().replace("source_span 국내 ETF", f"source_span 국내{character}ETF")
    payload, problems = read_line_records(text)
    assert payload is None
    assert {problem.code for problem in problems} == {CODE_UNSUPPORTED_LINE_BREAK}


def test_a_submission_that_is_not_text_is_refused() -> None:
    for value in (None, 3, {"requirement_records": []}, [RECORD_REQUIREMENT]):
        payload, problems = read_line_records(value)
        assert payload is None
        assert {problem.code for problem in problems} == {"malformed_submission"}


@pytest.mark.parametrize(
    "text",
    [
        f"{RECORD_UNACCOUNTED}\n{END}\n",
        f"{RECORD_UNACCOUNTED}\nspan \n{END}\n",
        f"{RECORD_UNACCOUNTED}\nspan    \n{END}\n",
    ],
)
def test_an_unaccounted_record_with_no_span_is_refused(text: str) -> None:
    """The one record with no object of its own still cannot arrive empty."""
    parsed = parse_line_submission(_rendered() + text)
    assert not parsed.well_formed
    assert "missing_required_span" in _codes(parsed)


# ------------------------------- the same refusals as the JSON notation's path


def _wrong_kind_ref() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"][1]["ref"] = PREDICATE_REF
    return wire


def _malformed_ref() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"][1]["ref"] = f"{KIND_PREFIXES['field']}_beef"
    return wire


def _empty_source_span() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["requirement_records"][0]["source_span"] = ""
    return wire


def _unknown_kind() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["requirement_records"][0]["kind"] = "physical_scan"
    return wire


def _unknown_status() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["requirement_records"][0]["status"] = "probably"
    return wire


def _orphan_reference() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"].append(
        {"requirement_id": "nobody", "role": "field", "ref": OTHER_FIELD_REF}
    )
    return wire


def _reference_without_an_owner() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"].append({"role": "field", "ref": OTHER_FIELD_REF})
    return wire


def _duplicate_requirement() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["requirement_records"].append(dict(wire["requirement_records"][0]))
    return wire


def _duplicate_reference() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"].append(dict(wire["ref_records"][0]))
    return wire


def _conflicting_ordering() -> dict[str, Any]:
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
    return wire


def _unknown_role() -> dict[str, Any]:
    wire = to_grouped_flat(_canonical())
    wire["ref_records"][0]["role"] = "physical_table"
    return wire


def _unknown_detail_kind() -> dict[str, Any]:
    wire = to_grouped_flat(
        _canonical(ordering={"field_ref": FIELD_REF, "direction_span": "높은"})
    )
    wire["detail_records"][0]["detail_kind"] = "join"
    return wire


def _value_span_outside_a_condition() -> dict[str, Any]:
    wire = to_grouped_flat(
        _canonical(ordering={"field_ref": FIELD_REF, "direction_span": "높은"})
    )
    wire["detail_records"][0]["value_span"] = "10"
    return wire


def _no_requirements() -> dict[str, Any]:
    return {"requirement_records": []}


@pytest.mark.parametrize(
    ("name", "build"),
    [
        ("wrong reference kind", _wrong_kind_ref),
        ("malformed reference", _malformed_ref),
        ("empty required span", _empty_source_span),
        ("unknown requirement kind", _unknown_kind),
        ("unknown requirement status", _unknown_status),
        ("orphan reference", _orphan_reference),
        ("reference with no owner", _reference_without_an_owner),
        ("duplicate requirement", _duplicate_requirement),
        ("duplicate reference", _duplicate_reference),
        ("conflicting ordering", _conflicting_ordering),
        ("unknown role", _unknown_role),
        ("unknown detail kind", _unknown_detail_kind),
        ("value span outside a condition", _value_span_outside_a_condition),
        ("no requirement at all", _no_requirements),
    ],
)
def test_what_the_json_notation_refuses_the_line_notation_refuses_identically(
    name: str, build: Callable[[], dict[str, Any]]
) -> None:
    wire = build()
    through_json = parse_grouped_flat(wire)
    through_lines = parse_line_submission(render_line_records(wire))
    assert not through_json.well_formed, name
    assert _codes(through_lines) == _codes(through_json), name
    assert through_lines.query == through_json.query, name


# ------------------------------------------------------- writing, or refusing


@pytest.mark.parametrize(
    "span",
    ["두 줄\n짜리", f"복귀{CARRIAGE_RETURN}문자", f"구분자{LINE_SEPARATOR}포함"],
)
def test_a_span_holding_a_line_break_is_refused_not_flattened(span: str) -> None:
    wire = to_grouped_flat(_canonical(source_span=span))
    with pytest.raises(LineFormatError):
        render_line_records(wire)


def test_a_value_that_is_not_text_is_refused() -> None:
    wire = to_grouped_flat(_canonical())
    wire["requirement_records"][0]["limit_span"] = 10
    with pytest.raises(LineFormatError):
        render_line_records(wire)


def test_a_record_or_payload_property_nobody_defined_is_refused() -> None:
    wire = to_grouped_flat(_canonical())
    wire["requirement_records"][0]["table"] = "products"
    with pytest.raises(LineFormatError):
        render_line_records(wire)
    with pytest.raises(LineFormatError):
        render_line_records({"requirement_records": [], "sql": "select 1"})


# --------------------------------------------------------- vocabulary parity


def test_the_records_accept_exactly_the_keys_grouped_flat_defines() -> None:
    """The key vocabulary is that module's property table, not a copy of it."""
    keys = line_record_keys()
    for token, properties in grouped_flat_record_properties().items():
        assert set(keys[token]) == properties, token
        assert len(keys[token]) == len(set(keys[token])), token
    assert set(keys[RECORD_UNACCOUNTED]) == {"span"}
    assert set(keys) == set(RECORD_TOKENS)


def test_no_record_offers_a_slot_for_physical_execution_detail() -> None:
    every_key = {key for keys in line_record_keys().values() for key in keys}
    for forbidden in ("table", "column", "sql", "join", "select", "product_id", "id"):
        assert forbidden not in every_key


def test_the_guidance_states_the_servers_own_vocabulary_and_nothing_physical() -> None:
    guidance = line_submission_guidance()
    for token in (*RECORD_TOKENS, END):
        assert token in guidance
    for value in (*REQUIREMENT_KINDS, *REQUIREMENT_STATUSES, *REF_ROLES, *DETAIL_KINDS):
        assert value in guidance
    for key in {key for keys in line_record_keys().values() for key in keys}:
        assert key in guidance
    # the instruction must not model the notation it is replacing
    for character in ("{", "}", "[", "]", BACKSLASH):
        assert character not in guidance
    assert "SQL, tables, columns, joins, stable identifiers" in guidance


# ------------------------------------------------------------------ envelope


def test_the_declaration_is_one_object_with_one_required_string() -> None:
    schema = line_parameters_schema()
    assert schema["required"] == [ENVELOPE_PROPERTY]
    assert schema["properties"][ENVELOPE_PROPERTY]["type"] == "string"
    assert "enum" not in repr(schema)
    assert "additionalProperties" not in schema
    assert schema is not line_parameters_schema()


def test_the_envelope_carries_the_text_and_nothing_else() -> None:
    parsed = parse_tool_arguments({ENVELOPE_PROPERTY: RICH_TEXT})
    assert parsed.well_formed, parsed.problems
    assert parsed.query == parse_submission(RICH_CANONICAL).query

    assert _codes(parse_tool_arguments([ENVELOPE_PROPERTY])) == {"envelope_not_an_object"}
    assert _codes(
        parse_tool_arguments({ENVELOPE_PROPERTY: RICH_TEXT, "note": "설명"})
    ) == {"unknown_envelope_property"}
    assert _codes(parse_tool_arguments({ENVELOPE_PROPERTY: RICH_WIRE})) == {
        "wrong_property_type"
    }
    assert _codes(parse_tool_arguments({"submission": RICH_TEXT})) == {
        "unknown_envelope_property"
    }


# ------------------------------------------- diagnostics carry no content


def test_diagnostics_report_shape_and_never_the_payload() -> None:
    arguments = {ENVELOPE_PROPERTY: RICH_TEXT}
    parsed = parse_tool_arguments(arguments)
    diagnostics = line_envelope_diagnostics(arguments, parsed)

    assert diagnostics["raw_args_type"] == "dict"
    assert diagnostics["argument_keys"] == [ENVELOPE_PROPERTY]
    assert diagnostics["submission_text_value_type"] == "str"
    assert diagnostics["first_line_is_record_header"] is True
    assert diagnostics["last_line_is_end"] is True
    assert diagnostics["starts_with_code_fence"] is False
    assert diagnostics["record_counts"] == {
        RECORD_REQUIREMENT: 3,
        "REF": 8,
        RECORD_DETAIL: 4,
        RECORD_UNACCOUNTED: 1,
    }
    assert diagnostics["parser_problem_codes"] == []

    serialised = json.dumps(diagnostics, ensure_ascii=False)
    for content in (
        DATASET_REF,
        FIELD_REF,
        PREDICATE_REF,
        ENTITY_REF,
        "1년 수익률이 높은 10개",
        "이상",
        "3%",
        "설명해줘",
    ):
        assert content not in serialised


def test_diagnostics_record_nothing_outside_the_approved_list() -> None:
    for arguments in (
        {ENVELOPE_PROPERTY: RICH_TEXT},
        {ENVELOPE_PROPERTY: RICH_WIRE},
        {"other": "x"},
        "a string",
    ):
        diagnostics = line_envelope_diagnostics(
            arguments,
            parse_tool_arguments(arguments),
            finish_reason="tool_calls",
            output_tokens=218,
        )
        assert set(diagnostics) <= set(DIAGNOSTIC_FIELDS)


@pytest.mark.parametrize(
    ("arguments", "value_type", "codes"),
    [
        ({ENVELOPE_PROPERTY: RICH_TEXT}, "str", []),
        ({ENVELOPE_PROPERTY: RICH_WIRE}, "dict", ["wrong_property_type"]),
        ({"other": "x"}, "absent", ["unknown_envelope_property"]),
        ({ENVELOPE_PROPERTY: "설명입니다"}, "str", ["empty_submission", "unknown_record"]),
    ],
)
def test_diagnostics_name_the_stage_that_refused(
    arguments: Any, value_type: str, codes: list[str]
) -> None:
    parsed = parse_tool_arguments(arguments)
    diagnostics = line_envelope_diagnostics(arguments, parsed)
    assert diagnostics["submission_text_value_type"] == value_type
    assert diagnostics["parser_problem_codes"] == codes
    assert diagnostics["argument_keys"] == sorted(arguments)


def test_diagnostics_tell_a_fence_from_a_truncation_without_reading_either() -> None:
    fenced = line_envelope_diagnostics({ENVELOPE_PROPERTY: "```\n" + RICH_TEXT + "```"})
    assert fenced["starts_with_code_fence"] is True
    assert fenced["first_line_is_record_header"] is False

    truncated_text = RICH_TEXT[: RICH_TEXT.rindex(END + "\n")]
    truncated = line_envelope_diagnostics(
        {ENVELOPE_PROPERTY: truncated_text},
        parse_tool_arguments({ENVELOPE_PROPERTY: truncated_text}),
    )
    assert truncated["first_line_is_record_header"] is True
    assert truncated["last_line_is_end"] is False
    assert truncated["parser_problem_codes"] == [CODE_UNTERMINATED_RECORD]
    assert truncated["length"] < len(RICH_TEXT)


def test_response_metadata_is_carried_only_when_the_caller_has_it() -> None:
    arguments = {ENVELOPE_PROPERTY: RICH_TEXT}
    assert "finish_reason" not in line_envelope_diagnostics(arguments)
    assert "output_tokens" not in line_envelope_diagnostics(arguments)
    with_response = line_envelope_diagnostics(
        arguments, finish_reason="tool_calls", output_tokens=218
    )
    assert with_response["finish_reason"] == "tool_calls"
    assert with_response["output_tokens"] == 218


def test_diagnostics_survive_arguments_that_are_not_an_object() -> None:
    diagnostics = line_envelope_diagnostics("a string", parse_tool_arguments("a string"))
    assert diagnostics["raw_args_type"] == "str"
    assert diagnostics["argument_keys"] == []
    assert diagnostics["parser_problem_codes"] == ["envelope_not_an_object"]


# ---------------------------- which malformation, told apart without content

# The 13th live call refused with ``empty_submission``, ``stray_line`` and
# ``unknown_record`` — the codes a header nobody opened produces, and the same
# codes for several different ways of not opening one. The documents below are
# those ways. Each test asserts that the shape classes separate them while the
# parser codes do not, so the next call can say which one arrived without the
# record holding a character of it.

NEWLINE = chr(10)
SHAPE_SPAN = "1년 수익률이 높은 10개"
UNKNOWN_TOKEN = "REQUIREMENTS_BLOCK"
INVENTED_REF = "zz_999999"

COLON_HEADER = NEWLINE.join([f"{RECORD_REQUIREMENT}:", "requirement_id r1", END])
INLINE_HEADER = NEWLINE.join([f"{RECORD_REQUIREMENT} requirement_id r1", END])
INDENTED_HEADER = NEWLINE.join(
    [f"  {RECORD_REQUIREMENT}", "  requirement_id r1", f"  {END}"]
)
COLON_KEYS = NEWLINE.join([RECORD_REQUIREMENT, "requirement_id: r1", END])
BULLETED = NEWLINE.join(
    [f"- {RECORD_REQUIREMENT}", "- requirement_id r1", f"- {END}"]
)
LITERAL_NEWLINES = (BACKSLASH + "n").join([RECORD_REQUIREMENT, "requirement_id r1", END])
JSON_SHAPED = NEWLINE.join(
    ["{", '  "requirement_records": [', '    {"requirement_id": "r1"}', "  ]", "}"]
)

SHAPE_CASES: dict[str, str] = {
    "colon_header": COLON_HEADER,
    "inline_header": INLINE_HEADER,
    "indented_header": INDENTED_HEADER,
    "colon_keys": COLON_KEYS,
    "bulleted": BULLETED,
    "literal_newlines": LITERAL_NEWLINES,
    "json_shaped": JSON_SHAPED,
    "well_formed": RICH_TEXT,
}


def _shape(text: str) -> dict[str, Any]:
    """Only the shape classes, read back out of the diagnostics the live run keeps."""
    arguments = {ENVELOPE_PROPERTY: text}
    diagnostics = line_envelope_diagnostics(arguments, parse_tool_arguments(arguments))
    names = (
        *CLASS_COUNTS.values(),
        "literal_backslash_n_present",
        "json_punctuation_present",
        "first_line_class",
        "last_line_class",
    )
    return {name: diagnostics[name] for name in names}


def test_a_header_written_with_a_colon_is_named_as_one() -> None:
    shape = _shape(COLON_HEADER)
    assert shape["record_header_with_suffix_count"] == 1
    assert shape["exact_record_header_count"] == 0
    assert shape["first_line_class"] == "record_header_with_suffix"
    assert shape["known_key_space_count"] == 1
    assert shape["exact_end_count"] == 1


def test_a_header_carrying_its_first_field_is_told_from_a_header_with_a_colon() -> None:
    shape = _shape(INLINE_HEADER)
    assert shape["record_header_with_suffix_count"] == 1
    assert shape["exact_record_header_count"] == 0
    # the field rode along on the header line, so no key line arrived at all,
    # which is what separates this from the header written with a colon
    assert shape["known_key_space_count"] == 0
    assert shape != _shape(COLON_HEADER)


def test_an_indented_header_is_told_from_one_at_the_margin() -> None:
    shape = _shape(INDENTED_HEADER)
    assert shape["indented_record_header_count"] == 1
    assert shape["exact_record_header_count"] == 0
    assert shape["indented_end_count"] == 1
    assert shape["exact_end_count"] == 0
    assert shape["first_line_class"] == "indented_record_header"
    assert shape["last_line_class"] == "indented_end"


def test_a_key_written_with_a_colon_is_told_from_one_written_with_a_space() -> None:
    shape = _shape(COLON_KEYS)
    assert shape["known_key_colon_count"] == 1
    assert shape["known_key_space_count"] == 0
    # the headers were right here; only the key lines were not
    assert shape["exact_record_header_count"] == 1
    assert shape["exact_end_count"] == 1


def test_a_bulleted_document_is_named_by_its_bullets() -> None:
    shape = _shape(BULLETED)
    assert shape["bullet_prefixed_line_count"] == 3
    assert shape["exact_record_header_count"] == 0
    assert shape["known_key_space_count"] == 0
    assert shape["first_line_class"] == "bullet_prefixed"
    assert shape["last_line_class"] == "bullet_prefixed"


@pytest.mark.parametrize(
    ("text", "present"),
    [(LITERAL_NEWLINES, True), (RICH_TEXT, False), (COLON_HEADER, False)],
)
def test_line_breaks_written_as_two_characters_are_reported_as_such(
    text: str, present: bool
) -> None:
    assert _shape(text)["literal_backslash_n_present"] is present
    if present:
        assert _shape(text)["exact_end_count"] == 0


def test_a_document_that_stayed_json_is_named_by_its_punctuation() -> None:
    shape = _shape(JSON_SHAPED)
    assert shape["json_punctuation_present"] is True
    assert shape["first_line_class"] == "json_punctuation"
    assert shape["exact_record_header_count"] == 0
    assert shape["known_key_space_count"] == 0
    assert _shape(RICH_TEXT)["json_punctuation_present"] is False


def test_a_well_formed_document_is_exact_headers_key_lines_and_ends() -> None:
    shape = _shape(RICH_TEXT)
    records = sum(
        RICH_TEXT.count(NEWLINE + token + NEWLINE) + RICH_TEXT.startswith(token + NEWLINE)
        for token in RECORD_TOKENS
    )
    assert shape["exact_record_header_count"] == records
    assert shape["exact_end_count"] == records
    assert shape["known_key_space_count"] > 0
    assert shape["first_line_class"] == "exact_record_header"
    assert shape["last_line_class"] == "exact_end"
    for counter in (
        "casefold_record_header_count",
        "indented_record_header_count",
        "record_header_with_suffix_count",
        "indented_end_count",
        "known_key_colon_count",
        "bullet_prefixed_line_count",
        "unknown_nonempty_line_count",
    ):
        assert shape[counter] == 0


def test_a_lowercase_header_is_named_rather_than_read_as_an_unknown_line() -> None:
    lowercased = NEWLINE.join(
        [RECORD_REQUIREMENT.lower(), "requirement_id r1", END.lower()]
    )
    shape = _shape(lowercased)
    assert shape["casefold_record_header_count"] == 1
    assert shape["exact_record_header_count"] == 0
    assert shape["unknown_nonempty_line_count"] == 1


def test_the_parser_codes_do_not_separate_these_documents_but_the_shapes_do() -> None:
    """Why this exists: several of them refuse identically and are not one fault."""
    codes = {
        name: tuple(
            line_envelope_diagnostics(
                {ENVELOPE_PROPERTY: text},
                parse_tool_arguments({ENVELOPE_PROPERTY: text}),
            )["parser_problem_codes"]
        )
        for name, text in SHAPE_CASES.items()
    }
    assert len(set(codes.values())) < len(codes)

    shapes = [
        json.dumps(_shape(text), ensure_ascii=False) for text in SHAPE_CASES.values()
    ]
    assert len(set(shapes)) == len(SHAPE_CASES)


def test_the_shape_classes_are_a_fixed_vocabulary_inside_the_approved_list() -> None:
    assert set(CLASS_COUNTS) <= set(LINE_CLASSES)
    assert set(CLASS_COUNTS.values()) <= set(DIAGNOSTIC_FIELDS)
    for name in (
        "literal_backslash_n_present",
        "json_punctuation_present",
        "first_line_class",
        "last_line_class",
    ):
        assert name in DIAGNOSTIC_FIELDS
    for text in (*SHAPE_CASES.values(), "", "   ", SHAPE_SPAN):
        assert {classify_line(line) for line in text.split(NEWLINE)} <= set(LINE_CLASSES)
        shape = line_shape_classes(text)
        assert shape["first_line_class"] in LINE_CLASSES
        assert shape["last_line_class"] in LINE_CLASSES
    assert line_shape_classes("")["first_line_class"] == "absent"
    assert line_shape_classes(NEWLINE * 2)["last_line_class"] == "absent"


def test_no_reference_span_identifier_or_unknown_token_reaches_the_diagnostics() -> None:
    """The classes name shapes this module decided on, never anything it read."""
    texts = (
        RICH_TEXT,
        NEWLINE.join(
            [UNKNOWN_TOKEN, f"source_span {SHAPE_SPAN}", f"ref {INVENTED_REF}", END]
        ),
        NEWLINE.join([RECORD_REQUIREMENT, f"source_span {SHAPE_SPAN}", END]),
        NEWLINE.join([RECORD_DETAIL, f"ref {DATASET_REF}", "span 이상", END]),
        JSON_SHAPED,
    )
    for text in texts:
        arguments = {ENVELOPE_PROPERTY: text}
        diagnostics = line_envelope_diagnostics(
            arguments, parse_tool_arguments(arguments), finish_reason="tool_calls"
        )
        assert set(diagnostics) <= set(DIAGNOSTIC_FIELDS)
        serialised = json.dumps(diagnostics, ensure_ascii=False)
        for content in (
            DATASET_REF,
            FIELD_REF,
            PREDICATE_REF,
            ENTITY_REF,
            INVENTED_REF,
            UNKNOWN_TOKEN,
            UNKNOWN_TOKEN.casefold(),
            SHAPE_SPAN,
            "이상",
            "3%",
            "설명해줘",
            "r1",
        ):
            assert content not in serialised


# ------------------------------------------- the actual Runtime View, offline


def test_the_approved_case_survives_the_notation_with_real_references() -> None:
    """References the request actually minted, carried as lines. No network."""
    from canna.runtime_view import validate

    from .hcx_runtime_view_live_support import APPROVED_QUESTION, build_approved_live_case

    case = build_approved_live_case()
    wire = {
        "requirement_records": [
            {
                "requirement_id": "a1",
                "kind": "ranking",
                "status": "mapped",
                "source_span": APPROVED_QUESTION,
                "limit_span": "10개",
            }
        ],
        "ref_records": [
            {
                "requirement_id": "a1",
                "role": "target_dataset",
                "ref": case.expected_dataset_ref,
            }
        ],
        "detail_records": [
            {
                "requirement_id": "a1",
                "detail_kind": "ordering",
                "ref": case.expected_field_ref,
                "span": "높은",
            }
        ],
    }
    text = render_line_records(wire)
    parsed = parse_tool_arguments({ENVELOPE_PROPERTY: text})
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    requirement = parsed.query.requirements[0]
    assert requirement.target_dataset_refs == (case.expected_dataset_ref,)
    assert requirement.ordering is not None
    assert requirement.ordering.field_ref == case.expected_field_ref
    assert requirement.ordering.direction_span == "높은"
    assert requirement.limit_span == "10개"
    assert requirement.source_span == APPROVED_QUESTION

    # the server's decision is the one it already made through the JSON path
    result = validate(case.facts, case.view, parsed.query)
    assert result.issues == ()
    assert result.semantic_valid
    values = result.plan.requirements[0].execution_values
    assert values is not None
    assert (values.ordering.direction, values.limit.limit) == ("desc", 10)

    lowered = text.lower()
    for term in case.facts.terms:
        assert term.semantic_id.lower() not in lowered
    for forbidden in ("sql", "table", "column", "join", "src_", "select "):
        assert forbidden not in lowered
