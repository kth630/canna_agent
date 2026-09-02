"""One record per line: a second notation, held to the first one's decisions.

The 2026-09-01 call wrote three records on three lines and closed the document
once. This notation reads that. The question these tests ask repeatedly is the
one the multiline notation had to answer too: can anything now reach the server
that the other notations would have refused? The answer has to be no by
construction — the reader produces the grouped-flat object and hands it to the
parsers that already existed — so these tests check the notation and then check
that its refusals are the same refusals, under the same codes.

Nothing here is wired into the runtime, and no network call is made anywhere in
this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from canna.runtime_view.grouped_flat import parse_grouped_flat, to_grouped_flat
from canna.runtime_view.line_records import parse_line_submission, render_line_records
from canna.runtime_view.one_line_records import (
    ASSIGN,
    CODE_UNREPRESENTABLE_VALUE,
    END,
    RECORD_DETAIL,
    RECORD_REFERENCE,
    RECORD_REQUIREMENT,
    RECORD_TOKENS,
    RECORD_UNACCOUNTED,
    SEGMENT,
    OneLineFormatError,
    one_line_grouped_flat_record_properties,
    one_line_record_keys,
    one_line_submission_guidance,
    parse_one_line_submission,
    read_one_line_records,
    render_one_line_records,
)
from canna.runtime_view.query import Submission, parse_submission
from canna.runtime_view.refs import KIND_PREFIXES, REF_DIGITS

from .hcx_runtime_view_live_support import APPROVED_QUESTION, ROOT, SEMANTIC_REGISTRY

DATASET_REF = f"{KIND_PREFIXES['dataset']}_" + "0" * REF_DIGITS
FIELD_REF = f"{KIND_PREFIXES['field']}_" + "1" * REF_DIGITS
OTHER_FIELD_REF = f"{KIND_PREFIXES['field']}_" + "2" * REF_DIGITS
PREDICATE_REF = f"{KIND_PREFIXES['predicate']}_" + "3" * REF_DIGITS
ENTITY_REF = f"{KIND_PREFIXES['entity']}_" + "4" * REF_DIGITS

NEWLINE = chr(10)
CARRIAGE_RETURN = chr(13)
LINE_SEPARATOR = chr(0x2028)
MODULE = ROOT / "src" / "canna" / "runtime_view" / "one_line_records.py"


def _codes(parsed: Submission) -> set[str]:
    return {problem.code for problem in parsed.problems}


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
RICH_TEXT = render_one_line_records(RICH_WIRE)


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


def _rendered(**overrides: Any) -> str:
    return render_one_line_records(to_grouped_flat(_canonical(**overrides)))


def _line(token: str, **fields: str) -> str:
    """One record, written the way the notation writes it."""
    return SEGMENT.join([token, *(f"{key}{ASSIGN}{value}" for key, value in fields.items())])


REQUIREMENT_FIELDS = {
    "requirement_id": "r1",
    "kind": "listing",
    "status": "mapped",
    "source_span": "국내 ETF",
}


# ------------------------------------------------------------------ round-trip


def test_a_grouped_flat_object_survives_the_one_line_round_trip_unchanged() -> None:
    payload, problems = read_one_line_records(RICH_TEXT)
    assert problems == ()
    assert payload == RICH_WIRE


def test_one_record_is_one_line() -> None:
    lines = [line for line in RICH_TEXT.split(NEWLINE) if line]
    records = sum(len(RICH_WIRE.get(name, ())) for name in RICH_WIRE)
    assert len(lines) == records
    assert all(line.split(SEGMENT)[0] in RECORD_TOKENS for line in lines)


def test_the_notation_produces_the_same_query_as_the_multiline_and_json_paths() -> None:
    parsed = parse_one_line_submission(RICH_TEXT)
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    assert parsed.query == parse_line_submission(render_line_records(RICH_WIRE)).query
    assert parsed.query == parse_grouped_flat(RICH_WIRE).query
    assert parsed.query == parse_submission(RICH_CANONICAL).query


def test_two_conditions_keep_their_own_comparison_and_value_together() -> None:
    parsed = parse_one_line_submission(RICH_TEXT)
    assert parsed.query is not None
    conditions = parsed.query.requirements[0].conditions
    assert [(c.field_ref, c.comparison_span, c.value_span) for c in conditions] == [
        (FIELD_REF, "이상", "3%"),
        (OTHER_FIELD_REF, "이하", "0.3%"),
    ]


def test_ordering_aggregation_limit_grouping_and_relationship_are_carried() -> None:
    parsed = parse_one_line_submission(RICH_TEXT)
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


def test_every_requirement_keeps_its_kind_and_its_status() -> None:
    parsed = parse_one_line_submission(RICH_TEXT)
    assert parsed.query is not None
    requirements = parsed.query.requirements
    assert [r.requirement_id for r in requirements] == ["r1", "r2", "r3"]
    assert [r.kind for r in requirements] == ["ranking", "aggregation", "comparison"]
    # an unresolved or ambiguous requirement is carried, never dropped
    assert [r.status for r in requirements] == ["mapped", "unresolved", "ambiguous"]
    assert parsed.query.unaccounted_spans == ("설명해줘",)


# ------------------------------------------------------------- values as written


@pytest.mark.parametrize(
    "span",
    [
        "a=b",
        "=",
        "수익률=1년",
        "kind=ranking",
        "  앞뒤 공백  ",
        "총보수 0.3% 이하",
    ],
)
def test_a_value_keeps_every_character_after_its_first_equals(span: str) -> None:
    """The first ``=`` separates; nothing else is read, trimmed or normalised."""
    parsed = parse_one_line_submission(_rendered(source_span=span))
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    assert parsed.query.requirements[0].source_span == span


def test_the_separator_and_a_line_break_are_refused_rather_than_escaped() -> None:
    for span in (
        f"국내{SEGMENT}ETF",
        SEGMENT,
        f"국내{NEWLINE}ETF",
        f"국내{CARRIAGE_RETURN}ETF",
        f"국내{LINE_SEPARATOR}ETF",
    ):
        with pytest.raises(OneLineFormatError) as raised:
            _rendered(source_span=span)
        assert raised.value.code == CODE_UNREPRESENTABLE_VALUE


def test_a_value_that_is_not_text_is_refused() -> None:
    with pytest.raises(OneLineFormatError) as raised:
        _rendered(source_span=10)
    assert raised.value.code == "wrong_property_type"


def test_a_line_break_character_inside_a_document_is_refused_not_read_through() -> None:
    text = _line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS) + LINE_SEPARATOR + "x"
    payload, problems = read_one_line_records(text)
    assert payload is None
    assert {problem.code for problem in problems} == {"unsupported_line_break"}


# ------------------------------------------------------------------ the END line


def test_a_document_reads_the_same_with_or_without_a_closing_end() -> None:
    with_end = RICH_TEXT + END + NEWLINE
    assert read_one_line_records(with_end) == read_one_line_records(RICH_TEXT)
    assert parse_one_line_submission(with_end).query == parse_one_line_submission(RICH_TEXT).query


@pytest.mark.parametrize(
    "text",
    [
        NEWLINE.join([_line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS), END, END]),
        NEWLINE.join([END, _line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS)]),
        NEWLINE.join(
            [
                _line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS),
                END,
                _line(
                    RECORD_REFERENCE,
                    requirement_id="r1",
                    role="target_dataset",
                    ref=DATASET_REF,
                ),
            ]
        ),
    ],
)
def test_an_end_that_is_not_alone_at_the_end_refuses_the_document(text: str) -> None:
    payload, problems = read_one_line_records(text)
    assert payload is None
    assert {problem.code for problem in problems} == {"stray_line"}


# --------------------------------------------------- the notation's own refusals


def test_a_first_segment_nobody_defined_is_refused() -> None:
    text = NEWLINE.join(
        [
            _line("REQUIREMENT", **REQUIREMENT_FIELDS),
            _line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS),
        ]
    )
    parsed = parse_one_line_submission(text)
    assert "unknown_record" in _codes(parsed)
    assert parsed.query is not None
    assert [r.requirement_id for r in parsed.query.requirements] == ["r1"]


@pytest.mark.parametrize(
    "segment",
    ["requirement_id", f"{ASSIGN}r1", ""],
)
def test_a_segment_with_no_key_and_separator_is_refused(segment: str) -> None:
    text = _line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS) + SEGMENT + segment
    parsed = parse_one_line_submission(text)
    assert "malformed_key_line" in _codes(parsed)
    assert not parsed.well_formed


def test_a_submission_that_is_not_text_is_refused() -> None:
    payload, problems = read_one_line_records({"submission": "text"})
    assert payload is None
    assert {problem.code for problem in problems} == {"malformed_submission"}


def test_an_unaccounted_record_with_no_span_is_refused() -> None:
    text = NEWLINE.join(
        [_line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS), _line(RECORD_UNACCOUNTED, span="  ")]
    )
    parsed = parse_one_line_submission(text)
    assert "missing_required_span" in _codes(parsed)


# --------------------------------------------- the same refusals as the others


def _fault_pairs() -> dict[str, tuple[str, str]]:
    """The same fault written in both notations, so the codes can be compared."""
    requirement = dict(REQUIREMENT_FIELDS)
    reference = {"requirement_id": "r1", "role": "target_dataset", "ref": DATASET_REF}
    ordering = {
        "requirement_id": "r1",
        "detail_kind": "ordering",
        "ref": FIELD_REF,
        "span": "높은",
    }
    other_ordering = dict(ordering, span="낮은")
    missing_status = {key: value for key, value in requirement.items() if key != "status"}
    orphan = dict(reference, requirement_id="r9")

    def one_line(*records: tuple[str, dict[str, str]]) -> str:
        return NEWLINE.join(_line(token, **fields) for token, fields in records) + NEWLINE

    def multiline(*records: tuple[str, dict[str, str]]) -> str:
        lines: list[str] = []
        for token, fields in records:
            lines.append(token)
            lines += [f"{key} {value}" for key, value in fields.items()]
            lines.append(END)
        return NEWLINE.join([*lines, ""])

    cases: dict[str, tuple[tuple[str, dict[str, str]], ...]] = {
        "unknown_key": ((RECORD_REQUIREMENT, dict(requirement, colour="blue")),),
        "missing_key": ((RECORD_REQUIREMENT, missing_status),),
        "duplicate_requirement": (
            (RECORD_REQUIREMENT, requirement),
            (RECORD_REQUIREMENT, requirement),
        ),
        "orphan_record": ((RECORD_REQUIREMENT, requirement), (RECORD_REFERENCE, orphan)),
        "conflicting_record": (
            (RECORD_REQUIREMENT, requirement),
            (RECORD_REFERENCE, reference),
            (RECORD_DETAIL, ordering),
            (RECORD_DETAIL, other_ordering),
        ),
        "unknown_role": (
            (RECORD_REQUIREMENT, requirement),
            (RECORD_REFERENCE, dict(reference, role="target")),
        ),
        "unknown_detail_kind": (
            (RECORD_REQUIREMENT, requirement),
            (RECORD_REFERENCE, reference),
            (RECORD_DETAIL, dict(ordering, detail_kind="sorting")),
        ),
        "empty_submission": ((RECORD_UNACCOUNTED, {"span": "설명해줘"}),),
    }
    return {
        name: (one_line(*records), multiline(*records)) for name, records in cases.items()
    }


@pytest.mark.parametrize("name", sorted(_fault_pairs()))
def test_what_the_multiline_notation_refuses_this_notation_refuses_identically(
    name: str,
) -> None:
    one_line_text, multiline_text = _fault_pairs()[name]
    one_line = parse_one_line_submission(one_line_text)
    multiline = parse_line_submission(multiline_text)
    assert _codes(one_line) == _codes(multiline)
    assert one_line.well_formed is multiline.well_formed is False
    assert one_line.query == multiline.query


def test_a_key_repeated_inside_one_record_is_refused() -> None:
    text = _line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS) + f"{SEGMENT}requirement_id{ASSIGN}r2"
    parsed = parse_one_line_submission(text)
    assert "duplicate_record_key" in _codes(parsed)
    assert not parsed.well_formed


@pytest.mark.parametrize(
    ("ref", "code"),
    [
        # a reference of the wrong kind for the slot, and one of no kind at all
        (FIELD_REF, "wrong_reference_kind"),
        ("nope_0000000000000", "wrong_reference_kind"),
        ("", "wrong_reference_kind"),
        # the right kind, written wrongly
        ("ds_00", "malformed_reference"),
        (DATASET_REF.upper(), "wrong_reference_kind"),
        (f"{DATASET_REF} ", "malformed_reference"),
    ],
)
def test_a_wrong_kind_or_malformed_reference_keeps_its_existing_reason_code(
    ref: str, code: str
) -> None:
    """The reference rules are the parser's; this notation only carries the value."""
    records = (
        (RECORD_REQUIREMENT, dict(REQUIREMENT_FIELDS)),
        (RECORD_REFERENCE, {"requirement_id": "r1", "role": "target_dataset", "ref": ref}),
    )
    text = NEWLINE.join(_line(token, **fields) for token, fields in records)
    parsed = parse_one_line_submission(text)
    assert code in _codes(parsed)
    assert not parsed.well_formed

    multiline_lines: list[str] = []
    for token, fields in records:
        multiline_lines.append(token)
        multiline_lines += [f"{key} {value}" for key, value in fields.items()]
        multiline_lines.append(END)
    assert _codes(parsed) == _codes(parse_line_submission(NEWLINE.join(multiline_lines)))


# ------------------------------------------------ the notation carries no more


def test_the_records_accept_exactly_the_keys_grouped_flat_defines() -> None:
    keys = one_line_record_keys()
    for token, properties in one_line_grouped_flat_record_properties().items():
        assert set(keys[token]) == properties
    assert set(keys[RECORD_UNACCOUNTED]) == {"span"}


def test_no_record_offers_a_slot_for_physical_execution_detail() -> None:
    offered = {key for keys in one_line_record_keys().values() for key in keys}
    forbidden = {
        "sql",
        "table",
        "column",
        "join",
        "source_table",
        "source_column",
        "physical_table",
        "physical_column",
    }
    assert not offered & forbidden
    lowered = one_line_submission_guidance().lower()
    for word in ("select ", "src_", "join on"):
        assert word not in lowered


def test_the_guidance_states_the_servers_own_vocabulary_and_nothing_physical() -> None:
    guidance = one_line_submission_guidance()
    for token in RECORD_TOKENS:
        assert token in guidance
    for word in ("ranking", "mapped", "unresolved", "ambiguous", "condition", "ordering"):
        assert word in guidance
    assert SEGMENT in guidance
    assert APPROVED_QUESTION not in guidance


def test_the_module_names_no_question_product_or_registry_identifier() -> None:
    """No evaluation question, no product and no stable identifier in the notation."""
    source = MODULE.read_text(encoding="utf-8")
    registry = json.loads(Path(SEMANTIC_REGISTRY).read_text(encoding="utf-8"))
    identifiers = {str(term["semantic_id"]) for term in registry["terms"]}
    identifiers |= {
        str(family)
        for term in registry["terms"]
        for family in term.get("families") or ()
    }
    assert identifiers
    assert not [name for name in identifiers if name in source]
    assert APPROVED_QUESTION not in source
    for fragment in ("ETF", "수익률", "총보수"):
        assert fragment not in source


# ------------------------------------------- the actual Runtime View, offline


def test_the_approved_case_survives_the_notation_with_real_references() -> None:
    """References the request actually minted, carried as one-line records. No network."""
    from canna.runtime_view import validate

    from .hcx_runtime_view_live_support import build_approved_live_case

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
    text = render_one_line_records(wire)
    parsed = parse_one_line_submission(text)
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    requirement = parsed.query.requirements[0]
    assert requirement.target_dataset_refs == (case.expected_dataset_ref,)
    assert requirement.ordering is not None
    assert requirement.ordering.field_ref == case.expected_field_ref
    assert requirement.ordering.direction_span == "높은"
    assert requirement.limit_span == "10개"
    assert requirement.source_span == APPROVED_QUESTION

    # the server's decision is the one it already made through the other paths
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


# ----------------------------------------------------- safe shape diagnostics


def test_diagnostics_count_the_one_line_shape_without_retaining_content() -> None:
    from canna.runtime_view.one_line_records import (
        ENVELOPE_PROPERTY,
        ONE_LINE_DIAGNOSTIC_FIELDS,
        one_line_envelope_diagnostics,
        parse_tool_arguments,
    )

    unknown_record = "SECRET_TOKEN"
    unknown_key = "SECRET_KEY"
    secret_span = "SECRET_SPAN"
    text = NEWLINE.join(
        [
            _line(RECORD_REQUIREMENT, **REQUIREMENT_FIELDS),
            _line(
                RECORD_REFERENCE,
                requirement_id="r1",
                role="target_dataset",
                ref=DATASET_REF,
            ),
            _line(
                RECORD_DETAIL,
                requirement_id="r1",
                detail_kind="ordering",
                ref=FIELD_REF,
                span=secret_span,
            ),
            _line(RECORD_UNACCOUNTED, span=secret_span),
            f"{RECORD_REQUIREMENT}{SEGMENT}{unknown_key}{ASSIGN}secret",
            f"{unknown_record}{SEGMENT}secret=value",
            END,
        ]
    )
    arguments = {ENVELOPE_PROPERTY: text, "SECRET_ENVELOPE_KEY": "secret"}
    parsed = parse_tool_arguments(arguments)
    diagnostics = one_line_envelope_diagnostics(
        arguments,
        parsed,
        finish_reason="SECRET_FINISH_REASON",
        output_tokens=17,
    )

    assert set(diagnostics) <= set(ONE_LINE_DIAGNOSTIC_FIELDS)
    assert diagnostics["record_line_counts"] == {
        "REQ": 2,
        "REF": 1,
        "DETAIL": 1,
        "UNACCOUNTED": 1,
    }
    assert diagnostics["end_count"] == 1
    assert diagnostics["end_position_valid"] is True
    assert diagnostics["pipe_present"] is True
    assert diagnostics["key_value_segment_count"] == 13
    assert diagnostics["malformed_segment_count"] == 0
    assert diagnostics["unknown_record_present"] is True
    assert diagnostics["unknown_key_present"] is True
    assert diagnostics["unknown_envelope_key_present"] is True
    assert diagnostics["finish_reason"] == "other"

    serialized = json.dumps(diagnostics, ensure_ascii=False)
    for forbidden in (
        unknown_record,
        unknown_key,
        secret_span,
        "SECRET_ENVELOPE_KEY",
        "SECRET_FINISH_REASON",
        DATASET_REF,
        FIELD_REF,
        "r1",
    ):
        assert forbidden not in serialized


def test_diagnostics_distinguish_malformed_json_bullet_and_literal_backslash_n() -> None:
    from canna.runtime_view.one_line_records import (
        ENVELOPE_PROPERTY,
        one_line_envelope_diagnostics,
    )

    malformed = NEWLINE.join(
        [
            f"{RECORD_REQUIREMENT}{SEGMENT}requirement_id",
            "- bullet",
            '{"json": true}',
            r"literal\nseparator",
            END,
            "after-end",
        ]
    )
    diagnostics = one_line_envelope_diagnostics({ENVELOPE_PROPERTY: malformed})

    assert diagnostics["malformed_segment_count"] == 1
    assert diagnostics["bullet_prefixed_line_count"] == 1
    assert diagnostics["json_punctuation_present"] is True
    assert diagnostics["literal_backslash_n_present"] is True
    assert diagnostics["end_count"] == 1
    assert diagnostics["end_position_valid"] is False


def test_diagnostics_reduce_untrusted_metadata_and_problem_codes_to_fixed_enums() -> None:
    from canna.runtime_view.one_line_records import (
        ENVELOPE_PROPERTY,
        one_line_envelope_diagnostics,
    )
    from canna.runtime_view.query import ShapeProblem

    diagnostics = one_line_envelope_diagnostics(
        {ENVELOPE_PROPERTY: RICH_TEXT},
        Submission(None, (ShapeProblem("SECRET_PROBLEM_CODE", "SECRET_DETAIL"),)),
        finish_reason="SECRET_FINISH_REASON",
        output_tokens="SECRET_TOKEN_COUNT",
    )

    assert diagnostics["raw_args_type"] == "object"
    assert diagnostics["submission_text_value_type"] == "string"
    assert diagnostics["finish_reason"] == "other"
    assert diagnostics["parser_problem_codes"] == ["other"]
    assert "output_tokens" not in diagnostics
    assert "SECRET" not in json.dumps(diagnostics)
