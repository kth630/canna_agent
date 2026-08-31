"""Composite-question retrieval evaluation: per candidate kind, not per question.

``benchmark`` answers one question about a question: were all expected semantic
IDs recovered?  A composite question needs a finer account, because a single
natural sentence names a product family, one or more measures and often a
relationship at once, and a single global top-k makes those candidate kinds
compete for the same seats.  Collapsing that into one boolean hides which kind
lost.

So this module keeps four things apart:

* ``required_candidates`` are recorded per kind, and recall is reported per kind
  as well as jointly, so "the relationship was dropped while the measures
  survived" is visible rather than averaged away.
* ``confusion_sets`` are *measured, never failed*.  A neighbouring term showing
  up as a candidate is correct behaviour; this layer proposes and does not
  confirm.  Both candidate-level and grounding-level counts are reported and
  the interpretation is left to human review.
* ``entity_mentions`` record that a question named a product or a security.
  The Registry holds semantic terms, not instances, so entity recall is
  structurally zero here.  That is a measured gap in a layer that does not
  exist yet, and it is excluded from joint recall rather than silently counted
  as a retrieval failure.
* ``execution_expectation`` records what the *execution* layer should do with a
  case.  It never affects a retrieval score: recovering the right candidate for
  a question the data cannot answer is a success of this layer.

Candidate-kind budgets are simulated offline over the same merged ordering.
Nothing here reads or writes the runtime retrieval configuration, and no
threshold or top-k in a report is a product setting.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import fmean
from typing import Any

from .embedding import EmbeddingProvider
from .index import RetrievalIndex, assert_usable
from .rules import search as rule_search
from .settings import RuleSettings
from .vocabulary import Vocabulary

# Candidate kinds are derived from the Registry's own term kinds so that a new
# Registry term is classified without touching this module.
KIND_DATASET = "dataset"
KIND_FIELD = "field"
KIND_PREDICATE = "predicate"
KIND_IDENTIFIER = "identifier"
KIND_OTHER = "other"

REGISTRY_KIND_TO_CANDIDATE_KIND = {
    "class": KIND_DATASET,
    "metric": KIND_FIELD,
    "attribute": KIND_FIELD,
    "data_property": KIND_FIELD,
    "predicate": KIND_PREDICATE,
    "identifier_scheme": KIND_IDENTIFIER,
    "shape": KIND_OTHER,
}

# ``entity`` is a fifth Runtime View kind with no Registry backing: it is
# declared here so a report can name the gap it measures.
KIND_ENTITY = "entity"
SCORED_KINDS = (KIND_DATASET, KIND_FIELD, KIND_PREDICATE, KIND_IDENTIFIER)

SECTION_CLEAR = "clear"
SECTION_COVERAGE_BOUNDARY = "coverage_boundary"
ALLOWED_SECTIONS = {SECTION_CLEAR, SECTION_COVERAGE_BOUNDARY}

ALLOWED_CONFUSION_CATEGORIES = {
    "family",
    "period",
    "relation_direction",
    "relation_kind",
    "metric_substitution",
}

ALLOWED_EXECUTION_EXPECTATIONS = {
    "executable",
    "blocked_entity_resolution",
    "refused_coverage",
    "refused_comparison_policy",
    "unresolved_absent_field",
}

REQUIRED_CASE_FIELDS = {
    "case_id",
    "section",
    "question",
    "test_purpose",
    "capability_under_test",
    "question_structure",
    "explicit_requirements",
    "semantic_clarity",
    "required_candidates",
    "equivalent_alternatives",
    "entity_mentions",
    "confusion_sets",
    "confusable_candidates_allowed",
    "coverage_notes",
    "expected_invariant",
    "falsifies_if",
    "execution_expectation",
    "natural_question_rationale",
}

RECALL_KS = (5, 10, 20, 30)


class CompositeError(ValueError):
    """The composite proposal or approval boundary is invalid."""


@dataclass(frozen=True)
class EntityMention:
    mention_role: str
    expected_resolution: str


@dataclass(frozen=True)
class CompositeCase:
    case_id: str
    section: str
    question: str
    required: Mapping[str, tuple[str, ...]]
    alternatives: Mapping[str, tuple[str, ...]]
    entity_mentions: tuple[EntityMention, ...]
    confusion_sets: Mapping[str, tuple[str, ...]]
    allowed_confusable: tuple[str, ...]
    execution_expectation: str

    @property
    def required_ids(self) -> tuple[str, ...]:
        return tuple(
            semantic_id for kind in SCORED_KINDS for semantic_id in self.required.get(kind, ())
        )

    def accepted_for(self, semantic_id: str) -> tuple[str, ...]:
        """A required ID plus any declared equivalent expression of it."""
        return (semantic_id, *self.alternatives.get(semantic_id, ()))


@dataclass(frozen=True)
class PreparedCase:
    case: CompositeCase
    rule_ids: tuple[str, ...]
    rule_grounding_ids: tuple[str, ...]
    rule_truncated: int
    embedding_ranking: tuple[tuple[str, float], ...]
    latency_ms: float
    kinds: Mapping[str, str] = field(default_factory=dict)

    def merged(self, top_k: int) -> tuple[str, ...]:
        """Rule candidates first, then embedding, deduplicated, then capped.

        An exact rule candidate is never displaced by an embedding neighbour;
        the cap can only remove what the embedding path proposed after every
        rule candidate has taken its seat.
        """
        embedding = tuple(semantic_id for semantic_id, _score in self.embedding_ranking)
        return _deduplicate((*self.rule_ids, *embedding))[:top_k]

    def embedding_ids(self, top_k: int) -> tuple[str, ...]:
        return tuple(semantic_id for semantic_id, _score in self.embedding_ranking[:top_k])


def candidate_kind(vocabulary: Vocabulary, semantic_id: str) -> str:
    if not vocabulary.has(semantic_id):
        return KIND_OTHER
    return REGISTRY_KIND_TO_CANDIDATE_KIND.get(vocabulary.term(semantic_id).kind, KIND_OTHER)


def registry_inverse_alternatives(vocabulary: Vocabulary, semantic_id: str) -> tuple[str, ...]:
    """Every predicate the Registry declares as this one's inverse, both ways.

    A question anchored on a security and the same question anchored on a
    product name the same relationship from opposite ends.  Which traversal
    direction executes is decided later, by the server, from predicate
    domain/range and the anchor entity type — so at candidate level either end
    of a declared inverse pair is the same recovered meaning.  The pairing is
    read from the Registry, never listed here.
    """
    if not vocabulary.has(semantic_id):
        return ()
    found: set[str] = set()
    declared = str(vocabulary.term(semantic_id).evidence.get("inverse_of", ""))
    if declared and vocabulary.has(declared):
        found.add(declared)
    for term in vocabulary.terms:
        if str(term.evidence.get("inverse_of", "")) == semantic_id:
            found.add(term.semantic_id)
    found.discard(semantic_id)
    return tuple(sorted(found))


def load_composite_proposal(
    path: Path,
    vocabulary: Vocabulary,
    *,
    approval_reference: str,
) -> tuple[dict[str, Any], tuple[CompositeCase, ...]]:
    """Validate provenance, approval and Registry membership before any call."""
    if not approval_reference.strip():
        raise CompositeError(
            "an explicit --approval-reference is required; an unapproved proposal "
            "must not be used to establish retrieval behaviour"
        )
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not records or records[0].get("record_type") != "proposal_metadata":
        raise CompositeError("the first JSONL record must be proposal_metadata")
    metadata = dict(records[0])
    if metadata.get("registry_content_hash") != vocabulary.content_hash:
        raise CompositeError("composite proposal was authored against another Registry hash")
    question_pairs = [[row.get("case_id", ""), row.get("question", "")] for row in records[1:]]
    payload = json.dumps(question_pairs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if metadata.get("questions_sha256") != hashlib.sha256(payload).hexdigest():
        raise CompositeError("question text/order hash does not match proposal metadata")

    cases: list[CompositeCase] = []
    seen: set[str] = set()
    for row in records[1:]:
        cases.append(_load_case(row, vocabulary, seen))
    if not cases:
        raise CompositeError("the composite proposal contains no cases")
    metadata["approval_reference"] = approval_reference.strip()
    return metadata, tuple(cases)


def _load_case(
    row: Mapping[str, Any], vocabulary: Vocabulary, seen: set[str]
) -> CompositeCase:
    if row.get("record_type") != "evaluation_case":
        raise CompositeError("all records after metadata must be evaluation_case")
    case_id = str(row.get("case_id", ""))
    missing = sorted(REQUIRED_CASE_FIELDS - row.keys())
    if missing:
        raise CompositeError(f"case {case_id} is missing metadata: {missing}")
    if not case_id or case_id in seen:
        raise CompositeError(f"missing or duplicate case_id: {case_id!r}")
    seen.add(case_id)
    section = str(row["section"])
    if section not in ALLOWED_SECTIONS:
        raise CompositeError(f"unsupported section for {case_id}: {section!r}")
    if str(row["semantic_clarity"]) != "explicit":
        raise CompositeError(f"case {case_id} must be semantically explicit")
    if not str(row["question"]).strip():
        raise CompositeError(f"case {case_id} has no question")
    expectation = str(row["execution_expectation"])
    if expectation not in ALLOWED_EXECUTION_EXPECTATIONS:
        raise CompositeError(f"case {case_id} has unknown execution expectation: {expectation!r}")

    required_payload = row["required_candidates"]
    if not isinstance(required_payload, Mapping):
        raise CompositeError(f"case {case_id} required_candidates must be an object")
    unknown_kinds = sorted(set(required_payload) - set(SCORED_KINDS) - {KIND_ENTITY})
    if unknown_kinds:
        raise CompositeError(f"case {case_id} names unknown candidate kinds: {unknown_kinds}")
    required: dict[str, tuple[str, ...]] = {}
    for kind in SCORED_KINDS:
        ids = tuple(str(value) for value in required_payload.get(kind, ()))
        _assert_known(vocabulary, case_id, ids)
        for semantic_id in ids:
            actual = candidate_kind(vocabulary, semantic_id)
            if actual != kind:
                raise CompositeError(
                    f"case {case_id} lists {semantic_id} under {kind!r} but the Registry "
                    f"classifies it as {actual!r}"
                )
        required[kind] = ids
    if required_payload.get(KIND_ENTITY):
        raise CompositeError(
            f"case {case_id} must record entity expectations in entity_mentions, not as "
            "Registry semantic IDs"
        )

    alternatives_payload = row["equivalent_alternatives"]
    if not isinstance(alternatives_payload, Mapping):
        raise CompositeError(f"case {case_id} equivalent_alternatives must be an object")
    alternatives: dict[str, tuple[str, ...]] = {}
    all_required = {value for values in required.values() for value in values}
    for key, values in alternatives_payload.items():
        if key not in all_required:
            raise CompositeError(
                f"case {case_id} declares an alternative for {key!r}, which it does not require"
            )
        ids = tuple(str(value) for value in values)
        _assert_known(vocabulary, case_id, ids)
        alternatives[str(key)] = ids

    confusion_payload = row["confusion_sets"]
    if not isinstance(confusion_payload, Mapping):
        raise CompositeError(f"case {case_id} confusion_sets must be an object")
    unknown_categories = sorted(set(confusion_payload) - ALLOWED_CONFUSION_CATEGORIES)
    if unknown_categories:
        raise CompositeError(
            f"case {case_id} has unknown confusion categories: {unknown_categories}"
        )
    confusion: dict[str, tuple[str, ...]] = {}
    for category, values in confusion_payload.items():
        ids = tuple(str(value) for value in values)
        _assert_known(vocabulary, case_id, ids)
        overlap = sorted(set(ids) & all_required)
        if overlap:
            raise CompositeError(
                f"case {case_id} lists {overlap} as both required and confusable"
            )
        confusion[str(category)] = ids

    allowed = tuple(str(value) for value in row["confusable_candidates_allowed"])
    _assert_known(vocabulary, case_id, allowed)

    mentions = tuple(
        EntityMention(
            mention_role=str(item.get("mention_role", "")),
            expected_resolution=str(item.get("expected_resolution", "")),
        )
        for item in row["entity_mentions"]
        if isinstance(item, Mapping)
    )
    if section == SECTION_CLEAR and not any(required[kind] for kind in SCORED_KINDS):
        raise CompositeError(f"clear case {case_id} must require at least one candidate")
    return CompositeCase(
        case_id=case_id,
        section=section,
        question=str(row["question"]),
        required=required,
        alternatives=alternatives,
        entity_mentions=mentions,
        confusion_sets=confusion,
        allowed_confusable=allowed,
        execution_expectation=expectation,
    )


def _assert_known(vocabulary: Vocabulary, case_id: str, ids: Sequence[str]) -> None:
    unknown = sorted(value for value in ids if not vocabulary.has(value))
    if unknown:
        raise CompositeError(f"case {case_id} names unknown semantic IDs: {unknown}")


def evaluate_composite(
    vocabulary: Vocabulary,
    index: RetrievalIndex,
    provider: EmbeddingProvider,
    cases: Sequence[CompositeCase],
    *,
    rule_settings: RuleSettings,
    top_ks: Sequence[int] = RECALL_KS,
    budget_grid: Sequence[Mapping[str, int]] = (),
) -> dict[str, Any]:
    """Evaluate one model on composite questions. Text goes only to the provider."""
    assert_usable(index, vocabulary, provider.identity)
    prepared = tuple(
        _prepare(vocabulary, index, provider, case, rule_settings) for case in cases
    )
    ks = tuple(sorted({int(value) for value in top_ks}))
    if any(value < 1 for value in ks):
        raise CompositeError("top-k values must be positive")

    latencies = sorted(item.latency_ms for item in prepared)
    return {
        "experiment": "composite_question_candidate_recovery",
        "model": index.identity.to_dict(),
        "registry_content_hash": vocabulary.content_hash,
        "index_generated_at": index.manifest.get("generated_at", ""),
        "decision_status": "evidence_only_no_threshold_or_top_k_settled",
        "budget_basis": "offline_simulation_over_merged_order_not_a_product_setting",
        "case_counts": {
            section: sum(1 for item in prepared if item.case.section == section)
            for section in sorted(ALLOWED_SECTIONS)
        },
        "path_recall_by_kind": [_path_recall(prepared, k) for k in ks],
        "global_top_k": [_global_row(vocabulary, prepared, k) for k in ks],
        "budget_simulation": [
            _budget_row(vocabulary, prepared, budget) for budget in budget_grid
        ],
        "entity_gap": _entity_gap(prepared),
        "case_results": _case_results(vocabulary, prepared, max(ks)),
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
        },
        "top_ks": list(ks),
        "question_text_in_report": False,
    }


def _prepare(
    vocabulary: Vocabulary,
    index: RetrievalIndex,
    provider: EmbeddingProvider,
    case: CompositeCase,
    rule_settings: RuleSettings,
) -> PreparedCase:
    matches, truncated = rule_search(vocabulary, case.question, rule_settings)
    rule_ids = _deduplicate(match.semantic_id for match in matches)
    grounding_ids = _deduplicate(
        match.semantic_id for match in matches if match.grounding_eligible
    )
    started = time.perf_counter()
    vectors = provider.embed([case.question])
    if len(vectors) != 1:
        raise CompositeError("embedding provider did not return exactly one query vector")
    latency = (time.perf_counter() - started) * 1000
    scored = index.search(vectors[0], top_k=len(index.entries), threshold=-math.inf)
    best: dict[str, float] = {}
    for item in scored:
        prior = best.get(item.entry.semantic_id)
        if prior is None or item.similarity > prior:
            best[item.entry.semantic_id] = item.similarity
    ranking = tuple(sorted(best.items(), key=lambda item: (-item[1], item[0])))
    kinds = {
        semantic_id: candidate_kind(vocabulary, semantic_id) for semantic_id, _score in ranking
    }
    for semantic_id in rule_ids:
        kinds.setdefault(semantic_id, candidate_kind(vocabulary, semantic_id))
    return PreparedCase(
        case=case,
        rule_ids=rule_ids,
        rule_grounding_ids=grounding_ids,
        rule_truncated=truncated,
        embedding_ranking=ranking,
        latency_ms=latency,
        kinds=kinds,
    )


def _satisfied(case: CompositeCase, semantic_id: str, returned: set[str]) -> bool:
    return any(value in returned for value in case.accepted_for(semantic_id))


def _kind_recall(items: Sequence[PreparedCase], kind: str, ids_of) -> dict[str, Any] | None:
    """Recall over the cases that actually require this candidate kind."""
    scoped = [item for item in items if item.case.required.get(kind)]
    if not scoped:
        return None
    per_case: list[float] = []
    complete: list[float] = []
    missing: list[dict[str, str]] = []
    for item in scoped:
        returned = set(ids_of(item))
        required = item.case.required[kind]
        hits = [_satisfied(item.case, value, returned) for value in required]
        per_case.append(fmean(float(value) for value in hits))
        complete.append(float(all(hits)))
        for value, hit in zip(required, hits, strict=True):
            if not hit:
                missing.append({"case_id": item.case.case_id, "semantic_id": value})
    return {
        "kind": kind,
        "cases_requiring_kind": len(scoped),
        "mean_required_id_recall": round(fmean(per_case), 6),
        "all_required_of_kind_recall": round(fmean(complete), 6),
        "missing": missing,
    }


def _path_recall(prepared: Sequence[PreparedCase], top_k: int) -> dict[str, Any]:
    """Keep the rule path, the embedding path and their merge separable."""
    paths = {
        "rule_only": lambda item: item.rule_ids,
        "rule_grounding_only": lambda item: item.rule_grounding_ids,
        "embedding_only": lambda item: item.embedding_ids(top_k),
        "merged": lambda item: item.merged(top_k),
    }
    rows: dict[str, Any] = {"top_k": top_k}
    for name, ids_of in paths.items():
        by_kind = [
            row for kind in SCORED_KINDS if (row := _kind_recall(prepared, kind, ids_of))
        ]
        joint = [
            float(
                all(
                    _satisfied(item.case, value, set(ids_of(item)))
                    for value in item.case.required_ids
                )
            )
            for item in prepared
            if item.case.required_ids
        ]
        rows[name] = {
            "by_kind": by_kind,
            "all_required_recall": round(fmean(joint), 6) if joint else None,
            "all_required_scored_cases": len(joint),
        }
    return rows


def _confusion_counts(
    item: PreparedCase, returned: Sequence[str]
) -> dict[str, dict[str, int]]:
    returned_set = set(returned)
    grounding = set(item.rule_grounding_ids)
    counts: dict[str, dict[str, int]] = {}
    for category, ids in item.case.confusion_sets.items():
        counts[category] = {
            "as_candidate": sum(1 for value in ids if value in returned_set),
            "as_grounding": sum(1 for value in ids if value in grounding),
            "declared": len(ids),
        }
    return counts


def _case_metrics(
    item: PreparedCase, returned: Sequence[str]
) -> dict[str, Any]:
    returned_set = set(returned)
    required = item.case.required_ids
    hits = [value for value in required if _satisfied(item.case, value, returned_set)]
    accepted = {
        value for semantic_id in required for value in item.case.accepted_for(semantic_id)
    }
    relevant = len(returned_set & accepted)
    return {
        "case_id": item.case.case_id,
        "section": item.case.section,
        "execution_expectation": item.case.execution_expectation,
        "required_id_count": len(required),
        "required_ids_recovered": len(hits),
        "all_required_recovered": len(hits) == len(required) if required else None,
        "candidate_count": len(returned),
        "relevant_candidate_count": relevant,
        "irrelevant_candidate_count": len(returned) - relevant,
        "candidate_precision": round(relevant / len(returned), 6) if returned else 0.0,
        "confusion": _confusion_counts(item, returned),
        "missing_required_ids": [
            value for value in required if not _satisfied(item.case, value, returned_set)
        ],
    }


def _global_row(
    vocabulary: Vocabulary, prepared: Sequence[PreparedCase], top_k: int
) -> dict[str, Any]:
    rows = []
    for item in prepared:
        merged = item.merged(top_k)
        metrics = _case_metrics(item, merged)
        available = len(_deduplicate((*item.rule_ids, *item.embedding_ids(len(item.kinds)))))
        metrics["global_truncated_candidates"] = max(0, available - len(merged))
        metrics["kind_mix"] = _kind_mix(vocabulary, merged)
        rows.append(metrics)
    return {"top_k": top_k, "aggregate": _aggregate(rows), "cases": rows}


def _budget_row(
    vocabulary: Vocabulary, prepared: Sequence[PreparedCase], budget: Mapping[str, int]
) -> dict[str, Any]:
    limits = {str(key): int(value) for key, value in budget.items()}
    unknown = sorted(set(limits) - set(SCORED_KINDS) - {KIND_OTHER})
    if unknown:
        raise CompositeError(f"budget names unknown candidate kinds: {unknown}")
    rows = []
    for item in prepared:
        full = item.merged(len(item.kinds) + len(item.rule_ids))
        kept: list[str] = []
        used: dict[str, int] = {}
        dropped: dict[str, int] = {}
        for semantic_id in full:
            kind = item.kinds.get(semantic_id, KIND_OTHER)
            limit = limits.get(kind, 0)
            if used.get(kind, 0) < limit:
                kept.append(semantic_id)
                used[kind] = used.get(kind, 0) + 1
            else:
                dropped[kind] = dropped.get(kind, 0) + 1
        metrics = _case_metrics(item, kept)
        metrics["budget_truncated_by_kind"] = dict(sorted(dropped.items()))
        metrics["kind_mix"] = _kind_mix(vocabulary, kept)
        rows.append(metrics)
    return {
        "budget": dict(sorted(limits.items())),
        "budget_total": sum(limits.values()),
        "aggregate": _aggregate(rows),
        "cases": rows,
    }


def _kind_mix(vocabulary: Vocabulary, ids: Sequence[str]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for semantic_id in ids:
        kind = candidate_kind(vocabulary, semantic_id)
        mix[kind] = mix.get(kind, 0) + 1
    return dict(sorted(mix.items()))


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row["all_required_recovered"] is not None]
    confusion: dict[str, dict[str, int]] = {}
    for row in rows:
        for category, counts in row["confusion"].items():
            bucket = confusion.setdefault(
                category, {"as_candidate": 0, "as_grounding": 0, "declared": 0}
            )
            for key, value in counts.items():
                bucket[key] += value
    return {
        "cases": len(rows),
        "all_required_recall": (
            round(fmean(float(row["all_required_recovered"]) for row in scored), 6)
            if scored
            else None
        ),
        "mean_candidate_count": round(fmean(float(row["candidate_count"]) for row in rows), 6),
        "mean_irrelevant_candidates": round(
            fmean(float(row["irrelevant_candidate_count"]) for row in rows), 6
        ),
        "mean_candidate_precision": round(
            fmean(float(row["candidate_precision"]) for row in rows), 6
        ),
        "confusion_totals": dict(sorted(confusion.items())),
    }


def _entity_gap(prepared: Sequence[PreparedCase]) -> dict[str, Any]:
    mentions = [
        {
            "case_id": item.case.case_id,
            "mention_role": mention.mention_role,
            "expected_resolution": mention.expected_resolution,
        }
        for item in prepared
        for mention in item.case.entity_mentions
    ]
    return {
        "cases_with_entity_mention": len({row["case_id"] for row in mentions}),
        "entity_mention_count": len(mentions),
        "entity_candidate_recall": 0.0,
        "reason": "the Semantic Registry holds terms, not product or security instances",
        "excluded_from_all_required_recall": True,
        "mentions": mentions,
    }


def _case_results(
    vocabulary: Vocabulary, prepared: Sequence[PreparedCase], top_k: int
) -> list[dict[str, Any]]:
    """Expose candidate IDs for review while deliberately omitting question text."""
    rows = []
    for item in prepared:
        merged = item.merged(top_k)
        rows.append(
            {
                "case_id": item.case.case_id,
                "section": item.case.section,
                "required_candidates": {
                    kind: list(values)
                    for kind, values in item.case.required.items()
                    if values
                },
                "rule_candidate_ids": list(item.rule_ids),
                "rule_grounding_ids": list(item.rule_grounding_ids),
                "rule_truncated": item.rule_truncated,
                "embedding_top20": [
                    {"semantic_id": semantic_id, "score": round(score, 8), "rank": rank}
                    for rank, (semantic_id, score) in enumerate(item.embedding_ranking[:20], 1)
                ],
                "merged_ids": list(merged),
                "merged_kinds": _kind_mix(vocabulary, merged),
                "required_rank_in_merged": _required_ranks(item, merged),
                "latency_ms": round(item.latency_ms, 3),
            }
        )
    return rows


def _required_ranks(item: PreparedCase, merged: Sequence[str]) -> list[dict[str, Any]]:
    positions = {semantic_id: rank for rank, semantic_id in enumerate(merged, 1)}
    rows = []
    for semantic_id in item.case.required_ids:
        found = [
            (positions[value], value)
            for value in item.case.accepted_for(semantic_id)
            if value in positions
        ]
        best = min(found) if found else None
        rows.append(
            {
                "semantic_id": semantic_id,
                "kind": item.kinds.get(semantic_id, KIND_OTHER),
                "merged_rank": best[0] if best else None,
                "satisfied_by": best[1] if best else None,
                "in_rule_path": semantic_id in item.rule_ids,
                "grounding_eligible": semantic_id in item.rule_grounding_ids,
            }
        )
    return rows


def _deduplicate(values) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    position = min(len(values) - 1, max(0, math.ceil(fraction * len(values)) - 1))
    return values[position]
