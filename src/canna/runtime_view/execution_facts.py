"""What the Execution Registry knows, read without being touched.

Whether a term can actually be executed is not knowable from the Semantic
Registry. The Registry says what a measure means; the Execution Registry says
which binding serves it, for which product family, at which grain, over how much
of the population and how stale. This layer owns neither, so it reads one and
asks the other.

The important correction is that a semantic ID does not have one binding. In the
shipped Execution Registry twenty-two of them have several — the same meaning
served for four product families, or twice within one family from two different
source columns. A contract that answered "the binding for this ID" would have to
pick one, and picking one silently is exactly the class of error this package
exists to stop. So there are two questions instead.

``candidate_bindings_for`` describes: it returns every binding, so a Runtime
View can show that a measure is served for three families and not a fourth.
``resolve_capability`` decides: it narrows by target family, grain, operation,
as-of and relationship kind, and hands back a binding only when exactly one
survives. None means unsupported or unavailable, more than one means ambiguous,
and both refuse rather than choose.

No physical table, column or join leaves this module. A binding's origin is
reported as the official source identifier the Data Catalog already publishes,
which names the provided dataset rather than the storage that holds it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

STATE_AVAILABLE = "available"
STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"

COVERAGE_FULL = "full"
COVERAGE_PARTIAL = "partial"
COVERAGE_OBSERVED = "observed"
COVERAGE_AMBIGUOUS = "ambiguous"

COVERAGE_MATCHED = "matched"
COVERAGE_NOT_FOUND = "unknown"
COVERAGE_MULTIPLE = "ambiguous"

KNOWLEDGE_KNOWN = "known"
KNOWLEDGE_PARTIAL = "partially_known"
KNOWLEDGE_NOT_EVALUATED = "not_evaluated"

AS_OF_UNKNOWN = "unknown"

RESOLUTION_RESOLVED = "resolved"
RESOLUTION_UNSUPPORTED = "unsupported"
RESOLUTION_UNAVAILABLE = "unavailable"
RESOLUTION_AMBIGUOUS = "ambiguous"

SOURCE_UNKNOWN = "unknown_source"


@dataclass(frozen=True)
class BindingSummary:
    """One way one meaning is actually served, described without physical detail."""

    semantic_id: str
    family_id: str
    subject_grain: str
    binding_kind: str = ""
    relation_kind: str = ""
    relation_direction: str = ""
    source_id: str = SOURCE_UNKNOWN
    semantic_operations: tuple[str, ...] = ()
    executable_operations: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    coverage_state: str = STATE_UNKNOWN
    coverage_resolution: str = COVERAGE_NOT_FOUND
    eligible_subjects: int | None = None
    attempted_subjects: int | None = None
    successful_subjects: int | None = None
    failed_subjects: int | None = None
    observed_subjects: int | None = None
    subject_total: int | None = None
    coverage_note: str = ""
    snapshot_state: str = STATE_UNKNOWN
    freshness_state: str = STATE_UNKNOWN
    effective_as_of_min: str = AS_OF_UNKNOWN
    effective_as_of_max: str = AS_OF_UNKNOWN
    holding_as_of_min: str = AS_OF_UNKNOWN
    holding_as_of_max: str = AS_OF_UNKNOWN
    as_of_status: str = AS_OF_UNKNOWN
    binding_available: bool = False

    def supports(self, operation: str) -> bool:
        return operation in self.executable_operations

    def covers_as_of(self, requested_as_of: str) -> bool:
        """Whether this binding's observed window can speak to that date."""
        if not requested_as_of:
            return True
        if AS_OF_UNKNOWN in (self.effective_as_of_min, self.effective_as_of_max):
            return False
        return self.effective_as_of_min <= requested_as_of <= self.effective_as_of_max

    def to_payload(self) -> dict[str, Any]:
        """The safe description: states and counts, never a table or a column."""
        return {
            "family_id": self.family_id,
            "subject_grain": self.subject_grain,
            "binding_kind": self.binding_kind,
            "relation_kind": self.relation_kind,
            "relation_direction": self.relation_direction,
            "source_id": self.source_id,
            "semantic_operations": list(self.semantic_operations),
            "executable_operations": list(self.executable_operations),
            "evidence_requirements": list(self.evidence_requirements),
            "coverage_state": self.coverage_state,
            "coverage_resolution": self.coverage_resolution,
            "eligible_subjects": self.eligible_subjects,
            "attempted_subjects": self.attempted_subjects,
            "successful_subjects": self.successful_subjects,
            "failed_subjects": self.failed_subjects,
            "observed_subjects": self.observed_subjects,
            "subject_total": self.subject_total,
            "coverage_note": self.coverage_note,
            "snapshot_state": self.snapshot_state,
            "freshness_state": self.freshness_state,
            "effective_as_of_min": self.effective_as_of_min,
            "effective_as_of_max": self.effective_as_of_max,
            "holding_as_of_min": self.holding_as_of_min,
            "holding_as_of_max": self.holding_as_of_max,
            "as_of_status": self.as_of_status,
            "binding_available": self.binding_available,
        }


@dataclass(frozen=True)
class TargetCapabilitySummary:
    """Family/grain execution facts for a dataset target, not a dataset binding.

    The Execution Registry binds fields and relations, not dataset classes.  A
    zero binding count therefore means only that no capability was described
    for this family/grain by the supplied adapter; it is not an unsupported
    verdict for the dataset.
    """

    family_id: str
    subject_grain: str
    safe_source_ids: tuple[str, ...] = ()
    binding_count: int = 0
    binding_operation_kinds: tuple[str, ...] = ()
    coverage_knowledge: str = KNOWLEDGE_NOT_EVALUATED
    freshness_knowledge: str = KNOWLEDGE_NOT_EVALUATED
    claim_readiness: str = KNOWLEDGE_NOT_EVALUATED

    def to_payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "subject_grain": self.subject_grain,
            "safe_source_ids": list(self.safe_source_ids),
            "binding_count": self.binding_count,
            "binding_operation_kinds": list(self.binding_operation_kinds),
            "coverage_knowledge": self.coverage_knowledge,
            "freshness_knowledge": self.freshness_knowledge,
            "claim_readiness": self.claim_readiness,
        }


@dataclass(frozen=True)
class CapabilityResolution:
    """Whether one candidate can serve one target, and by which single binding."""

    status: str
    reason: str
    considered: int = 0
    binding: BindingSummary | None = None
    alternatives: tuple[BindingSummary, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status == RESOLUTION_RESOLVED and self.binding is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "considered": self.considered,
            "binding": self.binding.to_payload() if self.binding else None,
            "alternatives": [item.to_payload() for item in self.alternatives],
        }


class ExecutionFacts(Protocol):
    """Describes candidates and resolves capabilities. Never chooses silently."""

    def candidate_bindings_for(self, semantic_id: str) -> tuple[BindingSummary, ...]: ...

    def target_capabilities_for(
        self, families: Sequence[str], grains: Sequence[str]
    ) -> tuple[TargetCapabilitySummary, ...]: ...

    def resolve_capability(
        self,
        target_semantic_id: str,
        candidate_semantic_id: str,
        operation: str,
        requested_as_of: str = "",
        relationship_kind: str = "",
    ) -> CapabilityResolution: ...


class NoExecutionFacts:
    """No adapter supplied. Nothing is described and nothing resolves."""

    def candidate_bindings_for(self, semantic_id: str) -> tuple[BindingSummary, ...]:
        return ()

    def target_capabilities_for(
        self, families: Sequence[str], grains: Sequence[str]
    ) -> tuple[TargetCapabilitySummary, ...]:
        return tuple(
            TargetCapabilitySummary(family_id=family, subject_grain=grain)
            for family in families
            for grain in grains
        )

    def resolve_capability(
        self,
        target_semantic_id: str,
        candidate_semantic_id: str,
        operation: str,
        requested_as_of: str = "",
        relationship_kind: str = "",
    ) -> CapabilityResolution:
        return CapabilityResolution(
            status=RESOLUTION_UNSUPPORTED,
            reason="no Execution Registry adapter is supplied to this request",
        )


def _text(value: Any, default: str = "") -> str:
    return str(value) if value not in (None, "") else default


def _sequence(value: Any) -> tuple[str, ...]:
    if not value or isinstance(value, str | bytes | Mapping):
        return ()
    return tuple(str(item) for item in value)


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _intersection(left: Sequence[str], right: Sequence[str]) -> tuple[str, ...]:
    allowed = {str(item) for item in right}
    return tuple(item for item in (str(value) for value in left) if item in allowed)


def _coverage_state(observed: int | None, total: int | None) -> str:
    if observed is None:
        return STATE_UNKNOWN
    if observed <= 0:
        return STATE_UNAVAILABLE
    if total is None or total <= 0:
        return COVERAGE_OBSERVED
    return COVERAGE_FULL if observed >= total else COVERAGE_PARTIAL


def _coverage_fields(coverage: Any) -> dict[str, Any]:
    """Read observed coverage without deciding what it means for a claim."""
    if not isinstance(coverage, Mapping):
        return {
            "coverage_state": STATE_UNKNOWN,
            "coverage_resolution": COVERAGE_NOT_FOUND,
            "eligible_subjects": None,
            "attempted_subjects": None,
            "successful_subjects": None,
            "failed_subjects": None,
            "observed_subjects": None,
            "subject_total": None,
            "coverage_note": "the Execution Registry records no observed coverage",
            "snapshot_state": STATE_UNKNOWN,
            "freshness_state": STATE_UNKNOWN,
            "effective_as_of_min": AS_OF_UNKNOWN,
            "effective_as_of_max": AS_OF_UNKNOWN,
            "holding_as_of_min": AS_OF_UNKNOWN,
            "holding_as_of_max": AS_OF_UNKNOWN,
            "as_of_status": AS_OF_UNKNOWN,
        }
    observed = _integer(coverage.get("valid_subjects", coverage.get("observed_subjects")))
    total = _integer(coverage.get("subject_total"))
    unknown_rows = coverage.get("unknown_as_of_rows") or 0
    as_of_min = _text(coverage.get("effective_as_of_min"), AS_OF_UNKNOWN)
    as_of_max = _text(coverage.get("effective_as_of_max"), AS_OF_UNKNOWN)
    return {
        "coverage_state": _coverage_state(observed, total),
        "coverage_resolution": COVERAGE_MATCHED,
        "eligible_subjects": None,
        "attempted_subjects": None,
        "successful_subjects": None,
        "failed_subjects": None,
        "observed_subjects": observed,
        "subject_total": total,
        "coverage_note": (
            "observed population only; excluded subjects are recorded by the "
            "Execution Registry"
        ),
        "freshness_state": (
            STATE_UNKNOWN if AS_OF_UNKNOWN in (as_of_min, as_of_max) else STATE_AVAILABLE
        ),
        "snapshot_state": STATE_UNKNOWN,
        "effective_as_of_min": as_of_min,
        "effective_as_of_max": as_of_max,
        "holding_as_of_min": AS_OF_UNKNOWN,
        "holding_as_of_max": AS_OF_UNKNOWN,
        "as_of_status": (
            "partially_unknown" if unknown_rows else ("known" if as_of_max != AS_OF_UNKNOWN else AS_OF_UNKNOWN)
        ),
    }


def _snapshot_state(coverage: Mapping[str, Any]) -> str:
    success = _integer(coverage.get("success_count"))
    full = _integer(coverage.get("full_snapshot_count"))
    partial = _integer(coverage.get("partial_snapshot_count"))
    unknown = _integer(coverage.get("unknown_snapshot_count"))
    if success == 0:
        return STATE_UNAVAILABLE
    if success is None or None in (full, partial, unknown):
        return STATE_UNKNOWN
    if unknown:
        return STATE_UNKNOWN
    if partial:
        return COVERAGE_PARTIAL
    if full == success and success > 0:
        return COVERAGE_FULL
    return STATE_UNKNOWN


def _holding_coverage_fields(
    matches: Sequence[Mapping[str, Any]], *, declared_sources: set[str]
) -> dict[str, Any]:
    if not matches:
        result = _coverage_fields(None)
        result["coverage_note"] = "no unique holdings coverage row matches this family"
        return result
    if len(matches) > 1:
        result = _coverage_fields(None)
        result["coverage_resolution"] = COVERAGE_MULTIPLE
        result["coverage_note"] = "multiple holdings coverage rows match this family"
        return result
    coverage = matches[0]
    eligible = _integer(coverage.get("eligible_count"))
    attempted = _integer(coverage.get("attempted_count"))
    success = _integer(coverage.get("success_count"))
    failed = _integer(coverage.get("failed_count"))
    observed = _integer(coverage.get("observed_subject_count"))
    snapshot = _snapshot_state(coverage)
    if success == 0 and (observed is None or observed == 0):
        state = STATE_UNAVAILABLE
    elif success is not None and success > 0:
        state = (
            COVERAGE_FULL
            if eligible is not None and success == eligible and snapshot == COVERAGE_FULL
            else COVERAGE_PARTIAL
        )
    elif observed is not None and observed > 0:
        state = COVERAGE_OBSERVED
    else:
        state = STATE_UNKNOWN
    holding_min = _text(coverage.get("holding_as_of_min"), AS_OF_UNKNOWN)
    holding_max = _text(coverage.get("holding_as_of_max"), AS_OF_UNKNOWN)
    return {
        "coverage_state": state,
        "coverage_resolution": COVERAGE_MATCHED,
        "eligible_subjects": eligible,
        "attempted_subjects": attempted,
        "successful_subjects": success,
        "failed_subjects": failed,
        "observed_subjects": observed,
        "subject_total": eligible,
        "coverage_note": _text(coverage.get("collection_scope_note")),
        "snapshot_state": snapshot,
        "freshness_state": (
            STATE_UNKNOWN
            if AS_OF_UNKNOWN in (holding_min, holding_max)
            else STATE_AVAILABLE
        ),
        "effective_as_of_min": (
            holding_min if coverage.get("as_of_role") == "effective" else AS_OF_UNKNOWN
        ),
        "effective_as_of_max": (
            holding_max if coverage.get("as_of_role") == "effective" else AS_OF_UNKNOWN
        ),
        "holding_as_of_min": holding_min,
        "holding_as_of_max": holding_max,
        "as_of_status": _text(coverage.get("as_of_role"), AS_OF_UNKNOWN),
        "source_id": (
            _text(coverage.get("source_id"))
            if _text(coverage.get("source_id")) in declared_sources
            else SOURCE_UNKNOWN
        ),
        "subject_grain": _text(coverage.get("subject_grain")),
    }


@dataclass
class ExecutionRegistryFacts:
    """A read-only projection of ``execution_registry.json``.

    The document is never written to and never modified. Family and grain for a
    query target come from the Semantic Registry, because the Execution Registry
    binds measures and relations rather than the classes they are measured on.
    """

    bindings_by_id: Mapping[str, tuple[BindingSummary, ...]] = field(default_factory=dict)
    target_families: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    target_grains: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        target_families: Mapping[str, Sequence[str]] | None = None,
        target_grains: Mapping[str, Sequence[str]] | None = None,
        semantic_operations: Mapping[str, Sequence[str]] | None = None,
    ) -> ExecutionRegistryFacts:
        source_rows = payload.get("data_catalog", {}).get("sources", ())
        sources = {
            str(row.get("source_id", "")).lower(): str(row.get("source_id", ""))
            for row in source_rows
            if isinstance(row, Mapping)
        }
        declared_sources = set(sources.values())
        allowed_by_id = {
            str(key): tuple(str(item) for item in value)
            for key, value in (semantic_operations or {}).items()
        }

        def source_id(table: str) -> str:
            key = table[4:].lower() if table.startswith("src_") else table.lower()
            return sources.get(key, SOURCE_UNKNOWN)

        grouped: dict[str, list[BindingSummary]] = {}
        for row in payload.get("bindings", ()):
            if not isinstance(row, Mapping):
                continue
            semantic_id = str(row.get("semantic_id", ""))
            allowed = allowed_by_id.get(semantic_id, ())
            executable = _intersection(allowed, _sequence(row.get("executable_operations")))
            physical = row.get("physical") or {}
            grouped.setdefault(semantic_id, []).append(
                BindingSummary(
                    semantic_id=semantic_id,
                    family_id=_text(row.get("family_id")),
                    subject_grain=_text(row.get("subject_grain")),
                    binding_kind=_text(row.get("binding_kind")),
                    source_id=source_id(str(physical.get("source_table", ""))),
                    semantic_operations=allowed,
                    executable_operations=executable,
                    evidence_requirements=_sequence(
                        (row.get("meaning") or {}).get("evidence_requirements")
                    ),
                    binding_available=True,
                    **_coverage_fields(row.get("observed_coverage")),
                )
            )
        coverage_by_family: dict[str, list[Mapping[str, Any]]] = {}
        for coverage in payload.get("holdings_coverage", ()):
            if not isinstance(coverage, Mapping):
                continue
            coverage_by_family.setdefault(_text(coverage.get("family_id")), []).append(coverage)
        for row in payload.get("relation_bindings", ()):
            if not isinstance(row, Mapping):
                continue
            semantic_id = str(row.get("semantic_id", ""))
            family_id = _text(row.get("family_id"))
            allowed = allowed_by_id.get(semantic_id, ())
            coverage = _holding_coverage_fields(
                coverage_by_family.get(family_id, ()), declared_sources=declared_sources
            )
            observed = row.get("observed") or {}
            grouped.setdefault(semantic_id, []).append(
                BindingSummary(
                    semantic_id=semantic_id,
                    family_id=family_id,
                    subject_grain=(
                        _text(coverage.pop("subject_grain", ""))
                        or _text(observed.get("subject_grain"), "product")
                    ),
                    relation_kind=_text(row.get("relation_kind")),
                    relation_direction=_text(row.get("direction")),
                    source_id=_text(coverage.pop("source_id", ""), SOURCE_UNKNOWN),
                    semantic_operations=allowed,
                    executable_operations=allowed if row.get("executable") else (),
                    evidence_requirements=_sequence(row.get("evidence_requirements")),
                    binding_available=bool(row.get("executable")),
                    **coverage,
                )
            )
        return cls(
            bindings_by_id={
                key: tuple(sorted(value, key=lambda item: (item.family_id, item.subject_grain, item.source_id)))
                for key, value in grouped.items()
            },
            target_families={
                str(key): tuple(str(item) for item in value)
                for key, value in (target_families or {}).items()
            },
            target_grains={
                str(key): tuple(str(item) for item in value)
                for key, value in (target_grains or {}).items()
            },
        )

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        target_families: Mapping[str, Sequence[str]] | None = None,
        target_grains: Mapping[str, Sequence[str]] | None = None,
        semantic_operations: Mapping[str, Sequence[str]] | None = None,
    ) -> ExecutionRegistryFacts:
        return cls.from_payload(
            json.loads(path.read_text(encoding="utf-8")),
            target_families=target_families,
            target_grains=target_grains,
            semantic_operations=semantic_operations,
        )

    def candidate_bindings_for(self, semantic_id: str) -> tuple[BindingSummary, ...]:
        return self.bindings_by_id.get(semantic_id, ())

    def target_capabilities_for(
        self, families: Sequence[str], grains: Sequence[str]
    ) -> tuple[TargetCapabilitySummary, ...]:
        all_bindings = tuple(
            row for rows in self.bindings_by_id.values() for row in rows
        )

        def knowledge(rows: Sequence[BindingSummary], attribute: str) -> str:
            if not rows:
                return KNOWLEDGE_NOT_EVALUATED
            known = sum(getattr(row, attribute) != STATE_UNKNOWN for row in rows)
            if known == len(rows):
                return KNOWLEDGE_KNOWN
            if known:
                return KNOWLEDGE_PARTIAL
            return KNOWLEDGE_NOT_EVALUATED

        summaries: list[TargetCapabilitySummary] = []
        for family in families:
            for grain in grains:
                rows = [
                    row
                    for row in all_bindings
                    if row.family_id == family and row.subject_grain == grain
                ]
                summaries.append(
                    TargetCapabilitySummary(
                        family_id=family,
                        subject_grain=grain,
                        safe_source_ids=tuple(
                            sorted(
                                {
                                    row.source_id
                                    for row in rows
                                    if row.source_id != SOURCE_UNKNOWN
                                }
                            )
                        ),
                        binding_count=len(rows),
                        binding_operation_kinds=tuple(
                            sorted(
                                {
                                    operation
                                    for row in rows
                                    for operation in row.executable_operations
                                }
                            )
                        ),
                        coverage_knowledge=knowledge(rows, "coverage_state"),
                        freshness_knowledge=knowledge(rows, "freshness_state"),
                    )
                )
        return tuple(summaries)

    def resolve_capability(
        self,
        target_semantic_id: str,
        candidate_semantic_id: str,
        operation: str,
        requested_as_of: str = "",
        relationship_kind: str = "",
    ) -> CapabilityResolution:
        """Exactly one binding, or a refusal that says which kind it is."""
        families = set(self.target_families.get(target_semantic_id, ()))
        grains = set(self.target_grains.get(target_semantic_id, ()))
        if not families:
            return CapabilityResolution(
                status=RESOLUTION_UNSUPPORTED,
                reason="the target's product family is not known to this adapter",
            )
        all_bindings = self.candidate_bindings_for(candidate_semantic_id)
        if not all_bindings:
            return CapabilityResolution(
                status=RESOLUTION_UNSUPPORTED,
                reason="the Execution Registry binds this meaning to nothing",
            )

        scoped = [item for item in all_bindings if item.family_id in families]
        if grains:
            scoped = [item for item in scoped if item.subject_grain in grains]
        if relationship_kind:
            scoped = [item for item in scoped if item.relation_kind == relationship_kind]
        if not scoped:
            return CapabilityResolution(
                status=RESOLUTION_UNSUPPORTED,
                reason="this meaning is not served for the target's family, grain or relation",
                considered=len(all_bindings),
            )

        usable = [item for item in scoped if item.binding_available and item.supports(operation)]
        if not usable:
            return CapabilityResolution(
                status=RESOLUTION_UNAVAILABLE,
                reason=f"no binding of this meaning supports {operation!r} for the target",
                considered=len(scoped),
                alternatives=tuple(scoped),
            )
        dated = [item for item in usable if item.covers_as_of(requested_as_of)]
        if not dated:
            return CapabilityResolution(
                status=RESOLUTION_UNAVAILABLE,
                reason="no binding covers the requested as-of date",
                considered=len(usable),
                alternatives=tuple(usable),
            )
        if len(dated) > 1:
            return CapabilityResolution(
                status=RESOLUTION_AMBIGUOUS,
                reason=(
                    "more than one binding of this meaning fits the target; the choice is "
                    "not this layer's to make"
                ),
                considered=len(dated),
                alternatives=tuple(dated),
            )
        return CapabilityResolution(
            status=RESOLUTION_RESOLVED,
            reason="exactly one binding fits the target, the operation and the as-of",
            considered=1,
            binding=dated[0],
        )


def bindings_or_empty(facts: ExecutionFacts | None, semantic_id: str) -> tuple[BindingSummary, ...]:
    if facts is None:
        return ()
    return tuple(facts.candidate_bindings_for(semantic_id))


def target_capabilities_or_not_evaluated(
    facts: ExecutionFacts | None, families: Sequence[str], grains: Sequence[str]
) -> tuple[TargetCapabilitySummary, ...]:
    if facts is not None and hasattr(facts, "target_capabilities_for"):
        return tuple(facts.target_capabilities_for(families, grains))
    return NoExecutionFacts().target_capabilities_for(families, grains)
