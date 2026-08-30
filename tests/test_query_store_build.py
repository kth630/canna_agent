"""Structural tests for the derivation rules behind the query store.

These test the rules, not today's data.  Type strings and field names below are
deliberately not the ones present in the official workbooks, so a rule that only
works for the current 280 fields fails here.
"""

from __future__ import annotations

import pytest

from canna.store.holdings import isin_checksum_ok
from canna.store.types import (
    allowed_operations,
    as_of_fields,
    binding_type_role,
    normalized_date_expression,
    physical_type,
    zero_semantics,
)

RANKING_OPERATIONS = {"order", "min", "max", "avg", "sum"}


@pytest.mark.parametrize(
    ("declared", "expected_type", "expected_role"),
    [
        ("text", "VARCHAR", "label_or_code"),
        ("TEXT", "VARCHAR", "label_or_code"),
        ("double precision", "DOUBLE", "measure"),
        ("numeric(10,4)", "DECIMAL(10,4)", "measure"),
        ("numeric(38, 15)", "DECIMAL(38,15)", "measure"),
        ("numeric(12,0)", "DECIMAL(12,0)", "integer_unverified_zero_semantics"),
        ("bigint", "BIGINT", "integer_unverified_zero_semantics"),
    ],
)
def test_declared_type_maps_to_physical_type_and_role(declared, expected_type, expected_role):
    duck_type, role, _ = physical_type(declared)
    assert (duck_type, role) == (expected_type, expected_role)


def test_unmapped_declared_type_is_a_build_failure_not_a_silent_default():
    with pytest.raises(ValueError):
        physical_type("geometry")


def test_measure_supports_ranking_and_excludes_zero_from_its_population():
    operations = set(allowed_operations("measure"))
    assert RANKING_OPERATIONS.issubset(operations)
    assert zero_semantics("measure") == "excluded_from_measure_population"


def test_unverified_integer_cannot_be_ranked_or_aggregated():
    """0 may be a legitimate code here, so ranking stays closed until verified."""
    operations = set(allowed_operations("integer_unverified_zero_semantics"))
    assert not operations & RANKING_OPERATIONS
    assert zero_semantics("integer_unverified_zero_semantics") == "preserved_pending_verification"


def test_label_or_code_is_not_rankable_and_keeps_its_zero_values():
    operations = set(allowed_operations("label_or_code"))
    assert not operations & RANKING_OPERATIONS
    assert "contains" in operations
    assert zero_semantics("label_or_code") == "preserved"


def test_date_slot_is_ordered_even_though_the_source_column_is_text():
    role = binding_type_role("label_or_code", "attribute", "date")
    assert role == "date"
    assert "order" in allowed_operations(role)
    assert zero_semantics(role) == "not_applicable"


def test_metric_parsed_from_text_becomes_a_measure():
    assert binding_type_role("label_or_code", "metric", "value") == "measure"


def test_scale_zero_integer_metric_keeps_its_unverified_zero_semantics():
    """Parsing does not tell us what 0 means, so ranking stays closed."""
    role = binding_type_role("integer_unverified_zero_semantics", "metric", "value")
    assert role == "integer_unverified_zero_semantics"
    assert not set(allowed_operations(role)) & RANKING_OPERATIONS


def test_attribute_from_a_measure_column_keeps_the_measure_role():
    assert binding_type_role("measure", "attribute", "value") == "measure"


def test_as_of_note_resolves_exact_field_names():
    order = ["alpha_dt", "beta_dt", "unrelated"]
    matched, exact, expanded = as_of_fields("alpha_dt, beta_dt", order)
    assert matched == ["alpha_dt", "beta_dt"]
    assert exact == ["alpha_dt", "beta_dt"]
    assert expanded == []


def test_as_of_note_expands_recorded_patterns_and_ignores_prose():
    order = ["price_base_dt", "nav_base_dt", "row_upt_dt", "name"]
    matched, exact, expanded = as_of_fields("field-specific *_base_dt, row_upt_dt", order)
    assert matched == ["nav_base_dt", "price_base_dt", "row_upt_dt"]
    assert exact == ["row_upt_dt"]
    assert expanded == ["price_base_dt", "nav_base_dt"]


def test_field_named_exactly_is_not_also_counted_as_pattern_expanded():
    order = ["a_base_dt", "b_base_dt"]
    matched, exact, expanded = as_of_fields("a_base_dt, *_base_dt", order)
    assert matched == ["a_base_dt", "b_base_dt"]
    assert exact == ["a_base_dt"]
    assert expanded == ["b_base_dt"]


def test_as_of_note_without_any_real_field_resolves_to_nothing():
    matched, exact, expanded = as_of_fields("no recorded as-of field", ["price", "amount"])
    assert (matched, exact, expanded) == ([], [], [])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20260824", "2026-08-24"),
        ("2026-08-24", "2026-08-24"),
        ("", None),
        ("2026", None),
        ("알 수 없음", None),
    ],
)
def test_date_normalisation_accepts_only_an_unambiguous_calendar_date(raw, expected):
    import duckdb

    expression = normalized_date_expression("value")
    result = duckdb.connect().execute(
        f"SELECT {expression} FROM (SELECT ? AS value)", [raw]
    ).fetchone()[0]
    assert (str(result) if result else None) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("US0378331005", True),
        ("KR7005930003", True),
        ("US0378331004", False),
        ("US037833100", False),
        ("", False),
        ("US03783310-5", False),
    ],
)
def test_isin_checksum_accepts_only_valid_check_digits(value, expected):
    assert isin_checksum_ok(value) is expected
