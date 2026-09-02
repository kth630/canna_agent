"""Fail-closed Execution Registry resolution for product fields."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from canna.execution.models import (
    BindingFailure,
    BindingFailureCode,
    ExecutionStatus,
    FieldOperation,
    ResolvedProductQuery,
)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RegistryFormatError(ValueError):
    """The Registry root cannot satisfy the execution contract."""


@dataclass(frozen=True)
class RowBinding:
    subject_column: str
    source_id_column: str
    source_row_id_column: str
    effective_as_of_column: str
    value_status_column: str
    valid_value_status: str


@dataclass(frozen=True)
class SelectionPolicy:
    kind: str
    snapshot_policy: str


@dataclass(frozen=True)
class BoundField:
    semantic_id: str
    family_id: str
    subject_grain: str
    observation_table: str
    selector_column: str
    selector_value: str
    value_column: str
    executable_operations: frozenset[str]
    observed_coverage: dict[str, Any]
    zero_semantics: str
    row: RowBinding
    selection: SelectionPolicy


@dataclass(frozen=True)
class DatasetBinding:
    family_id: str
    subject_grain: str
    population: dict[str, Any]


@dataclass(frozen=True)
class Resolution:
    status: ExecutionStatus
    binding: BoundField | None = None
    failure: BindingFailure | None = None


def load_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RegistryFormatError("Registry root must be an object")
    if not isinstance(payload.get("bindings"), list):
        raise RegistryFormatError("Registry bindings must be an array")
    if not isinstance(payload.get("data_catalog"), dict):
        raise RegistryFormatError("Registry data_catalog must be an object")
    return payload


def _failure(
    status: ExecutionStatus,
    code: BindingFailureCode,
    role: str,
    field_id: str,
    count: int | None,
    detail: str,
) -> Resolution:
    return Resolution(
        status=status,
        failure=BindingFailure(
            code=code,
            field_role=role,
            field_id=field_id,
            binding_count=count,
            detail=detail,
        ),
    )


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def resolve_dataset(
    registry: dict[str, Any], query: ResolvedProductQuery
) -> tuple[DatasetBinding | None, BindingFailure | None]:
    entries = registry.get("dataset_bindings")
    if not isinstance(entries, list):
        return None, BindingFailure(
            code=BindingFailureCode.DATASET_BINDING_UNAVAILABLE,
            detail="the Registry does not declare dataset population bindings",
        )
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("family_id") == query.dataset_family
        and entry.get("subject_grain") == query.result_grain.value
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("population"), dict):
        return None, BindingFailure(
            code=BindingFailureCode.DATASET_BINDING_UNAVAILABLE,
            detail="family and grain do not resolve to one dataset population binding",
        )
    match = matches[0]
    return (
        DatasetBinding(
            family_id=str(match["family_id"]),
            subject_grain=str(match["subject_grain"]),
            population=dict(match["population"]),
        ),
        None,
    )


def _row_binding(
    raw: dict[str, Any], role: str, field_id: str
) -> tuple[RowBinding | None, Resolution | None]:
    row = raw.get("row_binding")
    required = (
        "subject_column",
        "source_id_column",
        "source_row_id_column",
        "effective_as_of_column",
        "value_status_column",
    )
    if not isinstance(row, dict) or any(not _valid_identifier(row.get(key)) for key in required):
        return None, _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.PROVENANCE_BINDING_UNAVAILABLE,
            role,
            field_id,
            1,
            "row-level provenance and as-of columns are not fully declared",
        )
    valid_status = row.get("valid_value_status")
    if not isinstance(valid_status, str) or not valid_status:
        return None, _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.PROVENANCE_BINDING_UNAVAILABLE,
            role,
            field_id,
            1,
            "the valid observation status is not declared",
        )
    return (
        RowBinding(
            subject_column=str(row["subject_column"]),
            source_id_column=str(row["source_id_column"]),
            source_row_id_column=str(row["source_row_id_column"]),
            effective_as_of_column=str(row["effective_as_of_column"]),
            value_status_column=str(row["value_status_column"]),
            valid_value_status=valid_status,
        ),
        None,
    )


def _selection_policy(
    raw: dict[str, Any], role: str, field_id: str, coverage: dict[str, Any]
) -> tuple[SelectionPolicy | None, Resolution | None]:
    max_observations = coverage.get("max_observations_per_subject")
    if not isinstance(max_observations, int) or isinstance(max_observations, bool):
        return None, _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.SELECTION_POLICY_UNAVAILABLE,
            role,
            field_id,
            1,
            "max observations per subject is not explicitly declared",
        )
    policy = raw.get("selection_policy")
    if not isinstance(policy, dict):
        return None, _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.SELECTION_POLICY_UNAVAILABLE,
            role,
            field_id,
            1,
            "selection and snapshot policy are not declared",
        )
    kind = policy.get("kind")
    snapshot = policy.get("snapshot_policy")
    allowed = max_observations == 1 and kind == "unique_per_subject"
    allowed = allowed or (max_observations > 1 and kind == "latest_effective_as_of")
    if not allowed or snapshot != "single_effective_date":
        return None, _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.SELECTION_POLICY_UNAVAILABLE,
            role,
            field_id,
            1,
            "selection policy does not cover the observed multiplicity and snapshot requirement",
        )
    return SelectionPolicy(kind=str(kind), snapshot_policy=str(snapshot)), None


def resolve_field(
    registry: dict[str, Any],
    query: ResolvedProductQuery,
    field_id: str,
    role: str,
    required_operation: FieldOperation | None,
) -> Resolution:
    bindings = [
        binding
        for binding in registry["bindings"]
        if isinstance(binding, dict) and binding.get("semantic_id") == field_id
    ]
    if not bindings:
        return _failure(
            ExecutionStatus.UNSUPPORTED,
            BindingFailureCode.FIELD_NOT_REGISTERED,
            role,
            field_id,
            0,
            "the field has no Execution Registry binding",
        )
    family = [binding for binding in bindings if binding.get("family_id") == query.dataset_family]
    if not family:
        return _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.FAMILY_MISMATCH,
            role,
            field_id,
            0,
            "the field is not bound for the requested dataset family",
        )
    grain = [binding for binding in family if binding.get("subject_grain") == query.result_grain.value]
    if not grain:
        return _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.GRAIN_MISMATCH,
            role,
            field_id,
            0,
            "the field is not queryable at the requested result grain",
        )
    if len(grain) != 1:
        return _failure(
            ExecutionStatus.AMBIGUOUS,
            BindingFailureCode.MULTIPLE_BINDINGS,
            role,
            field_id,
            len(grain),
            "more than one binding matches family, grain and field",
        )
    raw = grain[0]
    if required_operation is not None and required_operation.value not in set(
        raw.get("executable_operations") or []
    ):
        return _failure(
            ExecutionStatus.UNSUPPORTED,
            BindingFailureCode.OPERATION_NOT_ALLOWED,
            role,
            field_id,
            1,
            "the matching binding does not allow the requested field operation",
        )
    identifier_keys = ("observation_table", "selector_column", "value_column")
    invalid = [key for key in identifier_keys if not _valid_identifier(raw.get(key))]
    if invalid:
        return _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.INVALID_REGISTRY_IDENTIFIER,
            role,
            field_id,
            1,
            "the Registry contains a non-allow-listed SQL identifier",
        )
    row, row_failure = _row_binding(raw, role, field_id)
    if row_failure is not None:
        return row_failure
    selector_scopes = {
        (str(candidate.get("family_id")), str(candidate.get("subject_grain")))
        for candidate in registry["bindings"]
        if isinstance(candidate, dict)
        and candidate.get("observation_table") == raw.get("observation_table")
        and candidate.get("selector_column") == raw.get("selector_column")
        and candidate.get("selector_value") == raw.get("selector_value")
    }
    if selector_scopes != {(query.dataset_family, query.result_grain.value)}:
        return _failure(
            ExecutionStatus.UNAVAILABLE,
            BindingFailureCode.BINDING_LAYOUT_UNAVAILABLE,
            role,
            field_id,
            1,
            "the Registry selector is not isolated to the requested dataset family",
        )
    coverage_raw = raw.get("observed_coverage")
    coverage = dict(coverage_raw) if isinstance(coverage_raw, dict) else {}
    selection, selection_failure = _selection_policy(raw, role, field_id, coverage)
    if selection_failure is not None:
        return selection_failure
    assert row is not None and selection is not None
    return Resolution(
        status=ExecutionStatus.EXECUTED,
        binding=BoundField(
            semantic_id=str(raw["semantic_id"]),
            family_id=str(raw["family_id"]),
            subject_grain=str(raw["subject_grain"]),
            observation_table=str(raw["observation_table"]),
            selector_column=str(raw["selector_column"]),
            selector_value=str(raw["selector_value"]),
            value_column=str(raw["value_column"]),
            executable_operations=frozenset(
                str(value) for value in raw.get("executable_operations") or []
            ),
            observed_coverage=coverage,
            zero_semantics=str(raw.get("zero_semantics") or "preserved"),
            row=row,
            selection=selection,
        ),
    )
