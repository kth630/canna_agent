"""Registry-owned candidate semantics for the stage 1-A Runtime View experiment.

Experiment only. This module is a reader and validator: every alias, label,
meaning, dataset binding, neighbor grouping and capability classification is
supplied by the caller as registry data. ``ARCHITECTURE.md`` section 7 makes the
registry the source of truth for semantics, so nothing here may restate a
field, predicate, product family or surface form as a Python constant.

The only vocabulary owned by this module is structural: which candidate kinds
exist (``ARCHITECTURE.md`` section 3) and which structural links retrieval knows
how to follow. A registry that names an unknown link is rejected at load time
rather than silently losing an expansion rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

CandidateKind = Literal["dataset", "field", "predicate", "entity"]
CANDIDATE_KINDS: tuple[str, ...] = ("dataset", "field", "predicate", "entity")

# Structural links retrieval can follow. The registry chooses which of these to
# enable; the mechanism lives in ``retrieval.py``.
NEIGHBOR_RULES: tuple[str, ...] = (
    "same_neighbor_group",
    "cross_family_homonym",
    "predicate_sibling",
)


class RegistryError(ValueError):
    """A registry that cannot be trusted to describe candidate semantics."""


class Normalization(BaseModel):
    """How question text and surface forms are compared.

    Owned by the registry because it is a property of the language the surface
    forms are written in, not of the retrieval mechanism.
    """

    model_config = ConfigDict(frozen=True)

    casefold: bool = True
    strip_characters: str = ""

    def apply(self, text: str) -> str:
        normalized = text.casefold() if self.casefold else text
        if self.strip_characters:
            table = {ord(character): None for character in self.strip_characters}
            normalized = normalized.translate(table)
        return normalized


class RetrievalPolicy(BaseModel):
    """Registry-declared retrieval budget and expansion rules."""

    model_config = ConfigDict(frozen=True)

    candidate_budget: int
    normalization: Normalization = Normalization()
    neighbor_rules: tuple[str, ...] = ()


class Capability(BaseModel):
    """A capability a product family either supports or does not.

    A capability with no surface form cannot be lexically requested; it is still
    classified per family so coverage stays a partition.
    """

    model_config = ConfigDict(frozen=True)

    capability_id: str
    label: str
    meaning: str
    surface_forms: tuple[str, ...] = ()


class CapabilityCoverage(BaseModel):
    """One product family's declared capability coverage and freshness."""

    model_config = ConfigDict(frozen=True)

    coverage_grain: str
    observed_universe: Mapping[str, object]
    freshness: Mapping[str, object]
    supported: tuple[str, ...]
    unsupported: tuple[str, ...]

    def classification(self, capability_id: str) -> str:
        if capability_id in self.supported:
            return "supported"
        if capability_id in self.unsupported:
            return "unsupported"
        raise RegistryError(f"capability not classified by this family: {capability_id}")


class RegistryEntry(BaseModel):
    """One candidate's semantics, independent of any request.

    The fields below are the discriminators ``QUESTION_STRUCTURE.md`` section 6
    requires a Runtime View candidate to carry. Which of them apply depends on
    ``kind``; an entry only fills what its kind has meaning for.
    """

    model_config = ConfigDict(frozen=True)

    semantic_id: str
    kind: CandidateKind
    label: str
    meaning: str
    surface_forms: tuple[str, ...] = ()
    dataset_id: str | None = None
    dataset_scope: tuple[str, ...] = ()
    neighbor_group: str | None = None
    predicate_group: str | None = None
    period: str | None = None
    unit: str | None = None
    currency: str | None = None
    grain: str | None = None
    source: str | None = None
    domain: str | None = None
    range: str | None = None
    subject_role: str | None = None
    object_role: str | None = None
    relation_mode: str | None = None
    entity_type: str | None = None
    identifier_scheme: str | None = None
    allowed_operations: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    capability_ids: tuple[str, ...] = ()
    capability_coverage: CapabilityCoverage | None = None

    def owning_dataset_ids(self) -> tuple[str, ...]:
        """Dataset ids this candidate cannot be understood without.

        A dataset owns itself, a field or bound entity owns its family, and a
        predicate needs every family it is scoped to so the view can say which
        families the relation is available for.
        """
        if self.kind == "dataset":
            return (self.semantic_id,)
        if self.dataset_scope:
            return self.dataset_scope
        if self.dataset_id:
            return (self.dataset_id,)
        return ()


def _sequence(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key) or ()
    if isinstance(value, str):
        raise RegistryError(f"{key} must be a list, not a string")
    return tuple(str(item) for item in value)


class Registry(BaseModel):
    """Validated candidate semantics plus the policy retrieval must obey."""

    model_config = ConfigDict(frozen=True)

    registry_id: str
    authority: str
    policy: RetrievalPolicy
    capabilities: tuple[Capability, ...]
    entries: tuple[RegistryEntry, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> Registry:
        policy_payload = payload.get("retrieval_policy")
        if not isinstance(policy_payload, Mapping):
            raise RegistryError("registry requires a retrieval_policy mapping")
        policy = RetrievalPolicy.model_validate(policy_payload)

        capabilities = tuple(
            Capability.model_validate(item) for item in _mappings(payload, "capabilities")
        )
        entries: list[RegistryEntry] = []
        for group, kind in (
            ("datasets", "dataset"),
            ("fields", "field"),
            ("predicates", "predicate"),
            ("entities", "entity"),
        ):
            for item in _mappings(payload, group):
                entries.append(_entry_from_mapping(item, kind))

        registry = cls(
            registry_id=str(payload.get("registry_id", "")),
            authority=str(payload.get("authority", "")),
            policy=policy,
            capabilities=capabilities,
            entries=tuple(entries),
        )
        registry.validate_consistency()
        return registry

    def validate_consistency(self) -> None:
        """Reject a registry whose candidates cannot be grounded.

        Build-time validation is the ``ARCHITECTURE.md`` section 7 rule applied
        to this experiment's single synthetic slice: an unknown reference is a
        deployment failure, not a runtime surprise.
        """
        problems: list[str] = []

        seen: set[str] = set()
        for entry in self.entries:
            if entry.semantic_id in seen:
                problems.append(f"duplicate semantic_id: {entry.semantic_id}")
            seen.add(entry.semantic_id)

        dataset_ids = {entry.semantic_id for entry in self.entries if entry.kind == "dataset"}
        capability_ids = {capability.capability_id for capability in self.capabilities}

        for rule in self.policy.neighbor_rules:
            if rule not in NEIGHBOR_RULES:
                problems.append(f"unknown neighbor rule: {rule}")
        if self.policy.candidate_budget < 1:
            problems.append("candidate_budget must be at least 1")

        for entry in self.entries:
            for dataset_id in entry.owning_dataset_ids():
                if dataset_id not in dataset_ids:
                    problems.append(f"{entry.semantic_id} references unknown dataset {dataset_id}")
            for capability_id in entry.capability_ids:
                if capability_id not in capability_ids:
                    problems.append(
                        f"{entry.semantic_id} references unknown capability {capability_id}"
                    )
            if entry.kind == "dataset":
                coverage = entry.capability_coverage
                if coverage is None:
                    problems.append(f"{entry.semantic_id} declares no capability coverage")
                    continue
                classified = set(coverage.supported) | set(coverage.unsupported)
                overlap = set(coverage.supported) & set(coverage.unsupported)
                if overlap:
                    problems.append(
                        f"{entry.semantic_id} classifies {sorted(overlap)} twice"
                    )
                unknown = classified - capability_ids
                if unknown:
                    problems.append(
                        f"{entry.semantic_id} classifies unknown capabilities {sorted(unknown)}"
                    )
                missing = capability_ids - classified
                if missing:
                    problems.append(
                        f"{entry.semantic_id} leaves {sorted(missing)} unclassified"
                    )

        if problems:
            raise RegistryError("; ".join(sorted(problems)))

    def entry(self, semantic_id: str) -> RegistryEntry:
        for entry in self.entries:
            if entry.semantic_id == semantic_id:
                return entry
        raise KeyError(semantic_id)

    def has(self, semantic_id: str) -> bool:
        return any(entry.semantic_id == semantic_id for entry in self.entries)

    def capability(self, capability_id: str) -> Capability:
        for capability in self.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise KeyError(capability_id)

    def entries_of_kind(self, kind: str) -> tuple[RegistryEntry, ...]:
        return tuple(entry for entry in self.entries if entry.kind == kind)

    def normalize(self, text: str) -> str:
        return self.policy.normalization.apply(text)

    def family_ids(self, semantic_id: str) -> tuple[str, ...]:
        return self.entry(semantic_id).owning_dataset_ids()


def _mappings(payload: Mapping[str, object], key: str) -> Sequence[Mapping[str, object]]:
    value = payload.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise RegistryError(f"{key} must be a list of objects")
    for item in value:
        if not isinstance(item, Mapping):
            raise RegistryError(f"{key} must contain objects")
    return value  # type: ignore[return-value]


def _entry_from_mapping(payload: Mapping[str, object], kind: str) -> RegistryEntry:
    coverage_payload = payload.get("capability_coverage")
    coverage = (
        CapabilityCoverage.model_validate(coverage_payload)
        if isinstance(coverage_payload, Mapping)
        else None
    )
    scalar_names = (
        "dataset_id",
        "neighbor_group",
        "predicate_group",
        "period",
        "unit",
        "currency",
        "grain",
        "source",
        "domain",
        "range",
        "subject_role",
        "object_role",
        "relation_mode",
        "entity_type",
        "identifier_scheme",
    )
    scalars = {
        name: (None if payload.get(name) is None else str(payload[name]))
        for name in scalar_names
        if name in payload
    }
    return RegistryEntry(
        semantic_id=str(payload["semantic_id"]),
        kind=kind,  # type: ignore[arg-type]
        label=str(payload["label"]),
        meaning=str(payload["meaning"]),
        surface_forms=_sequence(payload, "surface_forms"),
        dataset_scope=_sequence(payload, "dataset_scope"),
        allowed_operations=_sequence(payload, "allowed_operations"),
        evidence_requirements=_sequence(payload, "evidence_requirements"),
        capability_ids=_sequence(payload, "capability_ids"),
        capability_coverage=coverage,
        **scalars,  # type: ignore[arg-type]
    )


def load_registry(payload: Mapping[str, object]) -> Registry:
    """Public entry point so callers never build a Registry unvalidated."""
    return Registry.from_mapping(payload)


def surface_form_index(registry: Registry) -> tuple[tuple[str, str], ...]:
    """Return ``(normalized form, semantic_id)`` pairs in a deterministic order.

    Longer forms sort first so a caller that wants the most specific match can
    take it without re-sorting, and equal-length forms fall back to the semantic
    id to keep the order total.
    """
    pairs: list[tuple[str, str]] = []
    for entry in registry.entries:
        for form in entry.surface_forms:
            normalized = registry.normalize(form)
            if normalized:
                pairs.append((normalized, entry.semantic_id))
    return tuple(sorted(set(pairs), key=lambda pair: (-len(pair[0]), pair[0], pair[1])))


def capability_form_index(registry: Registry) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for capability in registry.capabilities:
        for form in capability.surface_forms:
            normalized = registry.normalize(form)
            if normalized:
                pairs.append((normalized, capability.capability_id))
    return tuple(sorted(set(pairs), key=lambda pair: (-len(pair[0]), pair[0], pair[1])))


def semantic_ids(entries: Iterable[RegistryEntry]) -> tuple[str, ...]:
    return tuple(entry.semantic_id for entry in entries)
