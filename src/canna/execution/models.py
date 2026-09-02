"""Typed contract for the pre-CanonicalPlan product execution slice.

These models intentionally accept resolved semantic identifiers, not natural
language.  They are an internal execution result, not final Evidence.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Grain(StrEnum):
    PRODUCT = "product"
    PRODUCT_CLASS = "product_class"


class FieldOperation(StrEnum):
    ORDER = "order"


class OrderDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class ExecutionStatus(StrEnum):
    EXECUTED = "executed"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"


class BindingFailureCode(StrEnum):
    REGISTRY_UNAVAILABLE = "registry_unavailable"
    MALFORMED_REGISTRY = "malformed_registry"
    STORE_UNAVAILABLE = "store_unavailable"
    GENERATION_MISMATCH = "generation_mismatch"
    FIELD_NOT_REGISTERED = "field_not_registered"
    FAMILY_MISMATCH = "family_mismatch"
    GRAIN_MISMATCH = "grain_mismatch"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    MULTIPLE_BINDINGS = "multiple_bindings"
    INVALID_REGISTRY_IDENTIFIER = "invalid_registry_identifier"
    BINDING_LAYOUT_UNAVAILABLE = "binding_layout_unavailable"
    DATASET_BINDING_UNAVAILABLE = "dataset_binding_unavailable"
    PROVENANCE_BINDING_UNAVAILABLE = "provenance_binding_unavailable"
    SOURCE_INTEGRITY_MISMATCH = "source_integrity_mismatch"
    SELECTION_POLICY_UNAVAILABLE = "selection_policy_unavailable"
    SNAPSHOT_INCOMPATIBLE = "snapshot_incompatible"
    AS_OF_UNAVAILABLE = "as_of_unavailable"
    QUERY_FAILED = "query_failed"


class CoverageScope(StrEnum):
    FULL = "full"
    OBSERVED = "observed"
    UNKNOWN = "unknown"


class FreshnessStatus(StrEnum):
    EXACT_REQUESTED = "exact_requested"
    LATEST_AVAILABLE = "latest_available"
    MIXED_EFFECTIVE_DATES = "mixed_effective_dates"
    UNKNOWN_EFFECTIVE_DATE = "unknown_effective_date"


Limit = Annotated[int, Field(ge=1)]
ScalarValue = str | int | float | date | None


class ResolvedProductQuery(StrictModel):
    """A server-resolved request injected directly into this slice."""

    dataset_family: str = Field(min_length=1)
    result_grain: Grain
    display_field_id: str = Field(min_length=1)
    order_field_id: str = Field(min_length=1)
    field_operation: FieldOperation
    direction: OrderDirection
    limit: Limit
    requested_as_of: date | None = None


class BindingFailure(StrictModel):
    code: BindingFailureCode
    field_role: str | None = None
    field_id: str | None = None
    binding_count: int | None = None
    detail: str


class AppliedOperation(StrictModel):
    operation: FieldOperation
    field_id: str
    direction: OrderDirection
    limit: int


class ExecutionValue(StrictModel):
    field_id: str
    value: ScalarValue
    effective_as_of: date | None
    source_id: str
    source_row_id: str


class ProductExecutionRow(StrictModel):
    subject_key: str
    display: ExecutionValue | None
    ordered_by: ExecutionValue


class SourceMetadata(StrictModel):
    source_id: str
    source_kind: str
    source_name: str
    source_file: str
    sha256: str
    hash_matches: bool | None


class FreshnessMetadata(StrictModel):
    requested_as_of: date | None
    effective_as_of_min: date | None
    effective_as_of_max: date | None
    distinct_effective_as_of: int
    unknown_effective_as_of_count: int
    status: FreshnessStatus


class CoverageMetadata(StrictModel):
    scope: CoverageScope
    subject_total: int | None
    observed_universe: int
    missing_subjects: int | None
    global_ranking_claim_allowed: bool
    basis: str


class TypedExecutionResult(StrictModel):
    """Execution-layer result.  Deliberately not named or typed as Evidence."""

    status: ExecutionStatus
    query: ResolvedProductQuery
    rows: tuple[ProductExecutionRow, ...] = ()
    sources: tuple[SourceMetadata, ...] = ()
    freshness: FreshnessMetadata | None = None
    coverage: CoverageMetadata | None = None
    applied_operations: tuple[AppliedOperation, ...] = ()
    binding_failures: tuple[BindingFailure, ...] = ()
