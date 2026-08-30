"""Declared-source-type rules for the query store.

The rules map a *declared* source type to a physical DuckDB type and to a role
that decides which operations the Execution Registry may expose.  Nothing here
knows any field name, product, date or row count: a rule that only works for
today's official workbooks is a bug.
"""

from __future__ import annotations

import fnmatch
import re

NUMERIC_DECIMAL = re.compile(r"^numeric\((\d+),\s*(\d+)\)$")

MEASURE = "measure"
LABEL_OR_CODE = "label_or_code"
INTEGER_UNVERIFIED = "integer_unverified_zero_semantics"
DATE = "date"

RANKING_OPERATIONS = ("order", "min", "max", "avg", "sum")


def physical_type(declared: str) -> tuple[str, str, int | None]:
    """Map a declared source type to a DuckDB type, a role kind and its scale."""
    declared = declared.strip().lower()
    if declared == "text":
        return "VARCHAR", LABEL_OR_CODE, None
    if declared == "double precision":
        return "DOUBLE", MEASURE, None
    if declared == "bigint":
        return "BIGINT", INTEGER_UNVERIFIED, 0
    match = NUMERIC_DECIMAL.match(declared)
    if match:
        precision, scale = int(match.group(1)), int(match.group(2))
        kind = MEASURE if scale > 0 else INTEGER_UNVERIFIED
        return f"DECIMAL({precision},{scale})", kind, scale
    raise ValueError(f"unmapped declared type: {declared!r}")


def binding_type_role(declared_role: str, binding_role: str, value_slot: str) -> str:
    """Resolve the role that actually governs a binding in the derived store.

    A date-slot attribute is stored as a parsed DATE and a metric sourced from a
    text column is stored as a parsed DOUBLE, so both are ordered by the store
    even though their source column is text.  A scale-0 integer keeps its
    unverified zero semantics, because parsing does not tell us what 0 means.
    """
    if value_slot == "date":
        return DATE
    if binding_role == "metric" and declared_role == LABEL_OR_CODE:
        return MEASURE
    return declared_role


def allowed_operations(kind: str) -> list[str]:
    """Operations are derived from the declared type role, never per field."""
    if kind == DATE:
        return ["eq", "ne", "lt", "lte", "gt", "gte", "order", "min", "max", "count", "group"]
    if kind == MEASURE:
        return ["eq", "ne", "lt", "lte", "gt", "gte", "order", "min", "max", "avg", "sum", "count"]
    if kind == LABEL_OR_CODE:
        return ["eq", "ne", "in", "contains", "group", "count"]
    # Zero may be a legitimate code here, so ranking and aggregation stay closed
    # until the meaning of 0 is verified against an official source.
    return ["eq", "ne", "in", "count"]


def zero_semantics(kind: str) -> str:
    if kind == DATE:
        return "not_applicable"
    if kind == MEASURE:
        return "excluded_from_measure_population"
    return "preserved_pending_verification" if kind.startswith("integer") else "preserved"


def as_of_fields(note: str, order: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Resolve a recorded as-of note against real field names.

    The note mixes exact field names with recorded shorthand patterns such as
    ``*_base_dt``.  Expanding a recorded pattern literally is deterministic, so
    both forms are resolved, but the two origins stay distinguishable.
    """
    tokens = [token for token in re.findall(r"[A-Za-z0-9_*]+", note) if token]
    names = set(order)
    exact = [field for field in order if field in {t for t in tokens if "*" not in t} & names]
    patterns = [t for t in tokens if "*" in t]
    expanded = [
        field
        for field in order
        if field not in set(exact)
        and any(fnmatch.fnmatchcase(field, pattern) for pattern in patterns)
    ]
    return sorted(set(exact) | set(expanded)), exact, expanded


def normalized_date_expression(column: str) -> str:
    """SQL that turns a recorded date text into a DATE without inventing values.

    Only an unambiguous eight-digit calendar date is accepted; anything else
    stays NULL so the caller records an as-of status instead of a guess.
    """
    digits = f"regexp_replace({column}, '[^0-9]', '', 'g')"
    return f"CASE WHEN length({digits}) = 8 THEN TRY_STRPTIME({digits}, '%Y%m%d')::DATE END"
