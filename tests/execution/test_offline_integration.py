from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from canna.execution import (
    ExecutionStatus,
    FieldOperation,
    Grain,
    OrderDirection,
    ProductQueryExecutor,
    ResolvedProductQuery,
)

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "data" / "processed" / "query_store.duckdb"
REGISTRY = ROOT / "data" / "processed" / "execution_registry.json"

pytestmark = [
    pytest.mark.real_data,
    pytest.mark.skipif(
        not (STORE.is_file() and REGISTRY.is_file()),
        reason="actual query store and Execution Registry are required for offline integration",
    ),
]


def test_real_registry_and_duckdb_are_diagnostic_only_until_row_binding_exists() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    order_binding = next(
        binding
        for binding in registry["bindings"]
        if binding["binding_kind"] == "metric"
        and "order" in binding["executable_operations"]
        and (binding.get("observed_coverage") or {}).get("valid_subjects")
        and (binding.get("observed_coverage") or {}).get("max_observations_per_subject") == 1
        and any(
            candidate["family_id"] == binding["family_id"]
            and candidate["subject_grain"] == binding["subject_grain"]
            and candidate["binding_kind"] == "attribute"
            and candidate["value_column"] == "label_value"
            and (candidate.get("observed_coverage") or {}).get("valid_subjects")
            and (candidate.get("observed_coverage") or {}).get("max_observations_per_subject") == 1
            for candidate in registry["bindings"]
        )
    )
    display_binding = next(
        binding
        for binding in registry["bindings"]
        if binding["family_id"] == order_binding["family_id"]
        and binding["subject_grain"] == order_binding["subject_grain"]
        and binding["binding_kind"] == "attribute"
        and binding["value_column"] == "label_value"
        and (binding.get("observed_coverage") or {}).get("valid_subjects")
        and (binding.get("observed_coverage") or {}).get("max_observations_per_subject") == 1
    )
    query = ResolvedProductQuery(
        dataset_family=order_binding["family_id"],
        result_grain=Grain(order_binding["subject_grain"]),
        display_field_id=display_binding["semantic_id"],
        order_field_id=order_binding["semantic_id"],
        field_operation=FieldOperation.ORDER,
        direction=OrderDirection.DESC,
        limit=5,
    )

    result = ProductQueryExecutor(REGISTRY, STORE).execute(query)

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.binding_failures[0].code.value == "provenance_binding_unavailable"

    connection = duckdb.connect(str(STORE), read_only=True)
    diagnostic_count = connection.execute(
        f"SELECT count(*) FROM {order_binding['observation_table']} "
        f"WHERE {order_binding['selector_column']} = ?",
        [order_binding["selector_value"]],
    ).fetchone()[0]
    connection.close()
    assert diagnostic_count > 0
