"""Deterministic candidate retrieval for the stage 1-A Runtime View experiment.

Experiment only. Retrieval reads the question text and the registry; it never
branches on a question id, a test id or a question string. Everything it knows
about meaning — which words name which candidate, which candidates are confusion
neighbors of each other, which family owns what — comes from registry data.

Determinism is the point of this module. The same question and registry must
produce the same admitted candidates in the same order on every run, so the
order the model sees can be held fixed while its behaviour is measured
(``FINDINGS_REVISED.md`` section 4 showed order changes results).
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from .registry import Registry, capability_form_index, surface_form_index

# Why a candidate is in the view. Diagnostic vocabulary, not data.
REASON_SURFACE_MATCH = "surface_match"
REASON_SAME_NEIGHBOR_GROUP = "same_neighbor_group"
REASON_CROSS_FAMILY_HOMONYM = "cross_family_homonym"
REASON_PREDICATE_SIBLING = "predicate_sibling"
REASON_DATASET_OWNERSHIP = "dataset_ownership"

# Ranking tiers. Datasets come first because every other candidate is read
# relative to the family that owns it; a directly named candidate outranks a
# neighbor that was only pulled in for contrast.
TIER_DATASET = 0
TIER_DIRECT = 1
TIER_NEIGHBOR = 2

TRUNCATION_DEPENDENCY = "owning_dataset_truncated"
TRUNCATION_BUDGET = "budget_exhausted"


class ScoredCandidate(BaseModel):
    """One candidate considered for a request, with why and how strongly."""

    model_config = ConfigDict(frozen=True)

    semantic_id: str
    kind: str
    tier: int
    best_form_length: int = 0
    matched_form_count: int = 0
    reasons: tuple[str, ...] = ()

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        return (
            self.tier,
            -self.best_form_length,
            -self.matched_form_count,
            self.semantic_id,
        )

    def directly_matched(self) -> bool:
        return REASON_SURFACE_MATCH in self.reasons


class TruncatedCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    semantic_id: str
    kind: str
    tier: int
    reason: str
    directly_matched: bool


class RetrievalResult(BaseModel):
    """What a question retrieved from the registry, before refs are minted."""

    model_config = ConfigDict(frozen=True)

    admitted: tuple[ScoredCandidate, ...]
    truncated: tuple[TruncatedCandidate, ...]
    matched_capability_ids: tuple[str, ...]
    candidate_budget: int

    def admitted_ids(self) -> tuple[str, ...]:
        return tuple(candidate.semantic_id for candidate in self.admitted)

    def admitted_of_kind(self, kind: str) -> tuple[ScoredCandidate, ...]:
        return tuple(candidate for candidate in self.admitted if candidate.kind == kind)

    def truncated_ids(self) -> tuple[str, ...]:
        return tuple(candidate.semantic_id for candidate in self.truncated)

    def reason_for(self, semantic_id: str) -> tuple[str, ...]:
        for candidate in self.admitted:
            if candidate.semantic_id == semantic_id:
                return candidate.reasons
        return ()


def lexical_matches(registry: Registry, question: str) -> dict[str, tuple[int, int]]:
    """Return ``semantic_id -> (longest matched form, matched form count)``.

    Substring matching over normalized text is deliberate: Korean questions
    inflect around the noun phrase, so a form is looked for inside the question
    rather than the question being split into tokens.
    """
    normalized_question = registry.normalize(question)
    matches: dict[str, tuple[int, int]] = {}
    for form, semantic_id in surface_form_index(registry):
        if form not in normalized_question:
            continue
        longest, count = matches.get(semantic_id, (0, 0))
        matches[semantic_id] = (max(longest, len(form)), count + 1)
    return matches


def matched_capabilities(registry: Registry, question: str) -> tuple[str, ...]:
    """Capabilities the question asks for by name, in registry order."""
    normalized_question = registry.normalize(question)
    found = {
        capability_id
        for form, capability_id in capability_form_index(registry)
        if form in normalized_question
    }
    return tuple(
        capability.capability_id
        for capability in registry.capabilities
        if capability.capability_id in found
    )


def _neighbors(registry: Registry, seed_ids: Iterable[str]) -> dict[str, set[str]]:
    """Expand seeds one hop along the structural links the registry enabled.

    One hop only. Neighbours of neighbours would grow the view without making
    the seeded meaning easier to tell apart, and would stop being bounded.
    """
    enabled = set(registry.policy.neighbor_rules)
    seeds = [registry.entry(semantic_id) for semantic_id in seed_ids]
    found: dict[str, set[str]] = {}

    def add(semantic_id: str, reason: str) -> None:
        found.setdefault(semantic_id, set()).add(reason)

    for seed in seeds:
        for entry in registry.entries:
            if entry.semantic_id == seed.semantic_id:
                continue
            if (
                "same_neighbor_group" in enabled
                and seed.neighbor_group is not None
                and entry.neighbor_group == seed.neighbor_group
            ):
                add(entry.semantic_id, REASON_SAME_NEIGHBOR_GROUP)
            if (
                "cross_family_homonym" in enabled
                and entry.kind == seed.kind
                and registry.normalize(entry.label) == registry.normalize(seed.label)
                and entry.dataset_id != seed.dataset_id
            ):
                add(entry.semantic_id, REASON_CROSS_FAMILY_HOMONYM)
            if (
                "predicate_sibling" in enabled
                and seed.kind == "predicate"
                and entry.kind == "predicate"
                and seed.predicate_group is not None
                and entry.predicate_group == seed.predicate_group
            ):
                add(entry.semantic_id, REASON_PREDICATE_SIBLING)
    return found


def retrieve(
    registry: Registry,
    question: str,
    candidate_budget: int | None = None,
) -> RetrievalResult:
    """Retrieve a bounded, deterministically ordered candidate set."""
    budget = registry.policy.candidate_budget if candidate_budget is None else candidate_budget
    matches = lexical_matches(registry, question)

    scores: dict[str, dict[str, object]] = {}

    def record(semantic_id: str, reason: str) -> None:
        entry = registry.entry(semantic_id)
        state = scores.setdefault(
            semantic_id,
            {"kind": entry.kind, "reasons": set(), "best": 0, "count": 0},
        )
        reasons = state["reasons"]
        assert isinstance(reasons, set)
        reasons.add(reason)

    for semantic_id, (best, count) in matches.items():
        record(semantic_id, REASON_SURFACE_MATCH)
        scores[semantic_id]["best"] = best
        scores[semantic_id]["count"] = count

    for semantic_id, reasons in _neighbors(registry, sorted(matches)).items():
        for reason in sorted(reasons):
            record(semantic_id, reason)

    # Ownership closure: a candidate is unreadable without the family it belongs
    # to, so every owning dataset joins the view even when nothing named it.
    for semantic_id in sorted(scores):
        for dataset_id in registry.family_ids(semantic_id):
            if dataset_id not in scores:
                record(dataset_id, REASON_DATASET_OWNERSHIP)

    scored = [
        ScoredCandidate(
            semantic_id=semantic_id,
            kind=str(state["kind"]),
            tier=_tier_of(str(state["kind"]), set(state["reasons"])),  # type: ignore[arg-type]
            best_form_length=int(state["best"]),  # type: ignore[arg-type]
            matched_form_count=int(state["count"]),  # type: ignore[arg-type]
            reasons=tuple(sorted(state["reasons"])),  # type: ignore[arg-type]
        )
        for semantic_id, state in scores.items()
    ]
    ranked = sorted(scored, key=lambda candidate: candidate.sort_key)

    admitted: list[ScoredCandidate] = []
    truncated: list[TruncatedCandidate] = []
    admitted_ids: set[str] = set()
    for candidate in ranked:
        owners = tuple(
            owner
            for owner in registry.family_ids(candidate.semantic_id)
            if owner != candidate.semantic_id
        )
        if owners and not _ownership_satisfied(candidate.kind, owners, admitted_ids):
            truncated.append(_truncate(candidate, TRUNCATION_DEPENDENCY))
            continue
        if len(admitted) >= budget:
            truncated.append(_truncate(candidate, TRUNCATION_BUDGET))
            continue
        admitted.append(candidate)
        admitted_ids.add(candidate.semantic_id)

    return RetrievalResult(
        admitted=tuple(admitted),
        truncated=tuple(truncated),
        matched_capability_ids=matched_capabilities(registry, question),
        candidate_budget=budget,
    )


def _ownership_satisfied(kind: str, owners: tuple[str, ...], admitted_ids: set[str]) -> bool:
    """Whether a candidate's family context survived the budget.

    A field or a bound entity has exactly one family and is meaningless without
    it. A predicate is scoped to several families and stays readable as long as
    one of them is in the view; the view then states which ones it applies to.
    """
    if kind == "predicate":
        return any(owner in admitted_ids for owner in owners)
    return all(owner in admitted_ids for owner in owners)


def _tier_of(kind: str, reasons: set[str]) -> int:
    if kind == "dataset":
        return TIER_DATASET
    return TIER_DIRECT if REASON_SURFACE_MATCH in reasons else TIER_NEIGHBOR


def _truncate(candidate: ScoredCandidate, reason: str) -> TruncatedCandidate:
    return TruncatedCandidate(
        semantic_id=candidate.semantic_id,
        kind=candidate.kind,
        tier=candidate.tier,
        reason=reason,
        directly_matched=candidate.directly_matched(),
    )
