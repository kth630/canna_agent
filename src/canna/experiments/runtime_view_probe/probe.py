"""One measured Runtime View request for the stage 1-A experiment.

Experiment only. A case is data: a question, an optional budget and the gold
candidates a reviewer decided the question needs. The probe never looks at a
case identifier, and the modules it calls never see one.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from .diagnostics import RetrievalOutcome, assess
from .measurement import RecallReport, aggregate_recall, required_candidate_recall
from .registry import Registry
from .retrieval import RetrievalResult, retrieve
from .view import RefMinter, RuntimeViewBundle, build_view


class ProbeCase(BaseModel):
    """One question and the gold retrieval expectation attached to it."""

    model_config = ConfigDict(frozen=True)

    case_key: str
    question: str
    required_candidate_ids: tuple[str, ...] = ()
    required_neighbor_ids: tuple[str, ...] = ()
    candidate_budget: int | None = None


class ProbeRecord(BaseModel):
    """Everything one request produced, including what it failed to produce."""

    model_config = ConfigDict(frozen=True)

    case_key: str
    question: str
    retrieval: RetrievalResult
    outcome: RetrievalOutcome
    bundle: RuntimeViewBundle
    recall: RecallReport
    retrieval_latency_ms: float
    view_latency_ms: float

    def as_transcript_record(self) -> dict[str, object]:
        """Flatten to JSON for provenance, keeping server-side state visible.

        The transcript is a server-side record, so it keeps semantic ids and the
        ref map; that is what makes a run auditable. It is never sent anywhere.
        """
        return {
            "case_key": self.case_key,
            "question": self.question,
            "candidate_budget": self.retrieval.candidate_budget,
            "presentation_order": list(self.bundle.view.presentation_order()),
            "candidate_reasons": {
                candidate.semantic_id: list(candidate.reasons)
                for candidate in self.retrieval.admitted
            },
            "truncated": [item.model_dump() for item in self.retrieval.truncated],
            "matched_capability_ids": list(self.retrieval.matched_capability_ids),
            "outcome": self.outcome.model_dump(),
            "metrics": {
                **self.bundle.metrics.model_dump(),
                "retrieval_latency_ms": round(self.retrieval_latency_ms, 3),
                "view_latency_ms": round(self.view_latency_ms, 3),
            },
            "recall": {
                "required": list(self.recall.required),
                "retrieved": list(self.recall.retrieved),
                "missing": [item.model_dump() for item in self.recall.missing],
                "question_recall": self.recall.recall,
                "per_family_recall": self.recall.per_family_recall(),
                "neighbors_required": list(self.recall.neighbors_required),
                "neighbors_missing": list(self.recall.neighbors_missing),
            },
            "semantic_id_by_ref": dict(self.bundle.semantic_id_by_ref),
            "prompt_payload": self.bundle.view.as_prompt_payload(),
        }


def run_case(
    registry: Registry,
    case: ProbeCase,
    minter: RefMinter | None = None,
) -> ProbeRecord:
    """Retrieve, build the view, judge it, and measure it — in that order."""
    started = time.perf_counter()
    result = retrieve(registry, case.question, case.candidate_budget)
    retrieved_at = time.perf_counter()
    bundle = build_view(registry, result, minter or RefMinter())
    built_at = time.perf_counter()

    return ProbeRecord(
        case_key=case.case_key,
        question=case.question,
        retrieval=result,
        outcome=assess(registry, result),
        bundle=bundle,
        recall=required_candidate_recall(
            registry,
            result,
            case.required_candidate_ids,
            case.required_neighbor_ids,
        ),
        retrieval_latency_ms=(retrieved_at - started) * 1000,
        view_latency_ms=(built_at - retrieved_at) * 1000,
    )


def summarise(records: Sequence[ProbeRecord]) -> Mapping[str, object]:
    """Aggregate a run: recall, view size, latency and failure mix."""
    if not records:
        return {"cases": 0}
    counts = sorted(record.bundle.metrics.candidate_count for record in records)
    sizes = sorted(record.bundle.metrics.serialized_bytes for record in records)
    latencies = sorted(
        record.retrieval_latency_ms + record.view_latency_ms for record in records
    )
    failure_mix: dict[str, int] = {}
    for record in records:
        for kind in record.outcome.failure_kinds():
            failure_mix[kind] = failure_mix.get(kind, 0) + 1

    return {
        "cases": len(records),
        "recall": aggregate_recall([record.recall for record in records]),
        "neighbor_recall": {
            "required": sum(len(record.recall.neighbors_required) for record in records),
            "missing": sum(len(record.recall.neighbors_missing) for record in records),
        },
        "executable_cases": sum(1 for record in records if record.outcome.executable),
        "failure_kind_counts": dict(sorted(failure_mix.items())),
        "candidate_count": _distribution(counts),
        "serialized_bytes": _distribution(sizes),
        "total_latency_ms": _distribution([round(value, 3) for value in latencies]),
    }


def _distribution(values: Sequence[float]) -> Mapping[str, float]:
    return {
        "min": values[0],
        "median": values[len(values) // 2],
        "max": values[-1],
        "mean": round(sum(values) / len(values), 3),
    }
