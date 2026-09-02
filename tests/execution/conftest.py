from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from hashlib import sha256
from pathlib import Path

import duckdb
import pytest

from canna.execution import (
    FieldOperation,
    Grain,
    OrderDirection,
    ProductQueryExecutor,
    ResolvedProductQuery,
)


@pytest.fixture
def synthetic_execution(tmp_path: Path):
    store = tmp_path / "store.duckdb"
    connection = duckdb.connect(str(store))
    connection.execute("CREATE TABLE build_manifest(build_id VARCHAR)")
    connection.execute("INSERT INTO build_manifest VALUES (?)", ["synthetic-build"])
    connection.execute(
        """
        CREATE TABLE observations(
            subject_key VARCHAR,
            subject_grain VARCHAR,
            family_id VARCHAR,
            field_id VARCHAR,
            numeric_value DOUBLE,
            label_value VARCHAR,
            effective_as_of DATE,
            value_status VARCHAR,
            source_id VARCHAR,
            source_row_id VARCHAR
        )
        """
    )
    connection.executemany(
        "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("p1", "product", "family_a", "display", None, "One", date(2026, 8, 21), "valid", "source_a", "d1"),
            ("p2", "product", "family_a", "display", None, "Two", date(2026, 8, 21), "valid", "source_a", "d2"),
            ("p3", "product", "family_a", "display", None, "Three", date(2026, 8, 21), "valid", "source_a", "d3"),
            ("p4", "product", "family_a", "display", None, "Four", date(2026, 8, 21), "valid", "source_a", "d4"),
            ("p1", "product", "family_a", "rank", 1.0, None, date(2026, 8, 21), "valid", "source_a", "r1"),
            ("p2", "product", "family_a", "rank", 3.0, None, date(2026, 8, 21), "valid", "source_a", "r2"),
            ("p3", "product", "family_a", "rank", 2.0, None, date(2026, 8, 21), "valid", "source_a", "r3"),
            ("p4", "product", "family_a", "rank", 0.0, None, date(2026, 8, 21), "zero_excluded", "source_a", "r4"),
        ],
    )
    connection.close()

    def binding(field_id: str, value_column: str, operations: list[str]) -> dict:
        return {
            "semantic_id": field_id,
            "family_id": "family_a",
            "subject_grain": "product",
            "observation_table": "observations",
            "selector_column": "field_id",
            "selector_value": field_id,
            "value_column": value_column,
            "executable_operations": operations,
            "zero_semantics": (
                "excluded_from_measure_population" if field_id == "rank" else "preserved"
            ),
            "physical": {"source_table": "a_name_that_is_not_the_source_id"},
            "row_binding": {
                "subject_column": "subject_key",
                "source_id_column": "source_id",
                "source_row_id_column": "source_row_id",
                "effective_as_of_column": "effective_as_of",
                "value_status_column": "value_status",
                "valid_value_status": "valid",
            },
            "selection_policy": {
                "kind": "unique_per_subject",
                "snapshot_policy": "single_effective_date",
            },
            "observed_coverage": {
                "subject_total": 4,
                "max_observations_per_subject": 1,
                "coverage_status": "partial" if field_id == "rank" else "full",
                "unknown_coverage": False,
                "missing_subjects": 0,
                "parse_failed_subjects": 0,
                "collection_failure_count": 0,
                "unknown_coverage_count": 0,
            },
        }

    registry = {
        "data_catalog": {
            "build_id": "synthetic-build",
            "store_sha256": sha256(store.read_bytes()).hexdigest(),
            "store_path": str(store),
            "sources": [
                {
                    "source_id": "source_a",
                    "source_kind": "official",
                    "source_name": "Synthetic official source",
                    "source_file": "source.xlsx",
                    "sha256": "fixture-hash",
                    "hash_matches": True,
                }
            ],
        },
        "bindings": [
            binding("display", "label_value", ["filter"]),
            binding("rank", "numeric_value", ["order"]),
        ],
        "dataset_bindings": [
            {
                "family_id": "family_a",
                "subject_grain": "product",
                "population": {
                    "subject_total": 4,
                    "coverage_status": "full",
                    "unknown_coverage": False,
                    "missing_subjects": 0,
                    "parse_failed_subjects": 0,
                    "collection_failure_count": 0,
                    "unknown_coverage_count": 0,
                },
            }
        ],
        "join_paths": [
            {
                "left": "product.product_key",
                "right": "observations.subject_key",
            }
        ],
    }
    registry_path = tmp_path / "execution_registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    def query(**changes) -> ResolvedProductQuery:
        values = {
            "dataset_family": "family_a",
            "result_grain": Grain.PRODUCT,
            "display_field_id": "display",
            "order_field_id": "rank",
            "field_operation": FieldOperation.ORDER,
            "direction": OrderDirection.DESC,
            "limit": 2,
        }
        values.update(changes)
        return ResolvedProductQuery(**values)

    def refresh_store_hash(payload: dict) -> None:
        payload["data_catalog"]["store_sha256"] = sha256(store.read_bytes()).hexdigest()

    return {
        "store": store,
        "registry": registry,
        "registry_path": registry_path,
        "executor": ProductQueryExecutor(registry_path, store),
        "query": query,
        "write_registry": lambda payload: registry_path.write_text(
            json.dumps(payload), encoding="utf-8"
        ),
        "copy_registry": lambda: deepcopy(registry),
        "refresh_store_hash": refresh_store_hash,
    }
