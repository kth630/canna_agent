"""The candidate pool one request is allowed to reason over.

The proposal's option generator consumes a Runtime View. This module turns the
two approved synthetic Runtime View sources into one shape so that the
generator can be written once, and -- this is the point -- it records which
prune axes each source actually *declared*. An axis a source is silent about is
not an axis that passes; it is an axis the generator has to refuse on, because
guessing a period, a unit or a relation's direction is the assumption the whole
contract exists to prevent.

No key, label, alias or binding is written here. Every one of them is read from
the fixture files that own them.

This module is experiment-only. It is not imported by any serving path,
it calls no provider, index or database, and nothing it produces is a
product contract.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KIND_DATASET = "dataset"
KIND_FIELD = "field"
KIND_PREDICATE = "predicate"
KIND_ENTITY = "entity"
KINDS = (KIND_DATASET, KIND_FIELD, KIND_PREDICATE, KIND_ENTITY)

# The prune axes section 6 of the proposal orders. A candidate that does not
# declare one cannot be pruned on it and cannot be silently kept either.
AXIS_TYPE = "type"
AXIS_FAMILY = "family"
AXIS_GRAIN = "grain"
AXIS_OPERATION = "operation"
AXIS_PERIOD = "period"
AXIS_UNIT = "unit"
AXIS_CURRENCY = "currency"
AXIS_DOMAIN_RANGE = "domain_range"
AXES = (
    AXIS_TYPE,
    AXIS_FAMILY,
    AXIS_GRAIN,
    AXIS_OPERATION,
    AXIS_PERIOD,
    AXIS_UNIT,
    AXIS_CURRENCY,
    AXIS_DOMAIN_RANGE,
)


class SourceError(ValueError):
    """A view source cannot be read into the common shape."""


@dataclass(frozen=True)
class ViewCandidate:
    """One Runtime View candidate, reduced to what an option may depend on."""

    key: str
    kind: str
    meaning: str
    surface_forms: tuple[str, ...]
    dataset_keys: tuple[str, ...]
    grains: tuple[str, ...]
    period: str
    unit: str
    currency: str
    allowed_operations: tuple[str, ...]
    subject_class: str
    object_class: str
    relation_mode: str
    entity_class: str
    role_nouns: tuple[str, ...]
    declared_axes: frozenset[str]
    coverage: Mapping[str, Any] = field(default_factory=dict)
    freshness: Mapping[str, Any] = field(default_factory=dict)

    def declares(self, axis: str) -> bool:
        return axis in self.declared_axes


@dataclass(frozen=True)
class ViewSource:
    """Everything one request may see, plus where it came from."""

    source_id: str
    authority: str
    candidates: tuple[ViewCandidate, ...]

    def of_kind(self, kind: str) -> tuple[ViewCandidate, ...]:
        return tuple(item for item in self.candidates if item.kind == kind)

    def get(self, key: str) -> ViewCandidate | None:
        return next((item for item in self.candidates if item.key == key), None)


def _text_sequence(value: Any) -> tuple[str, ...]:
    if not value or isinstance(value, str | bytes | Mapping):
        return ()
    return tuple(str(item) for item in value if str(item))


def _forms(*values: Any) -> tuple[str, ...]:
    seen: list[str] = []
    for value in values:
        if isinstance(value, str):
            candidates: Sequence[str] = (value,)
        else:
            candidates = _text_sequence(value)
        for item in candidates:
            text = item.strip()
            if text and text not in seen:
                seen.append(text)
    return tuple(seen)


def _axes_declared(row: Mapping[str, Any], kind: str) -> frozenset[str]:
    axes = {AXIS_TYPE}
    if kind == KIND_DATASET:
        axes.add(AXIS_FAMILY)
    if kind in (KIND_FIELD, KIND_PREDICATE) and (
        row.get("dataset_id") or row.get("dataset_key") or row.get("dataset_scope")
    ):
        axes.add(AXIS_FAMILY)
    if row.get("grain") or row.get("grains"):
        axes.add(AXIS_GRAIN)
    if row.get("allowed_operations"):
        axes.add(AXIS_OPERATION)
    if row.get("period"):
        axes.add(AXIS_PERIOD)
    if row.get("unit"):
        axes.add(AXIS_UNIT)
    if row.get("currency"):
        axes.add(AXIS_CURRENCY)
    if row.get("domain") and row.get("range"):
        axes.add(AXIS_DOMAIN_RANGE)
    return frozenset(axes)


def _candidate(key: str, kind: str, row: Mapping[str, Any]) -> ViewCandidate:
    dataset_keys = _forms(
        row.get("dataset_id") or "",
        row.get("dataset_key") or "",
        row.get("dataset_scope"),
    )
    coverage = dict(row.get("capability_coverage", {}) or {})
    return ViewCandidate(
        key=key,
        kind=kind,
        meaning=str(row.get("meaning", "") or ""),
        surface_forms=_forms(row.get("label"), row.get("surface_forms")),
        dataset_keys=dataset_keys,
        grains=_forms(row.get("grain"), row.get("grains")),
        period=str(row.get("period", "") or ""),
        unit=str(row.get("unit", "") or ""),
        currency=str(row.get("currency", "") or ""),
        allowed_operations=_text_sequence(row.get("allowed_operations")),
        subject_class=str(row.get("domain", "") or ""),
        object_class=str(row.get("range", "") or ""),
        relation_mode=str(row.get("relation_mode", "") or ""),
        role_nouns=_forms(row.get("subject_role"), row.get("object_role")),
        entity_class=str(row.get("entity_type", "") or row.get("grain", "") or ""),
        declared_axes=_axes_declared(row, kind),
        coverage=coverage,
        freshness=dict(coverage.get("freshness", {}) or {}),
    )


def load_view_source(path: Path) -> ViewSource:
    """Read either approved synthetic Runtime View shape into the common one."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    authority = str(payload.get("authority", "unknown"))
    rows: list[ViewCandidate] = []
    if "candidates" in payload:
        source_id = str(payload.get("catalog_id", Path(path).stem))
        for row in payload["candidates"]:
            kind = str(row.get("kind", ""))
            if kind not in KINDS:
                raise SourceError(f"unknown candidate kind in {Path(path).name}")
            rows.append(_candidate(str(row["catalog_key"]), kind, row))
    elif "datasets" in payload:
        source_id = str(payload.get("registry_id", Path(path).stem))
        for section, kind in (
            ("datasets", KIND_DATASET),
            ("fields", KIND_FIELD),
            ("predicates", KIND_PREDICATE),
            ("entities", KIND_ENTITY),
        ):
            for row in payload.get(section, ()):
                rows.append(_candidate(str(row["semantic_id"]), kind, row))
    else:
        raise SourceError(f"{Path(path).name} is neither approved view-source shape")
    if not rows:
        raise SourceError(f"{Path(path).name} declared no candidates")
    return ViewSource(source_id=source_id, authority=authority, candidates=tuple(rows))
