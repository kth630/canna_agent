"""Runtime View assembly with request-scoped opaque refs.

Experiment only. ``ARCHITECTURE.md`` section 4 requires refs to be minted per
request so the model cannot compose, memorise or guess a meaningful identifier.
This module therefore mints a fresh ref for every candidate on every request and
keeps the ``ref -> semantic_id`` map on the server side of the bundle; the
payload handed to a model contains no stable identifier of any kind — not a
semantic id, not a capability id, not a catalog handle.

Candidate order inside the view is the order retrieval ranked, so a repeated
request presents the same candidates in the same positions.
"""

from __future__ import annotations

import json
import random
import string
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from .registry import CANDIDATE_KINDS, Registry, RegistryEntry
from .retrieval import RetrievalResult

_REF_ALPHABET = string.ascii_lowercase + string.digits
_REF_LENGTH = 10


class RefMinter:
    """Mint collision-free refs that carry no type, order or meaning hint."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.SystemRandom()
        self._issued: set[str] = set()

    def mint(self) -> str:
        while True:
            ref = "".join(self._rng.choice(_REF_ALPHABET) for _ in range(_REF_LENGTH))
            if ref not in self._issued:
                self._issued.add(ref)
                return ref


class ViewCandidate(BaseModel):
    """One candidate as the view holds it: opaque ref plus discriminators."""

    model_config = ConfigDict(frozen=True)

    semantic_id: str
    kind: str
    ref: str
    payload: Mapping[str, object]


class RuntimeView(BaseModel):
    """The bounded candidate set offered for one request."""

    model_config = ConfigDict(frozen=True)

    datasets: tuple[ViewCandidate, ...]
    fields: tuple[ViewCandidate, ...]
    predicates: tuple[ViewCandidate, ...]
    entities: tuple[ViewCandidate, ...]

    def all_candidates(self) -> tuple[ViewCandidate, ...]:
        return self.datasets + self.fields + self.predicates + self.entities

    def presentation_order(self) -> tuple[str, ...]:
        return tuple(candidate.semantic_id for candidate in self.all_candidates())

    def refs(self) -> tuple[str, ...]:
        return tuple(candidate.ref for candidate in self.all_candidates())

    def contains(self, semantic_id: str) -> bool:
        return any(candidate.semantic_id == semantic_id for candidate in self.all_candidates())

    def as_prompt_payload(self) -> dict[str, object]:
        return {
            "dataset_candidates": [item.payload for item in self.datasets],
            "field_candidates": [item.payload for item in self.fields],
            "predicate_candidates": [item.payload for item in self.predicates],
            "entity_candidates": [item.payload for item in self.entities],
        }


class ViewMetrics(BaseModel):
    """Size of what reaches the model, per ``IMPLEMENTATION_PLAN.md`` stage 1."""

    model_config = ConfigDict(frozen=True)

    candidate_count: int
    candidate_count_by_kind: Mapping[str, int]
    serialized_bytes: int
    truncated_count: int


class RuntimeViewBundle(BaseModel):
    """View plus the server-side state a view must never hand to a model."""

    model_config = ConfigDict(frozen=True)

    view: RuntimeView
    semantic_id_by_ref: Mapping[str, str]
    metrics: ViewMetrics

    def ref_of(self, semantic_id: str) -> str | None:
        for ref, mapped in self.semantic_id_by_ref.items():
            if mapped == semantic_id:
                return ref
        return None


def build_view(
    registry: Registry,
    result: RetrievalResult,
    minter: RefMinter,
) -> RuntimeViewBundle:
    """Turn a retrieval result into a per-request Runtime View.

    Datasets are minted first so every other candidate can point at the
    request-scoped ref of the family that owns it, and so a predicate can list
    the families it applies to without naming them by a stable id.
    """
    ordered = result.admitted
    refs: dict[str, str] = {}
    for candidate in ordered:
        if candidate.kind == "dataset":
            refs[candidate.semantic_id] = minter.mint()
    for candidate in ordered:
        refs.setdefault(candidate.semantic_id, minter.mint())

    grouped: dict[str, list[ViewCandidate]] = {kind: [] for kind in CANDIDATE_KINDS}
    for candidate in ordered:
        entry = registry.entry(candidate.semantic_id)
        payload = _payload_for(registry, entry, refs)
        grouped[entry.kind].append(
            ViewCandidate(
                semantic_id=entry.semantic_id,
                kind=entry.kind,
                ref=refs[entry.semantic_id],
                payload=payload,
            )
        )

    view = RuntimeView(
        datasets=tuple(grouped["dataset"]),
        fields=tuple(grouped["field"]),
        predicates=tuple(grouped["predicate"]),
        entities=tuple(grouped["entity"]),
    )
    serialized = json.dumps(view.as_prompt_payload(), ensure_ascii=False, sort_keys=False)
    metrics = ViewMetrics(
        candidate_count=len(view.all_candidates()),
        candidate_count_by_kind={
            kind: len(grouped[kind]) for kind in CANDIDATE_KINDS
        },
        serialized_bytes=len(serialized.encode("utf-8")),
        truncated_count=len(result.truncated),
    )
    return RuntimeViewBundle(
        view=view,
        semantic_id_by_ref={ref: semantic_id for semantic_id, ref in refs.items()},
        metrics=metrics,
    )


def _payload_for(
    registry: Registry,
    entry: RegistryEntry,
    refs: Mapping[str, str],
) -> dict[str, object]:
    """Render one candidate for the model.

    Only meaning-bearing text and this request's refs go out. Semantic ids,
    capability ids and dataset ids stay behind; ownership travels as
    ``belongs_to_dataset_ref`` and scope as ``applies_to_dataset_refs``.
    """
    payload: dict[str, object] = {
        "ref": refs[entry.semantic_id],
        "label": entry.label,
        "meaning": entry.meaning,
    }
    if entry.dataset_id and entry.dataset_id in refs:
        payload["belongs_to_dataset_ref"] = refs[entry.dataset_id]
    scope_refs = [refs[dataset_id] for dataset_id in entry.dataset_scope if dataset_id in refs]
    if scope_refs:
        payload["applies_to_dataset_refs"] = scope_refs

    optional = {
        "period": entry.period,
        "unit": entry.unit,
        "currency": entry.currency,
        "grain": entry.grain,
        "source": entry.source,
        "domain": entry.domain,
        "range": entry.range,
        "subject_role": entry.subject_role,
        "object_role": entry.object_role,
        "relation_mode": entry.relation_mode,
        "entity_type": entry.entity_type,
        "identifier_scheme": entry.identifier_scheme,
    }
    payload.update({name: value for name, value in optional.items() if value is not None})
    if entry.allowed_operations:
        payload["allowed_operations"] = list(entry.allowed_operations)
    if entry.evidence_requirements:
        payload["evidence_requirements"] = list(entry.evidence_requirements)
    if entry.capability_coverage is not None:
        payload["capability_coverage"] = _coverage_payload(registry, entry)
    return payload


def _coverage_payload(registry: Registry, entry: RegistryEntry) -> dict[str, object]:
    """State this family's capability coverage in labels, not ids.

    Both halves of the partition are sent. An unsupported capability that is
    merely absent looks like a retrieval miss; named as unsupported, it is a
    coverage fact the reader can act on.
    """
    coverage = entry.capability_coverage
    assert coverage is not None
    return {
        "coverage_grain": coverage.coverage_grain,
        "observed_universe": dict(coverage.observed_universe),
        "freshness": dict(coverage.freshness),
        "supported_capabilities": [
            registry.capability(capability_id).label for capability_id in coverage.supported
        ],
        "unsupported_capabilities": [
            registry.capability(capability_id).label for capability_id in coverage.unsupported
        ],
    }
