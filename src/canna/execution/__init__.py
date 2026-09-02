"""Deterministic, registry-bound offline product execution."""

from canna.execution.executor import ProductQueryExecutor
from canna.execution.models import (
    AppliedOperation,
    BindingFailure,
    BindingFailureCode,
    CoverageMetadata,
    CoverageScope,
    ExecutionStatus,
    FieldOperation,
    FreshnessMetadata,
    FreshnessStatus,
    Grain,
    OrderDirection,
    ProductExecutionRow,
    ResolvedProductQuery,
    SourceMetadata,
    TypedExecutionResult,
)

__all__ = [
    "AppliedOperation",
    "BindingFailure",
    "BindingFailureCode",
    "CoverageMetadata",
    "CoverageScope",
    "ExecutionStatus",
    "FieldOperation",
    "FreshnessMetadata",
    "FreshnessStatus",
    "Grain",
    "OrderDirection",
    "ProductExecutionRow",
    "ProductQueryExecutor",
    "ResolvedProductQuery",
    "SourceMetadata",
    "TypedExecutionResult",
]
