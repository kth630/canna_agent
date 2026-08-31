"""Registry-wide, question-free diagnostics for embedding configuration.

This is a structural experiment, not a gold natural-language benchmark.  Each
label, alias or definition is used as a leave-one-surface-form-out query; its
own vector is excluded, and the experiment measures whether another surface
form of the same stable semantic ID survives each threshold/top-k pair.  It
therefore tests the whole current Registry without inventing evaluation
questions, while explicitly not claiming that natural-question thresholds are
settled.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean
from typing import Any

from .index import RetrievalIndex
from .vocabulary import Vocabulary


def cross_form_sweep(
    vocabulary: Vocabulary,
    index: RetrievalIndex,
    *,
    thresholds: Sequence[float],
    top_ks: Sequence[int],
) -> dict[str, Any]:
    """Measure same-ID cross-form recall over every eligible index entry."""
    if not thresholds or not top_ks:
        raise ValueError("thresholds and top_ks must not be empty")
    if any(not -1.0 <= value <= 1.0 for value in thresholds):
        raise ValueError("thresholds must be cosine values")
    if any(value < 1 for value in top_ks):
        raise ValueError("top_ks must be positive")

    form_counts: dict[str, int] = {}
    for entry in index.entries:
        form_counts[entry.semantic_id] = form_counts.get(entry.semantic_id, 0) + 1
    queries = [entry for entry in index.entries if form_counts[entry.semantic_id] > 1]
    if not queries:
        raise ValueError("the index has no semantic ID with multiple embedded forms")

    rankings: list[tuple[str, list[tuple[str, float]]]] = []
    for query in queries:
        scored = index.search(
            index.vector_for_entry(query.entry_id),
            top_k=len(index.entries),
            threshold=-1.0,
        )
        best_by_id: dict[str, float] = {}
        for item in scored:
            if item.entry.entry_id == query.entry_id:
                continue
            previous = best_by_id.get(item.entry.semantic_id)
            if previous is None or item.similarity > previous:
                best_by_id[item.entry.semantic_id] = item.similarity
        ranked = sorted(best_by_id.items(), key=lambda item: (-item[1], item[0]))
        rankings.append((query.semantic_id, ranked))

    rows: list[dict[str, Any]] = []
    for threshold in sorted({float(value) for value in thresholds}):
        for top_k in sorted({int(value) for value in top_ks}):
            hits: list[float] = []
            reciprocal_ranks: list[float] = []
            candidate_counts: list[float] = []
            competing_counts: list[float] = []
            for expected_id, ranking in rankings:
                admitted = [item for item in ranking if item[1] >= threshold][:top_k]
                ids = [semantic_id for semantic_id, _score in admitted]
                hit = expected_id in ids
                hits.append(float(hit))
                reciprocal_ranks.append(1.0 / (ids.index(expected_id) + 1) if hit else 0.0)
                candidate_counts.append(float(len(ids)))
                competing_counts.append(float(len(ids) - int(hit)))
            rows.append(
                {
                    "similarity_threshold": threshold,
                    "top_k": top_k,
                    "same_semantic_id_recall": round(fmean(hits), 6),
                    "mean_reciprocal_rank": round(fmean(reciprocal_ranks), 6),
                    "mean_candidate_count": round(fmean(candidate_counts), 6),
                    "mean_competing_semantic_ids": round(fmean(competing_counts), 6),
                }
            )

    return {
        "experiment": "registry_cross_form_leave_one_out",
        "decision_status": "structural_evidence_only_not_product_settled",
        "registry_content_hash": vocabulary.content_hash,
        "index_generated_at": index.manifest.get("generated_at", ""),
        "provider": index.identity.to_dict(),
        "index_entry_count": len(index.entries),
        "query_entry_count": len(queries),
        "semantic_terms_evaluated": len({entry.semantic_id for entry in queries}),
        "method": (
            "exclude the query surface-form vector, collapse remaining entries by stable "
            "semantic ID, then sweep cosine threshold and semantic-ID top-k"
        ),
        "limitations": [
            "uses Registry-authored label/alias/definition text, not approved natural questions",
            "does not estimate unrelated-question false-positive rate",
            "does not justify a product threshold without downstream approved evaluation",
        ],
        "index_build_usage": index.manifest.get("usage", {}),
        "sweep": rows,
    }
