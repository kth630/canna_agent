"""The Semantic Registry Retriever: rule and embedding candidates, merged.

The two paths run independently over the same approved vocabulary and are then
folded together by stable semantic id. Merging keeps both stories: a term found
by an exact label match and by embedding similarity carries one record per path,
each with the expression it matched, its score and its rank inside that path, so
recall can be attributed and neither path can be credited for the other's work.

What the Retriever will not do is decide. It produces no SQL, no physical
binding, no join and no execution plan; it does not run the Execution Registry;
and it never promotes a partial match or an embedding neighbour to a confirmed
meaning. The strongest thing it can say is that a question named an approved
term outright — and when two approved terms answer to the same name, it says
that too, and leaves the choice upstream.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from .candidates import (
    PATH_UNAVAILABLE,
    SOURCE_EMBEDDING,
    SOURCE_RULE,
    CandidateSource,
    PathReport,
    RetrievalCandidate,
    RetrievalResult,
    derive_status,
    find_ambiguous_expressions,
)
from .embedding import (
    ClovaStudioEmbeddings,
    CredentialsMissing,
    EmbeddingError,
    EmbeddingProvider,
    ProviderIdentity,
)
from .index import RetrievalIndex, assert_usable, load_index
from .normalize import normalization_contract, normalize
from .rules import RuleMatch
from .rules import search as rule_search
from .settings import RetrievalSettings, load_settings
from .vocabulary import Vocabulary, load_vocabulary

MERGED_SOURCE_ORDER = (SOURCE_RULE, SOURCE_EMBEDDING)


class Retriever:
    """Rule and embedding candidate generation over one Semantic Registry."""

    def __init__(
        self,
        vocabulary: Vocabulary,
        settings: RetrievalSettings,
        index: RetrievalIndex | None = None,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.vocabulary = vocabulary
        self.settings = settings
        self.index = index
        self.provider = provider
        if (index is None) != (provider is None):
            raise ValueError(
                "an embedding index and an embedding provider must be supplied together"
            )
        if index is not None and provider is not None:
            assert_usable(index, vocabulary, provider.identity)

    @property
    def embedding_enabled(self) -> bool:
        return self.index is not None and self.provider is not None

    @property
    def provider_identity(self) -> ProviderIdentity | None:
        return self.provider.identity if self.provider is not None else None

    def retrieve(self, question: str) -> RetrievalResult:
        started = time.perf_counter()
        normalized = normalize(question)
        by_id: dict[str, list[CandidateSource]] = {}
        paths: list[PathReport] = []

        rule_started = time.perf_counter()
        matches, rule_truncated = rule_search(self.vocabulary, question, self.settings.rule)
        rule_ms = (time.perf_counter() - rule_started) * 1000
        for rank, match in enumerate(matches, start=1):
            by_id.setdefault(match.semantic_id, []).append(_rule_source(match, rank))
        paths.append(
            PathReport(
                source=SOURCE_RULE,
                candidate_count=len(matches),
                latency_ms=rule_ms,
                truncated=rule_truncated,
                detail={
                    "tiers": _tier_counts(matches),
                    "grounding_eligible": sum(
                        1 for match in matches if match.grounding_eligible
                    ),
                    "normalization": normalization_contract(),
                },
            )
        )

        if self.embedding_enabled:
            embedding_started = time.perf_counter()
            try:
                paths.append(self._embedding_path(question, by_id))
            except EmbeddingError as error:
                paths.append(
                    PathReport(
                        source=SOURCE_EMBEDDING,
                        candidate_count=0,
                        latency_ms=(time.perf_counter() - embedding_started) * 1000,
                        availability=PATH_UNAVAILABLE,
                        unavailable_reason=(
                            "credentials_missing"
                            if isinstance(error, CredentialsMissing)
                            else "provider_error"
                        ),
                        detail={"error_type": type(error).__name__},
                    )
                )

        candidates = self._merge(by_id)
        ambiguous = find_ambiguous_expressions(candidates)
        status, reasons = derive_status(candidates, ambiguous)
        return RetrievalResult(
            question=question,
            normalized_question=normalized,
            status=status,
            reasons=reasons,
            candidates=candidates,
            ambiguous_expressions=ambiguous,
            paths=tuple(paths),
            settings_basis=self.settings.basis,
            registry_content_hash=self.vocabulary.content_hash,
            index_manifest=self.index.summary() if self.index is not None else {},
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _embedding_path(
        self, question: str, by_id: dict[str, list[CandidateSource]]
    ) -> PathReport:
        assert self.index is not None and self.provider is not None
        configuration = self.settings.embedding
        started = time.perf_counter()
        usage_before = _usage_snapshot(self.provider)
        vectors = self.provider.embed([question])
        if len(vectors) != 1:
            raise RuntimeError("the embedding provider did not return a query vector")
        scored = self.index.search(
            vectors[0],
            top_k=len(self.index.entries),
            threshold=configuration.similarity_threshold,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        usage = _usage_delta(usage_before, _usage_snapshot(self.provider))

        best: dict[str, tuple[float, str, str]] = {}
        for item in scored:
            current = best.get(item.entry.semantic_id)
            if current is None or item.similarity > current[0]:
                best[item.entry.semantic_id] = (
                    item.similarity,
                    item.entry.text,
                    item.entry.role,
                )
        ordered = sorted(best.items(), key=lambda item: (-item[1][0], item[0]))
        truncated = max(0, len(ordered) - configuration.top_k)
        for rank, (semantic_id, (similarity, text, role)) in enumerate(
            ordered[: configuration.top_k], start=1
        ):
            by_id.setdefault(semantic_id, []).append(
                CandidateSource(
                    source=SOURCE_EMBEDDING,
                    matched_expression=text,
                    matched_role=role,
                    score=similarity,
                    rank=rank,
                    # Similarity is a proposal. Only the rule path, and only its
                    # whole-form tiers, may mark a candidate groundable.
                    grounding_eligible=False,
                    detail={
                        "model": self.index.identity.model,
                        "distance_metric": self.index.identity.distance_metric,
                        "similarity_threshold": configuration.similarity_threshold,
                    },
                )
            )
        return PathReport(
            source=SOURCE_EMBEDDING,
            candidate_count=min(len(ordered), configuration.top_k),
            latency_ms=latency_ms,
            truncated=truncated,
            detail={
                "entries_scanned": len(self.index.entries),
                "entries_over_threshold": len(scored),
                "top_k": configuration.top_k,
                "similarity_threshold": configuration.similarity_threshold,
                "usage": usage,
            },
        )

    def _merge(
        self, by_id: dict[str, list[CandidateSource]]
    ) -> tuple[RetrievalCandidate, ...]:
        merged: list[RetrievalCandidate] = []
        for semantic_id, sources in by_id.items():
            term = self.vocabulary.term(semantic_id)
            ordered = tuple(
                sorted(
                    sources,
                    key=lambda source: (
                        MERGED_SOURCE_ORDER.index(source.source)
                        if source.source in MERGED_SOURCE_ORDER
                        else len(MERGED_SOURCE_ORDER),
                        source.rank,
                    ),
                )
            )
            merged.append(
                RetrievalCandidate(
                    semantic_id=semantic_id,
                    kind=term.kind,
                    preferred_label=term.preferred_label,
                    registry_content_hash=self.vocabulary.content_hash,
                    registry_evidence=dict(term.evidence),
                    sources=ordered,
                )
            )
        merged.sort(key=_merge_sort_key)
        return tuple(
            RetrievalCandidate(
                semantic_id=candidate.semantic_id,
                kind=candidate.kind,
                preferred_label=candidate.preferred_label,
                registry_content_hash=candidate.registry_content_hash,
                registry_evidence=candidate.registry_evidence,
                sources=candidate.sources,
                merged_rank=position,
            )
            for position, candidate in enumerate(merged, start=1)
        )


def _merge_sort_key(candidate: RetrievalCandidate) -> tuple[object, ...]:
    """Deterministic merged order.

    Groundable candidates lead because they are the only ones a downstream
    grounder may act on directly; everything after them is a proposal ordered by
    the strength of its own path. The semantic id breaks every remaining tie, so
    the same question and index always produce the same sequence.
    """
    rule = candidate.source(SOURCE_RULE)
    return (
        0 if candidate.grounding_eligible else 1,
        rule.rank if rule is not None else 1 << 20,
        -candidate.embedding_score,
        candidate.semantic_id,
    )


def _rule_source(match: RuleMatch, rank: int) -> CandidateSource:
    return CandidateSource(
        source=SOURCE_RULE,
        matched_expression=match.form.text,
        matched_role=match.form.role,
        score=match.score,
        rank=rank,
        match_tier=match.tier,
        matched_span=match.matched_span,
        grounding_eligible=match.grounding_eligible,
        detail={
            "locale": match.form.locale,
            "overlap_characters": match.overlap_characters,
            "form_characters": len(match.form.normalized),
        },
    )


def _tier_counts(matches: Sequence[RuleMatch]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in matches:
        counts[match.tier] = counts.get(match.tier, 0) + 1
    return dict(sorted(counts.items()))


def _usage_snapshot(provider: EmbeddingProvider) -> dict[str, int | float | bool]:
    usage = provider.usage
    return {
        "calls": usage.calls,
        "texts": usage.texts,
        "prompt_tokens": usage.prompt_tokens,
        "total_tokens": usage.total_tokens,
        "elapsed_ms": usage.elapsed_ms,
        "tokens_reported": usage.tokens_reported,
        "rate_limit_retries": usage.rate_limit_retries,
        "throttled_ms": usage.throttled_ms,
    }


def _usage_delta(
    before: dict[str, int | float | bool],
    after: dict[str, int | float | bool],
) -> dict[str, int | float | bool]:
    numeric = (
        "calls",
        "texts",
        "prompt_tokens",
        "total_tokens",
        "elapsed_ms",
        "rate_limit_retries",
        "throttled_ms",
    )
    delta = {key: after[key] - before[key] for key in numeric}
    delta["tokens_reported_by_provider"] = bool(after["tokens_reported"])
    return delta


def build_retriever(
    registry_path: Path | None = None,
    settings_path: Path | None = None,
    index_path: Path | None = None,
    provider: EmbeddingProvider | None = None,
    with_embedding: bool = True,
) -> Retriever:
    """Assemble the production Retriever.

    ``with_embedding`` false yields the rule path alone, which is a deliberate
    configuration and not a fallback: nothing here degrades to rules-only
    because a credential was missing or an API call failed. Those raise.
    """
    vocabulary = load_vocabulary(registry_path)
    settings = load_settings(settings_path)
    if not with_embedding:
        return Retriever(vocabulary, settings)
    embedding_provider = provider or ClovaStudioEmbeddings()
    index = load_index(index_path)
    return Retriever(vocabulary, settings, index, embedding_provider)
