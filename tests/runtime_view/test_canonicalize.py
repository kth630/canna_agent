"""The four canonicalisers, tested as grammar rather than as remembered questions.

No test here asserts anything about a product family, a measure or a question
anyone expects to be asked. Field metadata is synthesised from unit codes and
operation codes the ontology declares, so a rule that only held for today's
Registry would not pass; the tests that do read the real Registry ask it to
enumerate its own units and operations and then assert the rule on all of them.

The lexicons are tested against themselves. Every form declared in a table is
fed back in and has to return the meaning the table claims, which is how a form
silently shadowed by a longer one — "<" inside "<=", "최대" inside "최댓값" —
is caught rather than discovered later in a wrong answer.

Every refusal is asserted by code, not merely by "not ok". A canonicaliser that
refused everything for one reason would pass a weaker test and would be useless.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from canna.runtime_view.canonicalize import (
    AGGREGATION_FORMS,
    AGGREGATION_FUNCTIONS,
    AGGREGATION_OPERATIONS,
    CODE_AGGREGATION_AMBIGUOUS,
    CODE_AGGREGATION_UNSUPPORTED,
    CODE_COMPARISON_AMBIGUOUS,
    CODE_COMPARISON_UNSUPPORTED,
    CODE_DIRECTION_AMBIGUOUS,
    CODE_DIRECTION_UNSUPPORTED,
    CODE_FIELD_METADATA_UNAVAILABLE,
    CODE_LIMIT_AMBIGUOUS,
    CODE_LIMIT_IS_PROPORTION,
    CODE_LIMIT_NOT_POSITIVE,
    CODE_LIMIT_UNSUPPORTED,
    CODE_NEGATED,
    CODE_OPERATION_NOT_ALLOWED,
    CODE_UNIT_NOT_CANONICALIZABLE,
    CODE_VALUE_UNIT_MISMATCH,
    CODE_VALUE_UNSUPPORTED,
    COMPARISON_FORMS,
    COMPARISON_OPERATORS,
    DIRECTION_ASC,
    DIRECTION_DESC,
    DIRECTION_FORMS,
    IMPLEMENTED_CANONICALIZERS,
    OPERATION_AGGREGATE,
    OPERATION_COUNT,
    OPERATION_FILTER,
    OPERATION_ORDER,
    UNIT_COUNT,
    UNIT_CURRENCY_AMOUNT,
    UNIT_NONE,
    UNIT_NUMBER,
    UNIT_PERCENT_OBSERVED,
    UNIT_PRICE,
    UNIT_PROFILES,
    FieldMetadata,
    canonicalize_aggregation,
    canonicalize_comparison,
    canonicalize_direction,
    canonicalize_limit,
    canonicalize_ordering,
    canonicalize_requirement,
    field_metadata,
)
from canna.runtime_view.contract import (
    CANONICALIZER_AGGREGATION,
    CANONICALIZER_COMPARISON,
    CANONICALIZER_COMPARISON_REQUIREMENT,
    CANONICALIZER_EXPLANATION,
    CANONICALIZER_GROUPING,
    CANONICALIZER_LIMIT,
    CANONICALIZER_ORDERING,
    REQUIREMENT_KIND_RANKING,
    STATUS_MAPPED,
)
from canna.runtime_view.query import (
    SubmittedAggregation,
    SubmittedCondition,
    SubmittedOrdering,
    SubmittedRequirement,
)
from canna.runtime_view.spans import CODE_SPAN_ALIGNMENT_FAILED

ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_REGISTRY = ROOT / "data" / "processed" / "semantic_registry.json"
EXECUTION_REGISTRY = ROOT / "data" / "processed" / "execution_registry.json"

ALL_OPERATIONS = (OPERATION_FILTER, OPERATION_ORDER, OPERATION_AGGREGATE, OPERATION_COUNT)

# A reference shaped like the minter's output. Nothing resolves it here; the
# requirement-level tests supply metadata by reference themselves.
FIELD_REF = "fd_" + "0" * 32


def measure(unit: str = UNIT_PERCENT_OBSERVED, operations=ALL_OPERATIONS) -> FieldMetadata:
    """A field described only by a declared unit and declared permissions."""
    return FieldMetadata(
        semantic_id="synthetic:Measure",
        unit_code=unit,
        allowed_operations=tuple(operations),
    )


def quoting(*spans: str) -> str:
    """A question that literally contains the spans under test."""
    return "조건 " + " / ".join(spans) + " 을 적용한다"


# ---------------------------------------------------------------------------
# 1. Ordering direction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("form", "expected"), DIRECTION_FORMS)
def test_every_direction_form_returns_the_direction_it_declares(form, expected):
    result = canonicalize_direction(quoting(form), form)
    assert result.ok
    assert result.direction == expected


def test_a_span_saying_both_directions_is_refused():
    span = "높은 낮은"
    result = canonicalize_direction(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_DIRECTION_AMBIGUOUS


def test_a_negated_direction_is_not_read_as_the_opposite():
    span = "높지 않은"
    result = canonicalize_direction(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_NEGATED


@pytest.mark.parametrize("span", ["안정적인", "적당한", "빠른", "우수한"])
def test_a_direction_this_layer_was_never_taught_is_refused(span):
    result = canonicalize_direction(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_DIRECTION_UNSUPPORTED


def test_a_direction_span_the_question_does_not_contain_is_refused():
    result = canonicalize_direction("수익률을 정렬해줘", "높은 순")
    assert not result.ok
    assert result.failure.code == CODE_SPAN_ALIGNMENT_FAILED


def test_the_registry_has_to_allow_ordering_before_a_direction_executes():
    span = "높은 순"
    allowed = canonicalize_ordering(quoting(span), span, measure(operations=(OPERATION_ORDER,)))
    refused = canonicalize_ordering(quoting(span), span, measure(operations=(OPERATION_FILTER,)))
    assert allowed.ok and allowed.direction == DIRECTION_DESC
    assert not refused.ok
    assert refused.failure.code == CODE_OPERATION_NOT_ALLOWED


def test_an_unresolved_field_leaves_a_readable_direction_unexecuted():
    span = "낮은 순"
    result = canonicalize_ordering(quoting(span), span, None)
    assert not result.ok
    assert result.failure.code == CODE_FIELD_METADATA_UNAVAILABLE


# ---------------------------------------------------------------------------
# 2. Limit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        ("10개", 10),
        ("10", 10),
        ("상위 10개", 10),
        ("하위 3건", 3),
        ("１０개", 10),
        ("1,000개", 1000),
        ("top 5", 5),
    ],
)
def test_a_count_expression_becomes_a_positive_integer(span, expected):
    result = canonicalize_limit(quoting(span), span)
    assert result.ok
    assert result.limit == expected


@pytest.mark.parametrize("span", ["0개", "-5개", "2.5개"])
def test_a_count_that_is_not_a_positive_whole_number_is_refused(span):
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_LIMIT_NOT_POSITIVE


def test_a_share_of_the_population_is_not_a_row_count():
    span = "상위 10%"
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_LIMIT_IS_PROPORTION


@pytest.mark.parametrize("span", ["10개 이상", "10개 초과", "10에서 20"])
def test_a_bounded_value_is_not_a_row_count(span):
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.failure.code in {CODE_LIMIT_UNSUPPORTED, CODE_LIMIT_AMBIGUOUS}


@pytest.mark.parametrize("span", ["3개월", "1년", "30일"])
def test_a_period_is_not_a_row_count(span):
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_LIMIT_UNSUPPORTED


def test_two_numbers_do_not_produce_one_limit():
    span = "10 20"
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_LIMIT_AMBIGUOUS


@pytest.mark.parametrize("span", ["다섯 개", "몇 개", "일부"])
def test_a_count_without_digits_is_refused_rather_than_guessed(span):
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_LIMIT_UNSUPPORTED


def test_a_magnitude_word_is_not_expanded_into_a_row_count():
    span = "10만개"
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_LIMIT_UNSUPPORTED


def test_a_limit_span_the_question_does_not_contain_is_refused():
    result = canonicalize_limit("상품을 보여줘", "10개")
    assert not result.ok
    assert result.failure.code == CODE_SPAN_ALIGNMENT_FAILED


# ---------------------------------------------------------------------------
# 3. Comparison operator and typed value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("form", "expected"), COMPARISON_FORMS)
def test_every_comparison_form_returns_the_operator_it_declares(form, expected):
    question = quoting(form, "3%")
    result = canonicalize_comparison(question, form, "3%", measure())
    assert result.ok, result.failure
    assert result.operator == expected


@pytest.mark.parametrize(("value", "expected"), [("3%", "3"), ("0.5%", "0.5"), ("10 퍼센트", "10")])
def test_a_percentage_is_carried_in_percent_notation_and_never_divided(value, expected):
    question = quoting("이상", value)
    result = canonicalize_comparison(question, "이상", value, measure())
    assert result.ok
    assert result.value.number == Decimal(expected)
    assert result.value.unit_code == UNIT_PERCENT_OBSERVED


def test_a_bare_number_is_read_in_the_fields_declared_unit():
    question = quoting("이상", "3")
    result = canonicalize_comparison(question, "이상", "3", measure())
    assert result.ok
    assert result.value.number == Decimal(3)
    assert result.value.marker == ""


@pytest.mark.parametrize("unit", [UNIT_CURRENCY_AMOUNT, UNIT_PRICE, UNIT_NUMBER, UNIT_NONE])
def test_a_unit_whose_magnitude_is_not_declared_refuses_every_written_value(unit):
    question = quoting("이상", "1000")
    result = canonicalize_comparison(question, "이상", "1000", measure(unit=unit))
    assert not result.ok
    assert result.failure.code == CODE_UNIT_NOT_CANONICALIZABLE


def test_a_currency_amount_is_refused_rather_than_placed_on_a_guessed_scale():
    question = quoting("이상", "1조원")
    result = canonicalize_comparison(
        question, "이상", "1조원", measure(unit=UNIT_CURRENCY_AMOUNT)
    )
    assert not result.ok
    assert result.failure.code == CODE_UNIT_NOT_CANONICALIZABLE


def test_a_field_whose_currency_comes_from_a_row_refuses_a_written_amount():
    metadata = FieldMetadata(
        semantic_id="synthetic:Measure",
        unit_code=UNIT_PERCENT_OBSERVED,
        currency_policy="from_subject_currency",
        allowed_operations=ALL_OPERATIONS,
    )
    question = quoting("이상", "3%")
    result = canonicalize_comparison(question, "이상", "3%", metadata)
    assert not result.ok
    assert result.failure.code == CODE_UNIT_NOT_CANONICALIZABLE


def test_a_value_written_in_another_units_words_is_refused():
    question = quoting("이상", "10개")
    result = canonicalize_comparison(question, "이상", "10개", measure())
    assert not result.ok
    assert result.failure.code == CODE_VALUE_UNIT_MISMATCH


def test_a_single_magnitude_word_is_expanded_and_a_compound_one_is_not():
    counted = measure(unit=UNIT_COUNT)
    single = canonicalize_comparison(quoting("이상", "1만"), "이상", "1만", counted)
    compound = canonicalize_comparison(
        quoting("이상", "1조 5000억"), "이상", "1조 5000억", counted
    )
    assert single.ok and single.value.number == Decimal(10000)
    assert not compound.ok
    assert compound.failure.code == CODE_VALUE_UNSUPPORTED


def test_a_thousands_separator_and_a_full_width_digit_read_the_same():
    counted = measure(unit=UNIT_COUNT)
    plain = canonicalize_comparison(quoting("이상", "1,000"), "이상", "1,000", counted)
    wide = canonicalize_comparison(quoting("이상", "１０００"), "이상", "１０００", counted)
    assert plain.ok and wide.ok
    assert plain.value.number == wide.value.number == Decimal(1000)


def test_conflicting_comparisons_are_refused():
    span = "이상 이하"
    result = canonicalize_comparison(quoting(span, "3%"), span, "3%", measure())
    assert not result.ok
    assert result.failure.code == CODE_COMPARISON_AMBIGUOUS


def test_a_negated_comparison_is_not_inverted():
    span = "높지 않은"
    result = canonicalize_comparison(quoting(span, "3%"), span, "3%", measure())
    assert not result.ok
    assert result.failure.code == CODE_NEGATED


@pytest.mark.parametrize("span", ["비슷한", "적절한", "관련된"])
def test_a_comparison_this_layer_was_never_taught_is_refused(span):
    result = canonicalize_comparison(quoting(span, "3%"), span, "3%", measure())
    assert not result.ok
    assert result.failure.code == CODE_COMPARISON_UNSUPPORTED


def test_the_registry_has_to_allow_filtering_before_a_comparison_executes():
    question = quoting("이상", "3%")
    result = canonicalize_comparison(
        question, "이상", "3%", measure(operations=(OPERATION_ORDER,))
    )
    assert not result.ok
    assert result.failure.code == CODE_OPERATION_NOT_ALLOWED


@pytest.mark.parametrize("bad", ["comparison", "value"])
def test_a_comparison_span_the_question_does_not_contain_is_refused(bad):
    question = quoting("이상", "3%")
    comparison = "이하" if bad == "comparison" else "이상"
    value = "7%" if bad == "value" else "3%"
    result = canonicalize_comparison(question, comparison, value, measure())
    assert not result.ok
    assert result.failure.code == CODE_SPAN_ALIGNMENT_FAILED


def test_a_unit_this_layer_has_never_declared_is_refused_rather_than_assumed():
    question = quoting("이상", "3")
    result = canonicalize_comparison(
        question, "이상", "3", measure(unit="unit_nobody_declared")
    )
    assert not result.ok
    assert result.failure.code == CODE_UNIT_NOT_CANONICALIZABLE


def test_a_field_with_no_declared_unit_refuses_a_written_value():
    question = quoting("이상", "3")
    result = canonicalize_comparison(question, "이상", "3", measure(unit=""))
    assert not result.ok
    assert result.failure.code == CODE_UNIT_NOT_CANONICALIZABLE


# ---------------------------------------------------------------------------
# 4. Aggregation function
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("form", "expected"), AGGREGATION_FORMS)
def test_every_aggregation_form_returns_the_function_it_declares(form, expected):
    result = canonicalize_aggregation(quoting(form), form, measure())
    assert result.ok, result.failure
    assert result.function == expected
    assert result.required_operation == AGGREGATION_OPERATIONS[expected]


@pytest.mark.parametrize("span", ["가중평균", "이동평균", "연평균", "중앙값", "누적 합계"])
def test_a_modified_aggregation_is_not_read_as_the_one_it_contains(span):
    result = canonicalize_aggregation(quoting(span), span, measure())
    assert not result.ok
    assert result.failure.code == CODE_AGGREGATION_UNSUPPORTED


def test_conflicting_aggregations_are_refused():
    span = "최대 최소"
    result = canonicalize_aggregation(quoting(span), span, measure())
    assert not result.ok
    assert result.failure.code == CODE_AGGREGATION_AMBIGUOUS


def test_counting_and_aggregating_are_separate_registry_permissions():
    aggregate_only = measure(operations=(OPERATION_AGGREGATE,))
    count_only = measure(operations=(OPERATION_COUNT,))
    assert canonicalize_aggregation(quoting("평균"), "평균", aggregate_only).ok
    assert canonicalize_aggregation(quoting("개수"), "개수", count_only).ok
    refused_count = canonicalize_aggregation(quoting("개수"), "개수", aggregate_only)
    refused_average = canonicalize_aggregation(quoting("평균"), "평균", count_only)
    assert refused_count.failure.code == CODE_OPERATION_NOT_ALLOWED
    assert refused_average.failure.code == CODE_OPERATION_NOT_ALLOWED


@pytest.mark.parametrize("span", ["분포", "추세", "요약"])
def test_an_aggregation_this_layer_was_never_taught_is_refused(span):
    result = canonicalize_aggregation(quoting(span), span, measure())
    assert not result.ok
    assert result.failure.code == CODE_AGGREGATION_UNSUPPORTED


def test_a_negated_aggregation_is_refused():
    span = "평균이 아니"
    result = canonicalize_aggregation(quoting(span), span, measure())
    assert not result.ok
    assert result.failure.code in {CODE_AGGREGATION_UNSUPPORTED, CODE_NEGATED}


# ---------------------------------------------------------------------------
# Requirement level
# ---------------------------------------------------------------------------


def _requirement(**overrides) -> SubmittedRequirement:
    base = {
        "requirement_id": "r1",
        "kind": REQUIREMENT_KIND_RANKING,
        "status": STATUS_MAPPED,
        "source_span": "조건",
        "ordering": SubmittedOrdering(field_ref=FIELD_REF, direction_span="높은 순"),
        "limit_span": "10개",
    }
    base.update(overrides)
    return SubmittedRequirement(**base)


def test_a_requirement_canonicalises_every_slot_it_carries():
    question = quoting("높은 순", "10개", "이상", "3%", "평균")
    requirement = _requirement(
        conditions=(
            SubmittedCondition(field_ref=FIELD_REF, comparison_span="이상", value_span="3%"),
        ),
        aggregation=SubmittedAggregation(field_ref=FIELD_REF, function_span="평균"),
    )
    result = canonicalize_requirement(question, requirement, lambda _ref: measure())
    assert result.ok
    assert result.ordering.direction == DIRECTION_DESC
    assert result.limit.limit == 10
    assert result.conditions[0].operator == "gte"
    assert result.conditions[0].value.number == Decimal(3)
    assert result.aggregation.function == "avg"


def test_each_failing_slot_reports_its_own_reason():
    question = quoting("적당한", "3%", "이상")
    requirement = _requirement(
        ordering=SubmittedOrdering(field_ref=FIELD_REF, direction_span="적당한"),
        limit_span="",
        conditions=(
            SubmittedCondition(
                field_ref=FIELD_REF, comparison_span="이상", value_span="3%"
            ),
        ),
    )
    result = canonicalize_requirement(
        question, requirement, lambda _ref: measure(unit=UNIT_CURRENCY_AMOUNT)
    )
    assert not result.ok
    codes = {failure.code for failure in result.failures}
    slots = {failure.slot for failure in result.failures}
    assert codes == {CODE_DIRECTION_UNSUPPORTED, CODE_UNIT_NOT_CANONICALIZABLE}
    assert len(slots) == 2


def test_an_unresolved_field_reference_stops_only_the_slot_that_uses_it():
    question = quoting("높은 순", "10개")
    requirement = _requirement()
    result = canonicalize_requirement(question, requirement, lambda _ref: None)
    assert result.limit.ok and result.limit.limit == 10
    assert result.ordering.failure.code == CODE_FIELD_METADATA_UNAVAILABLE


def test_a_requirement_with_no_derivable_slot_produces_no_failures():
    requirement = SubmittedRequirement(
        requirement_id="r1", kind="listing", status=STATUS_MAPPED, source_span="조건"
    )
    result = canonicalize_requirement(quoting("조건"), requirement, lambda _ref: measure())
    assert result.ok
    assert result.ordering is None and result.limit is None and result.aggregation is None


def test_canonicalisation_is_deterministic():
    question = quoting("높은 순", "10개", "이상", "3%")
    requirement = _requirement(
        conditions=(
            SubmittedCondition(field_ref=FIELD_REF, comparison_span="이상", value_span="3%"),
        )
    )
    runs = [
        canonicalize_requirement(question, requirement, lambda _ref: measure())
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]


# ---------------------------------------------------------------------------
# Generalisation guards
# ---------------------------------------------------------------------------


def test_no_form_in_a_lexicon_claims_two_meanings():
    for table in (DIRECTION_FORMS, COMPARISON_FORMS, AGGREGATION_FORMS):
        meanings: dict[str, str] = {}
        for form, meaning in table:
            assert meanings.setdefault(form, meaning) == meaning, form


def test_the_available_canonicaliser_set_names_only_the_implemented_ones():
    assert IMPLEMENTED_CANONICALIZERS == {
        CANONICALIZER_ORDERING,
        CANONICALIZER_LIMIT,
        CANONICALIZER_COMPARISON,
        CANONICALIZER_AGGREGATION,
    }
    for unimplemented in (
        CANONICALIZER_GROUPING,
        CANONICALIZER_COMPARISON_REQUIREMENT,
        CANONICALIZER_EXPLANATION,
    ):
        assert unimplemented not in IMPLEMENTED_CANONICALIZERS


def test_a_unit_profile_either_reads_values_or_says_why_it_does_not():
    for code, profile in UNIT_PROFILES.items():
        assert profile.unit_code == code
        assert profile.basis.strip()
        if profile.canonicalizable:
            assert profile.refusal_code == ""
        else:
            assert profile.refusal_code
            assert profile.markers == ()


@pytest.fixture(scope="module")
def semantic_registry() -> dict:
    if not SEMANTIC_REGISTRY.is_file():
        pytest.skip("the semantic registry has not been generated in this workspace")
    return json.loads(SEMANTIC_REGISTRY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def execution_registry() -> dict:
    if not EXECUTION_REGISTRY.is_file():
        pytest.skip("the execution registry has not been generated in this workspace")
    return json.loads(EXECUTION_REGISTRY.read_text(encoding="utf-8"))


def test_every_unit_the_registry_declares_has_a_reading(semantic_registry):
    """A unit added to the ontology must fail loudly here, not default silently."""
    declared = {
        str(term.get("unit_code") or "")
        for term in semantic_registry["terms"]
        if str(term.get("unit_code") or "")
    }
    assert declared
    assert declared <= set(UNIT_PROFILES)


def test_every_operation_this_layer_requires_is_one_the_registry_grants(semantic_registry):
    granted = {
        str(operation)
        for term in semantic_registry["terms"]
        for operation in term.get("allowed_operations") or ()
    }
    assert set(ALL_OPERATIONS) <= granted


def test_the_operator_and_function_names_are_the_ones_execution_publishes(execution_registry):
    """The canonical spelling is the Execution Registry's, not a second vocabulary."""
    published = {
        str(operation)
        for binding in execution_registry["bindings"]
        for operation in binding.get("physical_operations") or ()
    }
    assert published
    assert set(COMPARISON_OPERATORS) <= published
    assert set(AGGREGATION_FUNCTIONS) <= published


def test_the_module_names_no_registry_identifier(semantic_registry):
    """No semantic id, family or source table is copied into the grammar tables."""
    lines = (
        (ROOT / "src" / "canna" / "runtime_view" / "canonicalize.py")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    # Provenance is required to be written down, and writing it down means
    # naming the ontology class a vocabulary was taken from. Comments and the
    # ``*_SOURCE`` citation constants are therefore excluded; everything that
    # executes — the grammar tables, the unit profiles, the logic — is not.
    source = "\n".join(
        line
        for line in lines
        if not line.lstrip().startswith("#") and "_SOURCE = " not in line
    )
    identifiers = {str(term["semantic_id"]) for term in semantic_registry["terms"]}
    identifiers |= {
        str(family)
        for term in semantic_registry["terms"]
        for family in term.get("families") or ()
    }
    assert identifiers
    assert not [name for name in identifiers if name in source]


def test_the_real_registry_has_measures_this_layer_can_compare(semantic_registry):
    """Discovered structurally: whatever the Registry marks percent-and-filterable."""
    comparable = [
        term
        for term in semantic_registry["terms"]
        if str(term.get("unit_code") or "") == UNIT_PERCENT_OBSERVED
        and OPERATION_FILTER in (term.get("allowed_operations") or ())
        and not str(term.get("currency_policy") or "")
    ]
    assert comparable, "the Registry declares no percent measure this layer could compare"
    question = quoting("이상", "3%")
    for term in comparable:
        metadata = FieldMetadata(
            semantic_id=str(term["semantic_id"]),
            unit_code=str(term["unit_code"]),
            period_code=str(term.get("period_code") or ""),
            currency_policy="",
            allowed_operations=tuple(
                str(value) for value in term.get("allowed_operations") or ()
            ),
        )
        result = canonicalize_comparison(question, "이상", "3%", metadata)
        assert result.ok, (term["semantic_id"], result.failure)
        assert result.value.number == Decimal(3)


def test_field_metadata_is_read_from_the_registry_term_and_not_invented(semantic_registry):
    class _Term:
        def __init__(self, row):
            self.semantic_id = row["semantic_id"]
            self.evidence = row

    row = next(
        term
        for term in semantic_registry["terms"]
        if term.get("allowed_operations") and term.get("unit_code")
    )
    metadata = field_metadata(_Term(row))
    assert metadata.semantic_id == row["semantic_id"]
    assert metadata.unit_code == row["unit_code"]
    assert metadata.allowed_operations == tuple(str(v) for v in row["allowed_operations"])


def test_missing_metadata_reads_as_nothing_rather_than_as_a_default():
    empty = field_metadata(object())
    assert empty == FieldMetadata()
    assert not empty.allows(OPERATION_FILTER)


def test_direction_and_aggregation_do_not_share_a_meaning_by_accident():
    """"최대" sorts one way and aggregates another; the slot decides, not the word."""
    span = "최대"
    assert canonicalize_direction(quoting(span), span).direction == DIRECTION_DESC
    assert canonicalize_aggregation(quoting(span), span, measure()).function == "max"
    low = "최소"
    assert canonicalize_direction(quoting(low), low).direction == DIRECTION_ASC
    assert canonicalize_aggregation(quoting(low), low, measure()).function == "min"


# ---------------------------------------------------------------------------
# Adversarial: the silent wrong answers the first version produced
# ---------------------------------------------------------------------------
#
# Each block below corresponds to a way the substring matcher read something the
# span did not say. They are kept together because they share one cause: a form
# was allowed to speak from inside text that was never checked as a whole.


@pytest.mark.parametrize(
    "span",
    ["< 또는 <=", "<= 또는 <", "= 또는 !=", "!= 또는 =", "> 그리고 >="],
)
def test_two_operators_at_two_positions_stay_ambiguous(span):
    """Subsumption is per occurrence, not per vocabulary.

    "<=" is one expression because the "<" inside it is the same characters.
    A "<" written somewhere else in the span is a second expression, and the
    span says two different things.
    """
    result = canonicalize_comparison(quoting(span, "3%"), span, "3%", measure())
    assert not result.ok
    assert result.failure.code == CODE_COMPARISON_AMBIGUOUS


@pytest.mark.parametrize(
    ("span", "expected"),
    [("<", "lt"), ("<=", "lte"), (">", "gt"), (">=", "gte"), ("=", "eq"), ("!=", "ne")],
)
def test_a_longer_symbol_operator_is_read_as_itself(span, expected):
    result = canonicalize_comparison(quoting(span, "3%"), span, "3%", measure())
    assert result.ok
    assert result.operator == expected


def test_text_that_merely_contains_a_comparison_is_not_read_as_one():
    result = canonicalize_comparison(quoting("이상한", "3%"), "이상한", "3%", measure())
    assert not result.ok
    assert result.operator != "gte"
    assert result.failure.code == CODE_COMPARISON_UNSUPPORTED


@pytest.mark.parametrize("span", ["최소가입금액", "상위험", "최대한", "이상형"])
def test_text_that_merely_contains_a_direction_is_not_read_as_one(span):
    result = canonicalize_direction(quoting(span), span)
    assert not result.ok
    assert result.direction == ""
    assert result.failure.code == CODE_DIRECTION_UNSUPPORTED


@pytest.mark.parametrize("span", ["평균적으로", "평균가", "최소한도"])
def test_text_that_merely_contains_an_aggregation_is_not_read_as_one(span):
    result = canonicalize_aggregation(quoting(span), span, measure())
    assert not result.ok
    assert result.function == ""
    assert result.failure.code == CODE_AGGREGATION_UNSUPPORTED


def test_the_expressions_that_did_read_correctly_still_do():
    assert canonicalize_direction(quoting("높은 순"), "높은 순").direction == DIRECTION_DESC
    assert canonicalize_direction(quoting("가장 낮은"), "가장 낮은").direction == DIRECTION_ASC
    assert (
        canonicalize_comparison(quoting("보다 큰", "3%"), "보다 큰", "3%", measure()).operator
        == "gt"
    )
    assert (
        canonicalize_aggregation(quoting("가장 낮은"), "가장 낮은", measure()).function == "min"
    )


@pytest.mark.parametrize(
    ("table", "reader"),
    [
        (DIRECTION_FORMS, "direction"),
        (COMPARISON_FORMS, "comparison"),
        (AGGREGATION_FORMS, "aggregation"),
    ],
)
def test_no_form_survives_an_unexplained_syllable(table, reader):
    """The property behind the four examples, asserted on every form there is.

    "잡" appears in no approved expression, so a span ending in it is a span
    this layer has no reading for — whichever form it starts with.
    """
    for form, _meaning in table:
        span = form + "잡"
        if reader == "direction":
            result = canonicalize_direction(quoting(span), span)
        elif reader == "comparison":
            result = canonicalize_comparison(quoting(span, "3%"), span, "3%", measure())
        else:
            result = canonicalize_aggregation(quoting(span), span, measure())
        assert not result.ok, form


@pytest.mark.parametrize(
    ("span", "reader", "code"),
    [
        ("안높은", "direction", CODE_NEGATED),
        ("안 높은", "direction", CODE_NEGATED),
        ("안같은", "comparison", CODE_NEGATED),
        ("안 평균", "aggregation", CODE_NEGATED),
        ("안정적인", "direction", CODE_DIRECTION_UNSUPPORTED),
    ],
)
def test_an_attached_negation_is_caught_without_swallowing_a_normal_word(span, reader, code):
    if reader == "direction":
        result = canonicalize_direction(quoting(span), span)
    elif reader == "comparison":
        result = canonicalize_comparison(quoting(span, "3%"), span, "3%", measure())
    else:
        result = canonicalize_aggregation(quoting(span), span, measure())
    assert not result.ok
    assert result.failure.code == code


@pytest.mark.parametrize("table", [DIRECTION_FORMS, COMPARISON_FORMS, AGGREGATION_FORMS])
def test_no_form_can_be_negated_and_still_read(table):
    for form, _meaning in table:
        span = "안" + form
        results = [
            canonicalize_direction(quoting(span), span),
            canonicalize_comparison(quoting(span, "3%"), span, "3%", measure()),
            canonicalize_aggregation(quoting(span), span, measure()),
        ]
        assert not any(result.ok for result in results), form


@pytest.mark.parametrize("span", ["1,00개", "1,개", "12,34,567개"])
def test_a_badly_grouped_number_is_not_repaired_into_a_limit(span):
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.failure.code == CODE_LIMIT_UNSUPPORTED


@pytest.mark.parametrize("span", ["1,%", "12,34%", "1,000,00%"])
def test_a_badly_grouped_number_is_not_repaired_into_a_value(span):
    result = canonicalize_comparison(quoting("이상", span), "이상", span, measure())
    assert not result.ok
    assert result.failure.code == CODE_VALUE_UNSUPPORTED


def test_a_correctly_grouped_number_still_reads():
    counted = measure(unit=UNIT_COUNT)
    value = canonicalize_comparison(
        quoting("이상", "12,345,678"), "이상", "12,345,678", counted
    )
    assert value.ok
    assert value.value.number == Decimal(12345678)
    assert canonicalize_limit(quoting("1,000개"), "1,000개").limit == 1000


@pytest.mark.parametrize("span", ["KODEX 200", "상품코드 123", "ETF 10", "2026", "약 10개"])
def test_a_number_inside_other_text_is_not_a_row_count(span):
    """A product name, a code, a year and an approximation all carry an integer."""
    result = canonicalize_limit(quoting(span), span)
    assert not result.ok
    assert result.limit == 0
    assert result.failure.code == CODE_LIMIT_UNSUPPORTED


@pytest.mark.parametrize(
    ("span", "expected"),
    [("10", 10), ("10개", 10), ("상위 10개", 10), ("하위 3건", 3), ("top 5", 5)],
)
def test_the_row_counts_that_did_read_correctly_still_do(span, expected):
    result = canonicalize_limit(quoting(span), span)
    assert result.ok
    assert result.limit == expected
