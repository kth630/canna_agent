"""Approval-gated natural-question evaluation for Semantic Registry retrieval.

The proposal file is provenance, not a product fixture.  This module only uses
it when the operator supplies an explicit user-approval reference. Reports omit
question text so neither provider-facing text nor local output logs become a
second question corpus.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, median
from typing import Any

from .embedding import EmbeddingProvider
from .index import RetrievalIndex, assert_usable
from .rules import search as rule_search
from .settings import RuleSettings
from .vocabulary import Vocabulary

RECALL_KS = (1, 3, 5, 10, 20)
ALLOWED_SECTIONS = {"clear", "unrelated", "ambiguous_diagnostic"}
ALLOWED_FAILURE_REASONS = {
    "registry_alias_gap",
    "label_definition_gap",
    "product_family_information_gap",
    "period_disambiguation_failure",
    "embedding_similarity_failure",
    "threshold_exclusion",
    "top_k_exclusion",
    "merge_deduplication_failure",
}
REQUIRED_CASE_FIELDS = {
    "test_purpose",
    "capability_under_test",
    "question_structure",
    "explicit_requirements",
    "semantic_clarity",
    "expected_semantic_ids",
    "expected_status",
    "failure_falsifies",
    "registry_evidence",
    "failure_analysis_hints",
}


class BenchmarkError(ValueError):
    """The benchmark input or approval boundary is invalid."""


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    section: str
    question: str
    expected_semantic_ids: frozenset[str]
    failure_analysis_hints: tuple[str, ...]


@dataclass(frozen=True)
class PreparedCase:
    case: EvaluationCase
    rule_ids: tuple[str, ...]
    grounding_rule_ids: tuple[str, ...]
    embedding_ranking: tuple[tuple[str, float], ...]
    latency_ms: float


def load_evaluation_proposal(
    path: Path,
    vocabulary: Vocabulary,
    *,
    approval_reference: str,
) -> tuple[dict[str, Any], tuple[EvaluationCase, ...]]:
    """Validate provenance and require an explicit approval reference."""
    if not approval_reference.strip():
        raise BenchmarkError(
            "an explicit --approval-reference is required; an unapproved proposal "
            "must not be used to establish model performance"
        )
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records or records[0].get("record_type") != "proposal_metadata":
        raise BenchmarkError("the first JSONL record must be proposal_metadata")
    metadata = dict(records[0])
    if metadata.get("registry_content_hash") != vocabulary.content_hash:
        raise BenchmarkError("evaluation proposal was authored against another Registry hash")
    question_pairs = [[row.get("case_id", ""), row.get("question", "")] for row in records[1:]]
    question_payload = json.dumps(
        question_pairs, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    actual_question_hash = hashlib.sha256(question_payload).hexdigest()
    if metadata.get("questions_sha256") != actual_question_hash:
        raise BenchmarkError("evaluation question text/order hash does not match proposal metadata")

    cases: list[EvaluationCase] = []
    seen: set[str] = set()
    for payload in records[1:]:
        if payload.get("record_type") != "evaluation_case":
            raise BenchmarkError("all records after metadata must be evaluation_case")
        case_id = str(payload.get("case_id", ""))
        section = str(payload.get("section", ""))
        clarity = str(payload.get("semantic_clarity", ""))
        question = str(payload.get("question", ""))
        expected = frozenset(str(value) for value in payload.get("expected_semantic_ids", []))
        hints = tuple(str(value) for value in payload.get("failure_analysis_hints", []))
        missing_fields = sorted(REQUIRED_CASE_FIELDS - payload.keys())
        if missing_fields:
            raise BenchmarkError(f"case {case_id} is missing metadata: {missing_fields}")
        if not case_id or case_id in seen:
            raise BenchmarkError(f"missing or duplicate case_id: {case_id!r}")
        if section not in ALLOWED_SECTIONS:
            raise BenchmarkError(f"unsupported section for {case_id}: {section!r}")
        if not question:
            raise BenchmarkError(f"case {case_id} has no question")
        if section == "ambiguous_diagnostic":
            if clarity != "materially_ambiguous" or len(expected) < 2:
                raise BenchmarkError(f"diagnostic case {case_id} must preserve multiple IDs")
        elif clarity != "explicit":
            raise BenchmarkError(f"non-diagnostic case {case_id} must be semantically explicit")
        if section == "unrelated" and expected:
            raise BenchmarkError(f"unrelated case {case_id} must have no expected IDs")
        if section == "clear" and not expected:
            raise BenchmarkError(f"clear case {case_id} must have an expected ID")
        unknown = sorted(value for value in expected if not vocabulary.has(value))
        if unknown:
            raise BenchmarkError(f"case {case_id} names unknown semantic IDs: {unknown}")
        evidence = payload.get("registry_evidence")
        if not isinstance(evidence, list):
            raise BenchmarkError(f"case {case_id} registry_evidence must be a list")
        unknown_evidence = sorted(
            {
                str(item.get("semantic_id", ""))
                for item in evidence
                if isinstance(item, Mapping)
                and item.get("semantic_id")
                and not vocabulary.has(str(item["semantic_id"]))
            }
        )
        if unknown_evidence:
            raise BenchmarkError(
                f"case {case_id} evidence names unknown semantic IDs: {unknown_evidence}"
            )
        invalid_hints = sorted(set(hints) - ALLOWED_FAILURE_REASONS)
        if invalid_hints:
            raise BenchmarkError(f"case {case_id} has invalid failure hints: {invalid_hints}")
        seen.add(case_id)
        cases.append(EvaluationCase(case_id, section, question, expected, hints))
    if not cases:
        raise BenchmarkError("the evaluation proposal contains no cases")
    metadata["approval_reference"] = approval_reference.strip()
    return metadata, tuple(cases)


def evaluate_model(
    vocabulary: Vocabulary,
    index: RetrievalIndex,
    provider: EmbeddingProvider,
    cases: Sequence[EvaluationCase],
    *,
    rule_settings: RuleSettings,
    thresholds: Sequence[float] | None = None,
    top_ks: Sequence[int] = RECALL_KS,
) -> dict[str, Any]:
    """Evaluate one model. Query text is sent only to the embedding provider."""
    assert_usable(index, vocabulary, provider.identity)
    prepared = tuple(
        _prepare_case(vocabulary, index, provider, case, rule_settings) for case in cases
    )
    threshold_values = (
        tuple(sorted({float(value) for value in thresholds}))
        if thresholds
        else _model_specific_thresholds(prepared)
    )
    ks = tuple(sorted({int(value) for value in top_ks}))
    if any(value < 1 for value in ks):
        raise BenchmarkError("top-k values must be positive")

    clear = tuple(item for item in prepared if item.case.section == "clear")
    diagnostics = tuple(
        item for item in prepared if item.case.section == "ambiguous_diagnostic"
    )
    unrelated = tuple(item for item in prepared if item.case.section == "unrelated")
    ranking_metrics = [_ranking_metrics(clear, k) for k in ks]
    sweep = [
        _sweep_row(clear, diagnostics, unrelated, threshold, k)
        for threshold in threshold_values
        for k in ks
    ]
    latencies = sorted(item.latency_ms for item in prepared)
    return {
        "model": index.identity.to_dict(),
        "registry_content_hash": vocabulary.content_hash,
        "index_generated_at": index.manifest.get("generated_at", ""),
        "case_counts": {
            "clear": len(clear),
            "unrelated": len(unrelated),
            "ambiguous_diagnostic": len(diagnostics),
        },
        "rule_only_recall": _recall(clear, lambda item: item.rule_ids),
        "rule_only_missing_case_ids": [
            item.case.case_id
            for item in clear
            if not item.case.expected_semantic_ids <= set(item.rule_ids)
        ],
        "ranking_metrics_without_threshold": ranking_metrics,
        "case_results": _case_results(prepared),
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
        },
        "threshold_basis": (
            "explicit_per_model_values" if thresholds else "per_model_observed_score_quantiles"
        ),
        "thresholds": list(threshold_values),
        "top_ks": list(ks),
        "sweep": sweep,
        "failure_analysis": _failure_analysis(clear),
        "question_text_in_report": False,
    }


def _case_results(prepared: Sequence[PreparedCase]) -> list[dict[str, Any]]:
    """Expose candidate IDs for review while deliberately omitting question text."""
    rows: list[dict[str, Any]] = []
    for item in prepared:
        embedding_top20 = [
            {
                "semantic_id": semantic_id,
                "score": round(score, 8),
                "rank": rank,
            }
            for rank, (semantic_id, score) in enumerate(item.embedding_ranking[:20], 1)
        ]
        embedding_ids = tuple(row["semantic_id"] for row in embedding_top20)
        merged_ids = _deduplicate((*item.rule_ids, *embedding_ids))[:20]
        rows.append(
            {
                "case_id": item.case.case_id,
                "section": item.case.section,
                "expected_semantic_ids": sorted(item.case.expected_semantic_ids),
                "rule_candidate_ids": list(item.rule_ids),
                "rule_grounding_ids": list(item.grounding_rule_ids),
                "embedding_top20": embedding_top20,
                "merged_top20_ids": list(merged_ids),
                "latency_ms": round(item.latency_ms, 3),
            }
        )
    return rows


def _prepare_case(
    vocabulary: Vocabulary,
    index: RetrievalIndex,
    provider: EmbeddingProvider,
    case: EvaluationCase,
    rule_settings: RuleSettings,
) -> PreparedCase:
    matches, _truncated = rule_search(vocabulary, case.question, rule_settings)
    rule_ids = _deduplicate(match.semantic_id for match in matches)
    grounding_ids = _deduplicate(
        match.semantic_id for match in matches if match.grounding_eligible
    )
    started = time.perf_counter()
    vectors = provider.embed([case.question])
    if len(vectors) != 1:
        raise BenchmarkError("embedding provider did not return exactly one query vector")
    scored = index.search(vectors[0], top_k=len(index.entries), threshold=-math.inf)
    best: dict[str, float] = {}
    for item in scored:
        prior = best.get(item.entry.semantic_id)
        if prior is None or item.similarity > prior:
            best[item.entry.semantic_id] = item.similarity
    ranking = tuple(sorted(best.items(), key=lambda item: (-item[1], item[0])))
    return PreparedCase(
        case=case,
        rule_ids=rule_ids,
        grounding_rule_ids=grounding_ids,
        embedding_ranking=ranking,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def _ranking_metrics(clear: Sequence[PreparedCase], top_k: int) -> dict[str, Any]:
    embedding_misses: list[str] = []
    merged_misses: list[str] = []
    for item in clear:
        embedding = tuple(value for value, _score in item.embedding_ranking[:top_k])
        merged = _deduplicate((*item.rule_ids, *embedding))[:top_k]
        if not item.case.expected_semantic_ids <= set(embedding):
            embedding_misses.append(item.case.case_id)
        if not item.case.expected_semantic_ids <= set(merged):
            merged_misses.append(item.case.case_id)
    return {
        "top_k": top_k,
        "embedding_only_recall": _recall(
            clear, lambda item: tuple(value for value, _score in item.embedding_ranking[:top_k])
        ),
        "merged_recall": _recall(
            clear,
            lambda item: _deduplicate(
                (*item.rule_ids, *(value for value, _score in item.embedding_ranking[:top_k]))
            )[:top_k],
        ),
        "embedding_missing_case_ids": embedding_misses,
        "merged_missing_case_ids": merged_misses,
    }


def _sweep_row(
    clear: Sequence[PreparedCase],
    diagnostics: Sequence[PreparedCase],
    unrelated: Sequence[PreparedCase],
    threshold: float,
    top_k: int,
) -> dict[str, Any]:
    embedding_lists = {
        item.case.case_id: tuple(
            semantic_id
            for semantic_id, score in item.embedding_ranking
            if score >= threshold
        )[:top_k]
        for item in (*clear, *diagnostics, *unrelated)
    }
    merged_lists = {
        item.case.case_id: _deduplicate(
            (*item.rule_ids, *embedding_lists[item.case.case_id])
        )[:top_k]
        for item in (*clear, *diagnostics, *unrelated)
    }
    counts = [len(merged_lists[item.case.case_id]) for item in clear]
    competing = [
        len(set(merged_lists[item.case.case_id]) - item.case.expected_semantic_ids)
        for item in clear
    ]
    ambiguous_preserved = [
        item.case.expected_semantic_ids <= set(merged_lists[item.case.case_id])
        for item in diagnostics
    ]
    unrelated_grounding = [
        item.case.case_id for item in unrelated if item.grounding_rule_ids
    ]
    missing = [
        item.case.case_id
        for item in clear
        if not item.case.expected_semantic_ids <= set(merged_lists[item.case.case_id])
    ]
    missing_analysis = _sweep_missing_analysis(
        clear, embedding_lists, merged_lists, threshold, top_k
    )
    return {
        "threshold": threshold,
        "top_k": top_k,
        "embedding_only_recall": _recall(
            clear, lambda item: embedding_lists[item.case.case_id]
        ),
        "merged_recall": _recall(clear, lambda item: merged_lists[item.case.case_id]),
        "missing_case_ids": missing,
        "missing_analysis": missing_analysis,
        "candidate_count": _distribution(counts),
        "mean_competing_ids_clear": round(fmean(competing), 6) if competing else 0.0,
        "ambiguous_required_set_preservation": (
            round(fmean(float(value) for value in ambiguous_preserved), 6)
            if ambiguous_preserved
            else None
        ),
        "unrelated_grounding_false_positive_count": len(unrelated_grounding),
        "unrelated_grounding_false_positive_case_ids": unrelated_grounding,
    }


def _sweep_missing_analysis(
    clear: Sequence[PreparedCase],
    embedding_lists: Mapping[str, tuple[str, ...]],
    merged_lists: Mapping[str, tuple[str, ...]],
    threshold: float,
    top_k: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in clear:
        ranks = {value: rank for rank, (value, _score) in enumerate(item.embedding_ranking, 1)}
        scores = dict(item.embedding_ranking)
        merged = set(merged_lists[item.case.case_id])
        admitted = set(embedding_lists[item.case.case_id])
        for semantic_id in sorted(item.case.expected_semantic_ids - merged):
            rank = ranks.get(semantic_id)
            score = scores.get(semantic_id)
            if score is not None and score < threshold:
                reason = "threshold_exclusion"
            elif rank is not None and rank > top_k:
                reason = "top_k_exclusion"
            elif semantic_id in admitted or semantic_id in item.rule_ids:
                reason = "merge_deduplication_failure"
            else:
                reason = "embedding_similarity_failure"
            rows.append(
                {
                    "case_id": item.case.case_id,
                    "semantic_id": semantic_id,
                    "reason": reason,
                    "embedding_rank": rank,
                    "embedding_score": score,
                    "human_review_hypotheses": list(item.case.failure_analysis_hints),
                }
            )
    return rows


def _failure_analysis(clear: Sequence[PreparedCase]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in clear:
        ranks = {value: rank for rank, (value, _score) in enumerate(item.embedding_ranking, 1)}
        scores = dict(item.embedding_ranking)
        merged = set(
            _deduplicate(
                (*item.rule_ids, *(value for value, _score in item.embedding_ranking[: max(RECALL_KS)])
            )
        )[: max(RECALL_KS)]
        )
        for semantic_id in sorted(item.case.expected_semantic_ids):
            rule_hit = semantic_id in item.rule_ids
            rank = ranks.get(semantic_id)
            if semantic_id in merged:
                continue
            automatic = (
                "top_k_exclusion"
                if rank is not None and rank > max(RECALL_KS)
                else (
                    "merge_deduplication_failure"
                    if rank is not None
                    else "embedding_similarity_failure"
                )
            )
            rows.append(
                {
                    "case_id": item.case.case_id,
                    "semantic_id": semantic_id,
                    "rule_hit": rule_hit,
                    "embedding_rank": rank,
                    "embedding_score": scores.get(semantic_id),
                    "automatic_retrieval_reason": automatic,
                    "human_review_hypotheses": list(item.case.failure_analysis_hints),
                    "registry_change_proposal_required": bool(
                        set(item.case.failure_analysis_hints)
                        & {
                            "registry_alias_gap",
                            "label_definition_gap",
                            "product_family_information_gap",
                        }
                    ),
                }
            )
    return rows


def _model_specific_thresholds(prepared: Sequence[PreparedCase]) -> tuple[float, ...]:
    scores = sorted(score for item in prepared for _semantic_id, score in item.embedding_ranking)
    if not scores:
        raise BenchmarkError("no embedding scores were produced")
    quantiles = (0.0, 0.25, 0.50, 0.75, 0.90, 0.95)
    return tuple(sorted({_percentile(scores, value) for value in quantiles}))


def _recall(
    cases: Sequence[PreparedCase],
    ids: Any,
) -> float | None:
    if not cases:
        return None
    return round(
        fmean(float(item.case.expected_semantic_ids <= set(ids(item))) for item in cases),
        6,
    )


def _distribution(values: Sequence[int]) -> dict[str, float | int]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "max": 0}
    return {
        "mean": round(fmean(values), 6),
        "median": float(median(values)),
        "max": max(values),
    }


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] * (1.0 - weight) + values[upper] * weight)


def _deduplicate(values: Sequence[str] | Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
