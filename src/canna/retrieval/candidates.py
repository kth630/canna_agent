"""The Retriever's output contract: candidates and nothing else.

What this contract deliberately cannot express is as much the point as what it
can. There is no field for a table, a column, a join, a SQL fragment or an
execution plan, so a downstream reader cannot mistake a retrieved candidate for
something that is ready to run. Grounding is HCX's decision, validation and
compilation are the server's, and execution belongs to the Tools.

Three ideas are kept apart:

* ``sources`` — how a candidate was found, one record per retrieval path, with
  the expression that matched, its score and its rank within that path.
* ``registry_evidence`` — what the Semantic Registry says the term means, so
  two neighbouring candidates can be told apart without leaving this layer.
* ``grounding_eligible`` — whether a candidate reached the approved vocabulary
  by naming it whole. Partial matches and embedding neighbours never do.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .normalize import normalize

SOURCE_RULE = "rule"
SOURCE_EMBEDDING = "embedding"

STATUS_CANDIDATES = "candidates"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNRESOLVED = "unresolved"

REASON_NO_CANDIDATES = "no_candidates"
REASON_NO_GROUNDING_EVIDENCE = "no_grounding_evidence"
REASON_COMPETING_MEANINGS = "competing_meanings"

PATH_AVAILABLE = "available"
PATH_UNAVAILABLE = "unavailable"

# Keys that must never appear anywhere in a serialized retrieval result. The
# guard is structural rather than a matter of review discipline.
FORBIDDEN_PAYLOAD_KEYS = (
    "table",
    "column",
    "sql",
    "join",
    "physical_table",
    "physical_column",
    "execution_plan",
)


@dataclass(frozen=True)
class CandidateSource:
    """One retrieval path's evidence for one candidate."""

    source: str
    matched_expression: str
    matched_role: str
    score: float
    rank: int
    match_tier: str = ""
    matched_span: str = ""
    grounding_eligible: bool = False
    detail: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "matched_expression": self.matched_expression,
            "matched_role": self.matched_role,
            "match_tier": self.match_tier,
            "matched_span": self.matched_span,
            "score": round(self.score, 6),
            "rank": self.rank,
            "grounding_eligible": self.grounding_eligible,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class RetrievalCandidate:
    """A registry term a question may have named, with why and how strongly."""

    semantic_id: str
    kind: str
    preferred_label: str
    registry_content_hash: str
    registry_evidence: Mapping[str, object]
    sources: tuple[CandidateSource, ...]
    merged_rank: int = 0

    @property
    def grounding_eligible(self) -> bool:
        return any(source.grounding_eligible for source in self.sources)

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(sorted({source.source for source in self.sources}))

    def source(self, name: str) -> CandidateSource | None:
        for candidate_source in self.sources:
            if candidate_source.source == name:
                return candidate_source
        return None

    @property
    def best_rule_tier(self) -> str:
        rule = self.source(SOURCE_RULE)
        return rule.match_tier if rule else ""

    @property
    def rule_score(self) -> float:
        rule = self.source(SOURCE_RULE)
        return rule.score if rule else 0.0

    @property
    def embedding_score(self) -> float:
        embedding = self.source(SOURCE_EMBEDDING)
        return embedding.score if embedding else 0.0

    @property
    def grounding_expressions(self) -> tuple[str, ...]:
        return tuple(
            source.matched_expression for source in self.sources if source.grounding_eligible
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_id": self.semantic_id,
            "kind": self.kind,
            "preferred_label": self.preferred_label,
            "registry_content_hash": self.registry_content_hash,
            "merged_rank": self.merged_rank,
            "grounding_eligible": self.grounding_eligible,
            "sources": [source.to_dict() for source in self.sources],
            "registry_evidence": dict(self.registry_evidence),
        }


@dataclass(frozen=True)
class AmbiguousExpression:
    """One expression that named more than one meaning at grounding strength."""

    expression: str
    semantic_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"expression": self.expression, "semantic_ids": list(self.semantic_ids)}


@dataclass(frozen=True)
class PathReport:
    """What one retrieval path cost and produced, kept separable on purpose."""

    source: str
    candidate_count: int
    latency_ms: float
    availability: str = PATH_AVAILABLE
    unavailable_reason: str = ""
    truncated: int = 0
    detail: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "candidate_count": self.candidate_count,
            "latency_ms": round(self.latency_ms, 3),
            "availability": self.availability,
            "unavailable_reason": self.unavailable_reason,
            "truncated": self.truncated,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class RetrievalResult:
    """Everything one question retrieved, and nothing it decided."""

    question: str
    normalized_question: str
    status: str
    reasons: tuple[str, ...]
    candidates: tuple[RetrievalCandidate, ...]
    ambiguous_expressions: tuple[AmbiguousExpression, ...]
    paths: tuple[PathReport, ...]
    settings_basis: str
    registry_content_hash: str
    index_manifest: Mapping[str, object] = field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def grounding_eligible(self) -> tuple[RetrievalCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.grounding_eligible)

    @property
    def semantic_ids(self) -> tuple[str, ...]:
        return tuple(candidate.semantic_id for candidate in self.candidates)

    def candidate(self, semantic_id: str) -> RetrievalCandidate | None:
        for candidate in self.candidates:
            if candidate.semantic_id == semantic_id:
                return candidate
        return None

    def from_source(self, source: str) -> tuple[RetrievalCandidate, ...]:
        return tuple(
            candidate for candidate in self.candidates if source in candidate.source_names
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "normalized_question": self.normalized_question,
            "status": self.status,
            "reasons": list(self.reasons),
            "settings_basis": self.settings_basis,
            "registry_content_hash": self.registry_content_hash,
            "latency_ms": round(self.latency_ms, 3),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "ambiguous_expressions": [item.to_dict() for item in self.ambiguous_expressions],
            "paths": [path.to_dict() for path in self.paths],
            "index_manifest": dict(self.index_manifest),
        }


def derive_status(
    candidates: Sequence[RetrievalCandidate],
    ambiguous: Sequence[AmbiguousExpression],
) -> tuple[str, tuple[str, ...]]:
    """Fold candidates into a status without deciding any meaning.

    ``ambiguous`` is not a refusal and never hides candidates: it says the
    retrieved set does not by itself settle what was named, which is a fact
    about the evidence rather than a judgement about the question.
    """
    if not candidates:
        return STATUS_UNRESOLVED, (REASON_NO_CANDIDATES,)
    reasons: list[str] = []
    if not any(candidate.grounding_eligible for candidate in candidates):
        reasons.append(REASON_NO_GROUNDING_EVIDENCE)
    if ambiguous:
        reasons.append(REASON_COMPETING_MEANINGS)
    if reasons:
        return STATUS_AMBIGUOUS, tuple(reasons)
    return STATUS_CANDIDATES, ()


def find_ambiguous_expressions(
    candidates: Sequence[RetrievalCandidate],
) -> tuple[AmbiguousExpression, ...]:
    """Expressions that named more than one meaning at grounding strength."""
    by_expression: dict[str, set[str]] = {}
    display: dict[str, set[str]] = {}
    for candidate in candidates:
        for source in candidate.sources:
            if not source.grounding_eligible:
                continue
            key = normalize(source.matched_expression)
            if not key:
                continue
            by_expression.setdefault(key, set()).add(candidate.semantic_id)
            display.setdefault(key, set()).add(source.matched_expression)
    return tuple(
        AmbiguousExpression(
            min(display[key], key=lambda value: (len(value), value)),
            tuple(sorted(ids)),
        )
        for key, ids in sorted(by_expression.items())
        if len(ids) > 1
    )
