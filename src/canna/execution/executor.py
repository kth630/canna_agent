"""Registry-only SQL compilation and offline DuckDB product execution."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import duckdb

from canna.execution.models import (
    AppliedOperation,
    BindingFailure,
    BindingFailureCode,
    CoverageMetadata,
    CoverageScope,
    ExecutionStatus,
    ExecutionValue,
    FreshnessMetadata,
    FreshnessStatus,
    ProductExecutionRow,
    ResolvedProductQuery,
    SourceMetadata,
    TypedExecutionResult,
)
from canna.execution.registry import (
    BoundField,
    DatasetBinding,
    RegistryFormatError,
    load_registry,
    resolve_dataset,
    resolve_field,
)


class ProductQueryExecutor:
    """Execute a bounded listing query without accepting SQL or physical names."""

    def __init__(self, registry_path: Path, store_path: Path | None = None) -> None:
        self.registry_path = registry_path
        self.store_path = store_path
        self._diagnostics: list[dict[str, str]] = []

    @property
    def diagnostics(self) -> tuple[dict[str, str], ...]:
        """Internal diagnostics; never copied into ``TypedExecutionResult``."""
        return tuple(self._diagnostics)

    def execute(self, query: ResolvedProductQuery) -> TypedExecutionResult:
        self._diagnostics.clear()
        registry = self._read_registry(query)
        if isinstance(registry, TypedExecutionResult):
            return registry
        store = self._resolve_store(registry)
        if store is None or not store.is_file():
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                BindingFailureCode.STORE_UNAVAILABLE,
                "the query store is unavailable",
            )
        display = resolve_field(registry, query, query.display_field_id, "display", None)
        if display.binding is None:
            return self._resolution_failure(query, display.status, display.failure)
        ordered = resolve_field(
            registry, query, query.order_field_id, "order", query.field_operation
        )
        if ordered.binding is None:
            return self._resolution_failure(query, ordered.status, ordered.failure)
        dataset, dataset_failure = resolve_dataset(registry, query)
        if dataset is None:
            return self._resolution_failure(
                query, ExecutionStatus.UNAVAILABLE, dataset_failure
            )
        connection: duckdb.DuckDBPyConnection | None = None
        try:
            mismatch = self._generation_failure(store, registry)
            if mismatch is not None:
                return self._resolution_failure(query, ExecutionStatus.UNAVAILABLE, mismatch)
            connection = duckdb.connect(str(store), read_only=True)
            records = self._run(connection, query, display.binding, ordered.binding)
        except (duckdb.Error, KeyError, TypeError, ValueError, OSError) as error:
            self._diagnostics.append(
                {"exception_type": type(error).__name__, "exception": repr(error)}
            )
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                BindingFailureCode.QUERY_FAILED,
                f"offline execution failed ({type(error).__name__})",
            )
        finally:
            if connection is not None:
                connection.close()
        if not records:
            code = (
                BindingFailureCode.AS_OF_UNAVAILABLE
                if query.requested_as_of is not None
                else BindingFailureCode.QUERY_FAILED
            )
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                code,
                "no valid compatible observations were selected",
            )
        return self._result(
            query, registry, dataset, display.binding, ordered.binding, records
        )

    def _read_registry(self, query: ResolvedProductQuery) -> dict[str, Any] | TypedExecutionResult:
        try:
            return load_registry(self.registry_path)
        except RegistryFormatError as error:
            self._diagnostics.append(
                {"exception_type": type(error).__name__, "exception": repr(error)}
            )
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                BindingFailureCode.MALFORMED_REGISTRY,
                "the Execution Registry root is malformed",
            )
        except (OSError, json.JSONDecodeError) as error:
            self._diagnostics.append(
                {"exception_type": type(error).__name__, "exception": repr(error)}
            )
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                BindingFailureCode.REGISTRY_UNAVAILABLE,
                f"the Execution Registry could not be loaded ({type(error).__name__})",
            )

    def _resolve_store(self, registry: dict[str, Any]) -> Path | None:
        if self.store_path is not None:
            return self.store_path
        declared = registry["data_catalog"].get("store_path")
        if not isinstance(declared, str) or not declared:
            return None
        candidate = Path(declared)
        if candidate.is_absolute():
            return candidate
        return self.registry_path.resolve().parents[2] / candidate

    @staticmethod
    def _generation_failure(
        store: Path, registry: dict[str, Any]
    ) -> BindingFailure | None:
        expected = registry["data_catalog"].get("store_sha256")
        if not isinstance(expected, str) or not expected:
            return BindingFailure(
                code=BindingFailureCode.GENERATION_MISMATCH,
                detail="the Registry does not provide a verified store hash",
            )
        digest = sha256()
        with store.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            return BindingFailure(
                code=BindingFailureCode.GENERATION_MISMATCH,
                detail="the Registry store hash does not match the query store",
            )
        return None

    @staticmethod
    def _selection_sql(
        binding: BoundField, requested: bool
    ) -> tuple[str, list[Any]]:
        row = binding.row
        as_of_clause = f"AND {row.effective_as_of_column} = ?" if requested else ""
        zero_clause = ""
        parameters: list[Any] = [binding.selector_value, row.valid_value_status]
        if requested:
            parameters.append(None)  # replaced by the caller with the requested date
        if binding.zero_semantics == "excluded_from_measure_population":
            zero_clause = f"AND {binding.value_column} <> ?"
            parameters.append(0)
        columns = f"""
            {row.subject_column} AS subject_identifier,
            {binding.value_column} AS field_value,
            {row.effective_as_of_column} AS effective_as_of,
            {row.source_id_column} AS source_id,
            {row.source_row_id_column} AS source_row_id
        """
        where = f"""
            {binding.selector_column} = ?
            AND {row.value_status_column} = ?
            AND {binding.value_column} IS NOT NULL
            {as_of_clause} {zero_clause}
        """
        if binding.selection.kind == "unique_per_subject":
            return f"SELECT {columns} FROM {binding.observation_table} WHERE {where}", parameters
        return (
            f"""
            SELECT subject_identifier, field_value, effective_as_of, source_id, source_row_id
            FROM (
                SELECT {columns}, row_number() OVER (
                    PARTITION BY {row.subject_column}
                    ORDER BY {row.effective_as_of_column} DESC NULLS LAST,
                             {row.source_row_id_column}
                ) AS selected
                FROM {binding.observation_table} WHERE {where}
            ) WHERE selected = 1
            """,
            parameters,
        )

    @classmethod
    def _run(
        cls,
        connection: duckdb.DuckDBPyConnection,
        query: ResolvedProductQuery,
        display: BoundField,
        ordered: BoundField,
    ) -> list[tuple[Any, ...]]:
        display_sql, display_parameters = cls._selection_sql(
            display, query.requested_as_of is not None
        )
        order_sql, order_parameters = cls._selection_sql(
            ordered, query.requested_as_of is not None
        )
        if query.requested_as_of is not None:
            display_parameters[2] = query.requested_as_of
            order_parameters[2] = query.requested_as_of
        parameters = order_parameters + display_parameters + [query.limit]
        direction = query.direction.value.upper()
        sql = f"""
            WITH order_selected AS ({order_sql}),
            display_selected AS ({display_sql})
            SELECT o.subject_identifier,
                   d.field_value, d.effective_as_of, d.source_id, d.source_row_id,
                   o.field_value, o.effective_as_of, o.source_id, o.source_row_id,
                   count(*) OVER () AS observed_universe,
                   min(d.effective_as_of) OVER () AS display_min,
                   max(d.effective_as_of) OVER () AS display_max,
                   count(*) FILTER (WHERE d.effective_as_of IS NULL) OVER () AS display_unknown,
                   min(o.effective_as_of) OVER () AS order_min,
                   max(o.effective_as_of) OVER () AS order_max,
                   count(*) FILTER (WHERE o.effective_as_of IS NULL) OVER () AS order_unknown,
                   count(*) FILTER (
                       WHERE d.effective_as_of IS DISTINCT FROM o.effective_as_of
                   ) OVER () AS field_date_mismatch,
                   list(DISTINCT d.source_id) OVER () AS display_sources,
                   list(DISTINCT o.source_id) OVER () AS order_sources,
                   count(*) FILTER (
                       WHERE d.source_id IS NULL OR d.source_row_id IS NULL
                   ) OVER () AS display_provenance_missing,
                   count(*) FILTER (
                       WHERE o.source_id IS NULL OR o.source_row_id IS NULL
                   ) OVER () AS order_provenance_missing,
                   count(*) OVER () - count(DISTINCT o.subject_identifier) OVER ()
                       AS duplicate_subjects
            FROM order_selected o
            JOIN display_selected d USING (subject_identifier)
            ORDER BY o.field_value {direction} NULLS LAST, o.subject_identifier
            LIMIT ?
        """
        return connection.execute(sql, parameters).fetchall()

    def _result(
        self,
        query: ResolvedProductQuery,
        registry: dict[str, Any],
        dataset: DatasetBinding,
        display: BoundField,
        ordered: BoundField,
        records: list[tuple[Any, ...]],
    ) -> TypedExecutionResult:
        first = records[0]
        if any(int(first[index]) for index in (19, 20)):
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                BindingFailureCode.PROVENANCE_BINDING_UNAVAILABLE,
                "selected observations do not carry complete row provenance",
            )
        if int(first[21]):
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                BindingFailureCode.SELECTION_POLICY_UNAVAILABLE,
                "selected observations violate the declared subject selection policy",
            )
        snapshot_failure = self._snapshot_failure(query, first)
        if snapshot_failure is not None:
            return self._resolution_failure(
                query, ExecutionStatus.UNAVAILABLE, snapshot_failure
            )
        all_source_ids = {
            str(source_id)
            for source_ids in (first[17], first[18])
            for source_id in (source_ids or [])
        }
        source_result = self._validated_sources(query, registry, all_source_ids)
        if isinstance(source_result, TypedExecutionResult):
            return source_result
        rows = tuple(
            ProductExecutionRow(
                subject_key=str(record[0]),
                display=ExecutionValue(
                    field_id=display.semantic_id,
                    value=record[1],
                    effective_as_of=record[2],
                    source_id=str(record[3]),
                    source_row_id=str(record[4]),
                ),
                ordered_by=ExecutionValue(
                    field_id=ordered.semantic_id,
                    value=record[5],
                    effective_as_of=record[6],
                    source_id=str(record[7]),
                    source_row_id=str(record[8]),
                ),
            )
            for record in records
        )
        observed = int(first[9])
        coverage = self._coverage(dataset, ordered, observed)
        return TypedExecutionResult(
            status=ExecutionStatus.EXECUTED,
            query=query,
            rows=rows,
            sources=source_result,
            freshness=FreshnessMetadata(
                requested_as_of=query.requested_as_of,
                effective_as_of_min=first[13],
                effective_as_of_max=first[14],
                distinct_effective_as_of=1,
                unknown_effective_as_of_count=0,
                status=(
                    FreshnessStatus.EXACT_REQUESTED
                    if query.requested_as_of is not None
                    else FreshnessStatus.LATEST_AVAILABLE
                ),
            ),
            coverage=coverage,
            applied_operations=(
                AppliedOperation(
                    operation=query.field_operation,
                    field_id=query.order_field_id,
                    direction=query.direction,
                    limit=query.limit,
                ),
            ),
        )

    @staticmethod
    def _snapshot_failure(
        query: ResolvedProductQuery, first: tuple[Any, ...]
    ) -> BindingFailure | None:
        display_min, display_max, display_unknown = first[10], first[11], int(first[12])
        order_min, order_max, order_unknown = first[13], first[14], int(first[15])
        mismatch = int(first[16])
        compatible = (
            display_unknown == 0
            and order_unknown == 0
            and display_min == display_max == order_min == order_max
            and mismatch == 0
        )
        if query.requested_as_of is not None:
            compatible = compatible and order_min == query.requested_as_of
        if compatible:
            return None
        return BindingFailure(
            code=BindingFailureCode.SNAPSHOT_INCOMPATIBLE,
            detail="display and order observations do not form one verified effective snapshot",
        )

    def _validated_sources(
        self,
        query: ResolvedProductQuery,
        registry: dict[str, Any],
        source_ids: set[str],
    ) -> tuple[SourceMetadata, ...] | TypedExecutionResult:
        source_index: dict[str, dict[str, Any]] = {}
        for source in registry["data_catalog"].get("sources") or []:
            if isinstance(source, dict) and isinstance(source.get("source_id"), str):
                source_index[str(source["source_id"])] = source
        if not source_ids or any(source_id not in source_index for source_id in source_ids):
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                BindingFailureCode.PROVENANCE_BINDING_UNAVAILABLE,
                "an observation source is not declared in the Registry",
            )
        if any(
            source_index[source_id].get("hash_matches") is not True
            or not source_index[source_id].get("sha256")
            for source_id in source_ids
        ):
            return self._failed(
                query,
                ExecutionStatus.UNAVAILABLE,
                BindingFailureCode.SOURCE_INTEGRITY_MISMATCH,
                "an observation source does not have a verified matching hash",
            )
        return tuple(self._source(source_index[source_id]) for source_id in sorted(source_ids))

    @staticmethod
    def _coverage(
        dataset: DatasetBinding, binding: BoundField, observed: int
    ) -> CoverageMetadata:
        population = dataset.population
        field = binding.observed_coverage
        dataset_total = population.get("subject_total")
        field_total = field.get("subject_total")
        totals = [value for value in (dataset_total, field_total) if isinstance(value, int)]
        total = totals[0] if totals and all(value == totals[0] for value in totals) else None
        missing = max(total - observed, 0) if total is not None else None
        required_zero = (
            "missing_subjects",
            "parse_failed_subjects",
            "collection_failure_count",
            "unknown_coverage_count",
        )
        explicit_zero = all(
            isinstance(container.get(key), int) and container[key] == 0
            for container in (population, field)
            for key in required_zero
        )
        explicit_full = (
            population.get("coverage_status") == "full"
            and field.get("coverage_status") == "full"
            and population.get("unknown_coverage") is False
            and field.get("unknown_coverage") is False
            and explicit_zero
            and total is not None
            and observed == total
        )
        unknown = (
            total is None
            or population.get("unknown_coverage") is not False
            or field.get("unknown_coverage") is not False
            or population.get("coverage_status") not in {"full", "partial"}
            or field.get("coverage_status") not in {"full", "partial"}
        )
        scope = CoverageScope.FULL if explicit_full else CoverageScope.UNKNOWN if unknown else CoverageScope.OBSERVED
        return CoverageMetadata(
            scope=scope,
            subject_total=total,
            observed_universe=observed,
            missing_subjects=missing,
            global_ranking_claim_allowed=explicit_full,
            basis="dataset population and field coverage declarations plus selected row count",
        )

    @staticmethod
    def _source(source: dict[str, Any]) -> SourceMetadata:
        return SourceMetadata(
            source_id=str(source["source_id"]),
            source_kind=str(source.get("source_kind") or ""),
            source_name=str(source.get("source_name") or ""),
            source_file=str(source.get("source_file") or ""),
            sha256=str(source["sha256"]),
            hash_matches=source.get("hash_matches"),
        )

    @staticmethod
    def _resolution_failure(
        query: ResolvedProductQuery,
        status: ExecutionStatus,
        failure: BindingFailure | None,
    ) -> TypedExecutionResult:
        assert failure is not None
        return TypedExecutionResult(status=status, query=query, binding_failures=(failure,))

    @staticmethod
    def _failed(
        query: ResolvedProductQuery,
        status: ExecutionStatus,
        code: BindingFailureCode,
        detail: str,
        role: str | None = None,
    ) -> TypedExecutionResult:
        return TypedExecutionResult(
            status=status,
            query=query,
            binding_failures=(BindingFailure(code=code, field_role=role, detail=detail),),
        )
