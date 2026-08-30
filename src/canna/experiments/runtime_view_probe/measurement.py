"""Required-candidate recall for the stage 1-A Runtime View experiment.

Experiment only, and harness-side only. ``ARCHITECTURE.md`` section 3 says a
Runtime View that drops a candidate lowers the accuracy ceiling of everything
after it, so retrieval recall is measured independently of the model. That
measurement needs gold labels, which exist only in fixtures — so nothing in the
request path may call into this module's inputs.

Recall is reported per question and per product family, because a view can be
complete for one family and empty for another in the same question.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from .registry import Registry
from .retrieval import TRUNCATION_BUDGET, TRUNCATION_DEPENDENCY, RetrievalResult

MISS_NOT_MATCHED = "not_matched"
MISS_BUDGET_TRUNCATED = "budget_truncated"
MISS_DEPENDENCY_TRUNCATED = "dependency_truncated"

UNSCOPED_FAMILY = "__unscoped__"


class MissingCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    semantic_id: str
    kind: str
    reason: str


class FamilyRecall(BaseModel):
    model_config = ConfigDict(frozen=True)

    family_id: str
    required: int
    retrieved: int

    @property
    def recall(self) -> float:
        return 1.0 if self.required == 0 else self.retrieved / self.required


class RecallReport(BaseModel):
    """Gold-based retrieval measurement for one question."""

    model_config = ConfigDict(frozen=True)

    required: tuple[str, ...]
    retrieved: tuple[str, ...]
    missing: tuple[MissingCandidate, ...]
    per_family: tuple[FamilyRecall, ...]
    neighbors_required: tuple[str, ...] = ()
    neighbors_missing: tuple[str, ...] = ()

    @property
    def recall(self) -> float:
        return 1.0 if not self.required else len(self.retrieved) / len(self.required)

    @property
    def complete(self) -> bool:
        return not self.missing

    def per_family_recall(self) -> dict[str, float]:
        return {family.family_id: family.recall for family in self.per_family}


def required_candidate_recall(
    registry: Registry,
    result: RetrievalResult,
    required_ids: Sequence[str],
    neighbor_ids: Sequence[str] = (),
) -> RecallReport:
    """Measure whether the view carries every candidate the question needs.

    A required candidate that is unknown to the registry is a broken fixture,
    not a retrieval miss, so it raises instead of scoring zero.
    """
    unknown = sorted(
        semantic_id
        for semantic_id in tuple(required_ids) + tuple(neighbor_ids)
        if not registry.has(semantic_id)
    )
    if unknown:
        raise KeyError(f"gold references candidates absent from the registry: {unknown}")

    admitted = set(result.admitted_ids())
    truncation_reason = {
        candidate.semantic_id: candidate.reason for candidate in result.truncated
    }

    retrieved = tuple(
        semantic_id for semantic_id in required_ids if semantic_id in admitted
    )
    missing = tuple(
        MissingCandidate(
            semantic_id=semantic_id,
            kind=registry.entry(semantic_id).kind,
            reason=_miss_reason(truncation_reason.get(semantic_id)),
        )
        for semantic_id in required_ids
        if semantic_id not in admitted
    )

    return RecallReport(
        required=tuple(required_ids),
        retrieved=retrieved,
        missing=missing,
        per_family=_family_recall(registry, required_ids, admitted),
        neighbors_required=tuple(neighbor_ids),
        neighbors_missing=tuple(
            semantic_id for semantic_id in neighbor_ids if semantic_id not in admitted
        ),
    )


def _miss_reason(truncation: str | None) -> str:
    if truncation == TRUNCATION_BUDGET:
        return MISS_BUDGET_TRUNCATED
    if truncation == TRUNCATION_DEPENDENCY:
        return MISS_DEPENDENCY_TRUNCATED
    return MISS_NOT_MATCHED


def _family_recall(
    registry: Registry,
    required_ids: Sequence[str],
    admitted: set[str],
) -> tuple[FamilyRecall, ...]:
    """Group required candidates by the family whose meaning they carry.

    A predicate scoped to several families counts once per family it is scoped
    to: losing it damages the answer for each of them.
    """
    totals: dict[str, list[int]] = {}
    for semantic_id in required_ids:
        families = registry.family_ids(semantic_id) or (UNSCOPED_FAMILY,)
        for family_id in families:
            bucket = totals.setdefault(family_id, [0, 0])
            bucket[0] += 1
            if semantic_id in admitted:
                bucket[1] += 1
    return tuple(
        FamilyRecall(family_id=family_id, required=counts[0], retrieved=counts[1])
        for family_id, counts in sorted(totals.items())
    )


def aggregate_recall(reports: Sequence[RecallReport]) -> Mapping[str, object]:
    """Aggregate question-level and family-level recall across a run."""
    required_total = sum(len(report.required) for report in reports)
    retrieved_total = sum(len(report.retrieved) for report in reports)
    per_family: dict[str, list[int]] = {}
    for report in reports:
        for family in report.per_family:
            bucket = per_family.setdefault(family.family_id, [0, 0])
            bucket[0] += family.required
            bucket[1] += family.retrieved
    return {
        "questions": len(reports),
        "required_candidates": required_total,
        "retrieved_candidates": retrieved_total,
        "micro_recall": 1.0 if required_total == 0 else retrieved_total / required_total,
        "questions_with_complete_recall": sum(1 for report in reports if report.complete),
        "per_family_recall": {
            family_id: (1.0 if counts[0] == 0 else counts[1] / counts[0])
            for family_id, counts in sorted(per_family.items())
        },
        "per_family_required": {
            family_id: counts[0] for family_id, counts in sorted(per_family.items())
        },
    }
