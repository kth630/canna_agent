from __future__ import annotations

from datetime import date

import duckdb
import pytest
from pydantic import ValidationError

from canna.execution import (
    BindingFailureCode,
    CoverageScope,
    ExecutionStatus,
    FreshnessStatus,
    Grain,
    OrderDirection,
    ProductQueryExecutor,
)


def ordered_values(result) -> list[float]:
    return [row.ordered_by.value for row in result.rows]


def mutate_store(synthetic_execution, sql: str, parameters=()) -> dict:
    connection = duckdb.connect(str(synthetic_execution["store"]))
    connection.execute(sql, parameters)
    connection.close()
    registry = synthetic_execution["copy_registry"]()
    synthetic_execution["refresh_store_hash"](registry)
    synthetic_execution["write_registry"](registry)
    return registry


def test_normal_ranking_preserves_typed_result_metadata(synthetic_execution) -> None:
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())

    assert result.status is ExecutionStatus.EXECUTED
    assert ordered_values(result) == [3.0, 2.0]
    assert [row.display.value for row in result.rows] == ["Two", "Three"]
    assert result.applied_operations[0].field_id == "rank"
    assert result.sources[0].source_id == "source_a"
    assert synthetic_execution["registry"]["bindings"][0]["physical"]["source_table"] != "source_a"
    assert result.rows[0].display.source_row_id == "d2"
    assert result.rows[0].ordered_by.source_row_id == "r2"
    assert result.rows[0].display.effective_as_of == date(2026, 8, 21)
    assert result.rows[0].ordered_by.effective_as_of == date(2026, 8, 21)
    assert result.freshness.status is FreshnessStatus.LATEST_AVAILABLE
    assert result.binding_failures == ()


@pytest.mark.parametrize(
    ("direction", "expected"),
    [(OrderDirection.ASC, [1.0, 2.0, 3.0]), (OrderDirection.DESC, [3.0, 2.0, 1.0])],
)
def test_order_direction_is_typed_and_deterministic(
    synthetic_execution, direction: OrderDirection, expected: list[float]
) -> None:
    query = synthetic_execution["query"](direction=direction, limit=3)
    assert ordered_values(synthetic_execution["executor"].execute(query)) == expected


def test_limit_boundaries_are_rejected_before_sql(synthetic_execution) -> None:
    assert synthetic_execution["query"](limit=1).limit == 1
    assert synthetic_execution["query"](limit=101).limit == 101
    with pytest.raises(ValidationError):
        synthetic_execution["query"](limit=0)
    with pytest.raises(ValidationError):
        synthetic_execution["query"](limit=-1)
    with pytest.raises(ValidationError):
        synthetic_execution["query"](direction="DESC")


def test_operation_not_allowed_is_unsupported(synthetic_execution) -> None:
    query = synthetic_execution["query"](order_field_id="display")
    result = synthetic_execution["executor"].execute(query)
    assert result.status is ExecutionStatus.UNSUPPORTED
    assert result.binding_failures[0].code is BindingFailureCode.OPERATION_NOT_ALLOWED


def test_missing_and_multiple_bindings_fail_closed(synthetic_execution) -> None:
    missing = synthetic_execution["executor"].execute(
        synthetic_execution["query"](order_field_id="absent")
    )
    assert missing.status is ExecutionStatus.UNSUPPORTED
    assert missing.binding_failures[0].code is BindingFailureCode.FIELD_NOT_REGISTERED

    registry = synthetic_execution["copy_registry"]()
    registry["bindings"].append(dict(registry["bindings"][1]))
    synthetic_execution["write_registry"](registry)
    multiple = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert multiple.status is ExecutionStatus.AMBIGUOUS
    assert multiple.binding_failures[0].code is BindingFailureCode.MULTIPLE_BINDINGS
    assert multiple.binding_failures[0].binding_count == 2


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"dataset_family": "family_b"}, BindingFailureCode.FAMILY_MISMATCH),
        ({"result_grain": Grain.PRODUCT_CLASS}, BindingFailureCode.GRAIN_MISMATCH),
    ],
)
def test_family_and_grain_mismatch_are_unavailable(synthetic_execution, changes, code) -> None:
    result = synthetic_execution["executor"].execute(synthetic_execution["query"](**changes))
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is code


def test_partial_coverage_never_claims_global_top_n(synthetic_execution) -> None:
    result = synthetic_execution["executor"].execute(synthetic_execution["query"](limit=3))
    assert result.coverage.scope is CoverageScope.OBSERVED
    assert result.coverage.subject_total == 4
    assert result.coverage.observed_universe == 3
    assert result.coverage.missing_subjects == 1
    assert result.coverage.global_ranking_claim_allowed is False


def test_requested_as_of_must_match_an_actual_observation(synthetic_execution) -> None:
    exact = synthetic_execution["executor"].execute(
        synthetic_execution["query"](requested_as_of=date(2026, 8, 21))
    )
    assert exact.status is ExecutionStatus.EXECUTED
    assert exact.freshness.status is FreshnessStatus.EXACT_REQUESTED
    assert exact.freshness.requested_as_of == date(2026, 8, 21)

    mismatch = synthetic_execution["executor"].execute(
        synthetic_execution["query"](requested_as_of=date(2026, 8, 19))
    )
    assert mismatch.status is ExecutionStatus.UNAVAILABLE
    assert mismatch.binding_failures[0].code is BindingFailureCode.AS_OF_UNAVAILABLE


def test_display_and_order_requested_as_of_must_both_match(synthetic_execution) -> None:
    mutate_store(
        synthetic_execution,
        "UPDATE observations SET effective_as_of = ? WHERE field_id = ?",
        [date(2026, 8, 20), "display"],
    )
    result = synthetic_execution["executor"].execute(
        synthetic_execution["query"](requested_as_of=date(2026, 8, 21))
    )
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.AS_OF_UNAVAILABLE


@pytest.mark.parametrize("replacement", [date(2026, 8, 20), None])
def test_mixed_or_unknown_effective_dates_fail_closed(
    synthetic_execution, replacement
) -> None:
    mutate_store(
        synthetic_execution,
        "UPDATE observations SET effective_as_of = ? WHERE source_row_id = ?",
        [replacement, "r1"],
    )
    result = synthetic_execution["executor"].execute(synthetic_execution["query"](limit=3))
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.SNAPSHOT_INCOMPATIBLE


def test_source_binding_is_required_and_physical_table_name_is_never_inferred(
    synthetic_execution,
) -> None:
    registry = synthetic_execution["copy_registry"]()
    del registry["bindings"][1]["row_binding"]["source_id_column"]
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.PROVENANCE_BINDING_UNAVAILABLE


def test_source_hash_mismatch_fails_closed(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    registry["data_catalog"]["sources"][0]["hash_matches"] = False
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.SOURCE_INTEGRITY_MISMATCH


def test_registry_identifiers_are_allow_listed(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    registry["bindings"][1]["observation_table"] = "observations; DROP TABLE observations"
    synthetic_execution["write_registry"](registry)

    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.INVALID_REGISTRY_IDENTIFIER

    connection = duckdb.connect(str(synthetic_execution["store"]), read_only=True)
    assert connection.execute("SELECT count(*) FROM observations").fetchone()[0] == 8
    connection.close()


def test_display_selector_collision_with_another_family_fails_closed(
    synthetic_execution,
) -> None:
    registry = synthetic_execution["copy_registry"]()
    collision = dict(registry["bindings"][0])
    collision["family_id"] = "family_b"
    registry["bindings"].append(collision)
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.BINDING_LAYOUT_UNAVAILABLE


def test_missing_max_observations_metadata_is_not_treated_as_zero(
    synthetic_execution,
) -> None:
    registry = synthetic_execution["copy_registry"]()
    del registry["bindings"][1]["observed_coverage"]["max_observations_per_subject"]
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.SELECTION_POLICY_UNAVAILABLE


def test_selector_values_are_parameter_bound(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    injected = "rank' OR 1=1 --"
    registry["bindings"][1]["semantic_id"] = injected
    registry["bindings"][1]["selector_value"] = injected
    synthetic_execution["write_registry"](registry)

    empty = synthetic_execution["executor"].execute(
        synthetic_execution["query"](order_field_id=injected)
    )
    assert empty.status is ExecutionStatus.UNAVAILABLE
    assert empty.binding_failures[0].code is BindingFailureCode.QUERY_FAILED


def test_store_generation_must_match_registry(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    registry["data_catalog"]["store_sha256"] = "different-store-hash"
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.GENERATION_MISMATCH


def test_missing_subject_total_produces_unknown_coverage(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    del registry["bindings"][1]["observed_coverage"]["subject_total"]
    del registry["dataset_bindings"][0]["population"]["subject_total"]
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.EXECUTED
    assert result.coverage.scope is CoverageScope.UNKNOWN
    assert result.coverage.subject_total is None
    assert result.coverage.missing_subjects is None
    assert result.coverage.global_ranking_claim_allowed is False


def test_equal_count_with_coverage_failure_is_not_full(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    registry["bindings"][1]["observed_coverage"].update(
        {"subject_total": 3, "coverage_status": "full", "collection_failure_count": 1}
    )
    registry["dataset_bindings"][0]["population"].update(
        {"subject_total": 3, "coverage_status": "full"}
    )
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"](limit=3))
    assert result.coverage.observed_universe == result.coverage.subject_total == 3
    assert result.coverage.scope is CoverageScope.OBSERVED
    assert result.coverage.global_ranking_claim_allowed is False


def test_full_requires_explicit_complete_metadata_and_equal_count(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    registry["bindings"][1]["observed_coverage"].update(
        {"subject_total": 3, "coverage_status": "full"}
    )
    registry["dataset_bindings"][0]["population"].update(
        {"subject_total": 3, "coverage_status": "full"}
    )
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"](limit=3))
    assert result.coverage.scope is CoverageScope.FULL
    assert result.coverage.global_ranking_claim_allowed is True


def test_dataset_population_binding_is_required(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    del registry["dataset_bindings"]
    synthetic_execution["write_registry"](registry)
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.DATASET_BINDING_UNAVAILABLE


def test_malformed_registry_root_is_rejected(synthetic_execution) -> None:
    synthetic_execution["registry_path"].write_text("[]", encoding="utf-8")
    result = synthetic_execution["executor"].execute(synthetic_execution["query"]())
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.MALFORMED_REGISTRY


def test_database_error_does_not_expose_sql_table_or_path(synthetic_execution) -> None:
    registry = synthetic_execution["copy_registry"]()
    registry["bindings"][1]["value_column"] = "missing_physical_column"
    synthetic_execution["write_registry"](registry)
    executor = synthetic_execution["executor"]
    result = executor.execute(synthetic_execution["query"]())
    detail = result.binding_failures[0].detail
    assert result.binding_failures[0].code is BindingFailureCode.QUERY_FAILED
    assert "missing_physical_column" not in detail
    assert "observations" not in detail
    assert str(synthetic_execution["store"]) not in detail
    assert "BinderException" in detail
    assert "missing_physical_column" in executor.diagnostics[0]["exception"]


def test_missing_registry_is_an_explicit_unavailable_result(synthetic_execution, tmp_path) -> None:
    result = ProductQueryExecutor(tmp_path / "missing-registry.json").execute(
        synthetic_execution["query"]()
    )
    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code is BindingFailureCode.REGISTRY_UNAVAILABLE
